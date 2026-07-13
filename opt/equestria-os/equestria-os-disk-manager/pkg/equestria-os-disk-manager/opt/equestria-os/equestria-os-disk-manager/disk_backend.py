"""
CLI backend for privileged disk operations in Equestria OS.
"""
import sys
import os
import re
import glob
import json
import stat
import shutil
import tempfile
import subprocess

# Переопределяются только в тестах (pkexec запускает бэкенд с чистым окружением)
FSTAB_PATH = os.environ.get("EQ_FSTAB", "/etc/fstab")
NET_CRED_DIR = os.environ.get("EQ_NET_CRED_DIR", "/etc/equestria-os/net-credentials")
DAV_SECRETS = os.environ.get("EQ_DAV_SECRETS", "/etc/davfs2/secrets")

# Пределы длины метки по правилам самих ФС — mkfs падает при превышении
LABEL_LIMITS = {
    "ext2": 16, "ext3": 16, "ext4": 16,
    "btrfs": 255,
    "ntfs": 32,
    "exfat": 11,
    "fat32": 11, "fat16": 11, "vfat": 11,
}
FAT16_MAX_MIB = 4096  # том FAT16 больше 4 ГиБ не существует
FAT_LABEL_RE = re.compile(r"[A-Za-z0-9 _.\-]+")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
FAT_ID_RE = re.compile(r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}")


def _fail(msg):
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(1)


# ── Выбор драйвера NTFS ────────────────────────────────────────────
# С ядра 7.1 в mainline вернулся драйвер «ntfs» (бывший NTFSPlus) — быстрее
# и современнее ntfs3. До 6.9 «ntfs» — это СТАРЫЙ драйвер только для чтения,
# поэтому имя ntfs признаём новым драйвером только на ядрах >= 6.9.

def _kernel_tuple(release):
    m = re.match(r"(\d+)\.(\d+)", release)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _kernel_has_module(release, subpath):
    return bool(glob.glob(f"/lib/modules/{release}/kernel/fs/{subpath}"))


def _new_ntfs_in_kernel(release):
    return (_kernel_tuple(release) >= (6, 9)
            and _kernel_has_module(release, "ntfs/ntfs.ko*"))


def ntfs_mount_type():
    """Лучший тип NTFS для разового mount на ТЕКУЩЕМ ядре."""
    rel = os.uname().release
    try:
        builtin = open("/proc/filesystems").read()
    except OSError:
        builtin = ""
    if _new_ntfs_in_kernel(rel) or ("\tntfs\n" in builtin and _kernel_tuple(rel) >= (6, 9)):
        return "ntfs"
    if _kernel_has_module(rel, "ntfs3/ntfs3.ko*") or "ntfs3" in builtin:
        return "ntfs3"
    if shutil.which("ntfs-3g"):
        return "ntfs-3g"
    return "ntfs3"


def ntfs_fstab_type():
    """Тип NTFS для fstab: обязан работать на ВСЕХ установленных ядрах
    (система может грузиться и в linux, и в linux-lts)."""
    try:
        kernels = [k for k in os.listdir("/lib/modules")
                   if os.path.isdir(f"/lib/modules/{k}/kernel")]
    except OSError:
        kernels = []
    if kernels and all(_new_ntfs_in_kernel(k) for k in kernels):
        return "ntfs"
    if kernels and all(_kernel_has_module(k, "ntfs3/ntfs3.ko*") for k in kernels):
        return "ntfs3"
    if shutil.which("ntfs-3g"):
        return "ntfs-3g"
    return "ntfs3"


def remove_from_fstab(uuid):
    if not os.path.exists(FSTAB_PATH):
        return
    with open(FSTAB_PATH, 'r') as f:
        lines = f.readlines()
    with open(FSTAB_PATH, 'w') as f:
        for line in lines:
            if not line.strip().startswith(f"UUID={uuid}"):
                f.write(line)
    sys.stdout.write(f"OK: Removed {uuid} from fstab\n")


def add_to_fstab(uuid, mountpoint, fstype, options):
    # NTFS: подставляем лучший драйвер, работающий на всех установленных ядрах
    if fstype in ("ntfs", "ntfs-3g", "ntfs3"):
        fstype = ntfs_fstab_type()
    if fstype in ("fat32", "fat16"):
        fstype = "vfat"
    # pass=2 только там, где существует fsck.<тип>; для ntfs его нет
    passno = {"ext2": 2, "ext3": 2, "ext4": 2,
              "vfat": 2, "exfat": 2}.get(fstype, 0)

    old_content = None
    if os.path.exists(FSTAB_PATH):
        with open(FSTAB_PATH) as f:
            old_content = f.read()

    remove_from_fstab(uuid)
    os.makedirs(mountpoint, exist_ok=True)
    safe_mp = mountpoint.replace(" ", "\\040")
    with open(FSTAB_PATH, 'a') as f:
        f.write(f"UUID={uuid}\t{safe_mp}\t{fstype}\t{options}\t0\t{passno}\n")

    # Если раздел уже смонтирован в другом месте — пробное монтирование
    # только запутает; оставляем запись, она сработает со следующей загрузки
    already = subprocess.run(["findmnt", "-S", f"UUID={uuid}"],
                             capture_output=True).returncode == 0
    if already:
        sys.stdout.write(f"OK: Added {uuid} to fstab (already mounted elsewhere)\n")
        return

    # Проба монтирования: кривые опции не должны доехать до перезагрузки
    r = subprocess.run(["mount", mountpoint], capture_output=True, text=True)
    if r.returncode != 0:
        if old_content is not None:
            with open(FSTAB_PATH, 'w') as f:
                f.write(old_content)
        _fail("Mount failed, fstab entry was NOT saved: "
              + (r.stderr or r.stdout).strip())
    sys.stdout.write(f"OK: Added {uuid} and mounted to {mountpoint}\n")


def mount_partition(device, mountpoint):
    os.makedirs(mountpoint, exist_ok=True)
    dev = f"/dev/{device}"
    fstype = subprocess.run(["lsblk", "-ndo", "FSTYPE", dev],
                            capture_output=True, text=True).stdout.strip()
    cmd = ["mount"]
    if fstype in ("ntfs", "ntfs-3g"):
        cmd += ["-t", ntfs_mount_type()]
    # ФС без прав доступа монтируем на пользователя, запустившего GUI,
    # иначе диск принадлежит root и в него нельзя писать
    if fstype in ("ntfs", "ntfs-3g", "vfat", "exfat"):
        caller_uid = os.environ.get("PKEXEC_UID") or os.environ.get("SUDO_UID")
        if caller_uid and caller_uid.isdigit():
            try:
                import pwd
                gid = pwd.getpwuid(int(caller_uid)).pw_gid
            except (KeyError, ValueError):
                gid = caller_uid
            cmd += ["-o", f"uid={caller_uid},gid={gid}"]
    cmd += [dev, mountpoint]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        _fail((r.stderr or r.stdout).strip() or "mount failed")
    sys.stdout.write(f"OK: Mounted {dev} to {mountpoint}\n")


def umount_partition(mountpoint):
    subprocess.run(["umount", mountpoint], check=True)
    sys.stdout.write(f"OK: Unmounted {mountpoint}\n")


def fix_permissions(mountpoint, username, recursive=False):
    if not os.path.ismount(mountpoint):
        subprocess.run(["mount", mountpoint], check=False)
    if not os.path.exists(mountpoint):
        sys.stderr.write(f"Error: Mountpoint {mountpoint} does not exist\n")
        sys.exit(1)

    chown_cmd = ["chown"]
    chmod_cmd = ["chmod"]
    if recursive:
        chown_cmd.append("-R")
        chmod_cmd.append("-R")
    chown_cmd.extend([f"{username}:{username}", mountpoint])
    chmod_cmd.extend(["u+rwX", mountpoint])

    subprocess.run(chown_cmd, check=True)
    subprocess.run(chmod_cmd, check=True)
    sys.stdout.write(f"OK: Permissions fixed for {mountpoint} (owner: {username})\n")


def set_label(device, fstype, label):
    dev = f"/dev/{device}"
    if fstype in ("ext2", "ext3", "ext4"):
        subprocess.run(["e2label", dev, label], check=True)
    elif fstype == "btrfs":
        subprocess.run(["btrfs", "filesystem", "label", dev, label], check=True)
    elif fstype in ("ntfs", "ntfs-3g"):
        subprocess.run(["ntfslabel", dev, label], check=True)
    elif fstype == "exfat":
        subprocess.run(["exfatlabel", dev, label], check=True)
    elif fstype in ("vfat", "fat32"):
        subprocess.run(["fatlabel", dev, label], check=True)
    else:
        sys.stderr.write(f"Error: Setting label not supported for {fstype}\n")
        sys.exit(1)
    sys.stdout.write(f"OK: Label set to '{label}' on {dev}\n")


def add_nofail_to_fstab(uuid):
    if not os.path.exists(FSTAB_PATH):
        return
    with open(FSTAB_PATH, 'r') as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#") and f"UUID={uuid}" in stripped:
            raw_parts = stripped.split()
            if len(raw_parts) >= 6:
                opts = raw_parts[-3]
                if "nofail" not in opts.split(","):
                    line = line.replace(opts, opts + ",nofail", 1)
        new_lines.append(line)
    with open(FSTAB_PATH, 'w') as f:
        f.writelines(new_lines)
    sys.stdout.write(f"OK: Added nofail to {uuid} in fstab\n")


def validate_label(fstype, label):
    """Возвращает текст ошибки или None. Проверяем ДО запуска mkfs,
    чтобы пользователь получил понятное сообщение, а не вывод mkfs."""
    limit = LABEL_LIMITS.get(fstype)
    if limit and len(label) > limit:
        return f"Label is longer than {limit} characters allowed for {fstype}"
    if "\n" in label or "\t" in label:
        return "Label contains forbidden characters"
    if fstype in ("fat32", "fat16", "vfat", "exfat") and not FAT_LABEL_RE.fullmatch(label):
        return "FAT/exFAT label: only letters, digits, space, '_', '.', '-'"
    return None


def build_mkfs_cmd(device, fstype, label=None, keep_uuid=None):
    """Собирает команду mkfs. Общая точка для бэкенда и предпросмотра в GUI.
    Ничего не запускает; на некорректные параметры кидает ValueError."""
    dev = f"/dev/{device}"
    if label:
        err = validate_label(fstype, label)
        if err:
            raise ValueError(err)
    if keep_uuid:
        want = FAT_ID_RE if fstype in ("fat32", "fat16", "vfat") else UUID_RE
        if fstype in ("ntfs", "exfat"):
            raise ValueError(f"Keeping UUID is not supported for {fstype}")
        if not want.fullmatch(keep_uuid):
            raise ValueError(f"UUID {keep_uuid!r} does not match {fstype} format")

    if fstype in ("ext4", "ext3", "ext2"):
        cmd = [f"mkfs.{fstype}", "-F"]
        cmd += ["-L", label] if label else []
        cmd += ["-U", keep_uuid] if keep_uuid else []
    elif fstype == "btrfs":
        cmd = ["mkfs.btrfs", "-f"]
        cmd += ["-L", label] if label else []
        cmd += ["-U", keep_uuid] if keep_uuid else []
    elif fstype == "ntfs":
        # -f: быстрое форматирование; без него mkntfs зануляет весь раздел
        cmd = ["mkfs.ntfs", "-f"]
        cmd += ["-L", label] if label else []
    elif fstype == "exfat":
        cmd = ["mkfs.exfat"]
        cmd += ["-n", label] if label else []
    elif fstype in ("fat32", "fat16", "vfat"):
        cmd = ["mkfs.vfat", "-F", "16" if fstype == "fat16" else "32"]
        # FAT хранит метку в верхнем регистре; mkfs.fat ругается на нижний
        cmd += ["-n", label.upper()] if label else []
        cmd += ["-i", keep_uuid.replace("-", "")] if keep_uuid else []
    else:
        raise ValueError(f"Unsupported filesystem: {fstype}")
    cmd.append(dev)
    return cmd


def check_format_target(device):
    """Все проверки безопасности перед форматированием. Любая ошибка — отказ
    ДО того, как хоть один байт будет изменён."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", device):
        _fail(f"Invalid device name: {device!r}")
    dev = f"/dev/{device}"
    try:
        st = os.stat(dev)
    except OSError:
        _fail(f"{dev} does not exist")
    if not stat.S_ISBLK(st.st_mode):
        _fail(f"{dev} is not a block device")

    dev_type = subprocess.run(["lsblk", "-ndo", "TYPE", dev],
                              capture_output=True, text=True).stdout.strip()
    # Раздел распознаём и по PARTN: у разделов loop-устройств TYPE бывает "loop"
    partn = subprocess.run(["lsblk", "-ndo", "PARTN", dev],
                           capture_output=True, text=True).stdout.strip()
    if dev_type != "part" and not partn:
        _fail(f"{dev} is not a partition (type: {dev_type or 'unknown'}) — "
              "formatting whole disks is not allowed")

    if subprocess.run(["findmnt", "--source", dev],
                      capture_output=True).returncode == 0:
        _fail(f"{dev} is mounted — unmount it first")

    try:
        with open("/proc/swaps") as f:
            for line in f.readlines()[1:]:
                if line.split()[0] == dev:
                    _fail(f"{dev} is an active swap — disable it first")
    except OSError:
        pass

    holders_dir = f"/sys/class/block/{device}/holders"
    if os.path.isdir(holders_dir):
        holders = os.listdir(holders_dir)
        if holders:
            _fail(f"{dev} is in use by: {', '.join(holders)} (LVM/LUKS/RAID)")
    return dev


def format_partition(device, fstype, label=None, keep_uuid=None, rm_fstab_uuid=None):
    dev = check_format_target(device)
    if fstype == "fat16":
        try:
            with open(f"/sys/class/block/{device}/size") as f:
                size_mib = int(f.read()) * 512 // (1024 * 1024)
            if size_mib > FAT16_MAX_MIB:
                _fail(f"FAT16 supports volumes up to {FAT16_MAX_MIB} MiB only "
                      f"(partition is {size_mib} MiB) — use FAT32 or exFAT")
        except OSError:
            pass
    try:
        cmd = build_mkfs_cmd(device, fstype, label, keep_uuid)
    except ValueError as e:
        _fail(str(e))
    if shutil.which(cmd[0]) is None:
        _fail(f"{cmd[0]} is not installed")

    # Запись fstab убираем только после того, как все проверки пройдены
    if rm_fstab_uuid:
        remove_from_fstab(rm_fstab_uuid)

    # Стираем старые сигнатуры, чтобы на разделе не осталось следов двух ФС
    r = subprocess.run(["wipefs", "-a", dev], capture_output=True, text=True)
    if r.returncode != 0:
        _fail(f"wipefs failed: {(r.stderr or r.stdout).strip()}")

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        _fail((r.stderr or r.stdout).strip() or f"{cmd[0]} failed")
    if r.stdout.strip():
        sys.stdout.write(r.stdout.strip() + "\n")

    # Даём udev обновить /dev/disk/by-uuid, чтобы GUI сразу увидел новую ФС
    subprocess.run(["udevadm", "settle"], capture_output=True)
    sys.stdout.write(f"OK: Formatted {dev} as {fstype}\n")


# ── Сетевые диски (SMB/NFS) ────────────────────────────────────────
# Монтируем в настоящую папку через fstab: nofail + _netdev не дают
# повиснуть загрузке, x-systemd.automount подключает при первом обращении
# (NAS может быть выключен). Пароль — только в root-файле, не в fstab.

NET_BASE_OPTS = "nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=15"


def _read_fstab():
    if os.path.exists(FSTAB_PATH):
        with open(FSTAB_PATH) as f:
            return f.read()
    return None


def _restore_fstab(old_content):
    if old_content is not None:
        with open(FSTAB_PATH, 'w') as f:
            f.write(old_content)


def _daemon_reload():
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)


def _fstab_escape(path):
    return path.replace(" ", "\\040")


def _remove_fstab_by_field(value, field):
    """Убирает строки, у которых поле field (0=источник, 1=точка) равно value."""
    if not os.path.exists(FSTAB_PATH):
        return
    esc = _fstab_escape(value)
    with open(FSTAB_PATH) as f:
        lines = f.readlines()
    with open(FSTAB_PATH, 'w') as f:
        for line in lines:
            parts = line.split()
            if parts and not line.strip().startswith("#") \
                    and len(parts) > field and parts[field] == esc:
                continue
            f.write(line)


def _net_validate(server_or_source, mountpoint):
    if any(ch in server_or_source + mountpoint for ch in "\n\t"):
        _fail("Forbidden characters in server or mount point")
    if not mountpoint.startswith("/"):
        _fail("Mount point must be an absolute path")


def _cred_file_for(mountpoint):
    # путь к файлу попадает в опции fstab — пробелы и спецсимволы недопустимы
    name = re.sub(r"[^A-Za-z0-9._-]", "-", mountpoint.strip("/")) or "root"
    return os.path.join(NET_CRED_DIR, f"{name}.cred")


def _net_add_common(source, mountpoint, fstype, options):
    """Общий хвост: запись fstab, проба монтирования, откат при неудаче."""
    old = _read_fstab()
    _remove_fstab_by_field(source, 0)
    _remove_fstab_by_field(mountpoint, 1)
    os.makedirs(mountpoint, exist_ok=True)
    with open(FSTAB_PATH, 'a') as f:
        f.write(f"{_fstab_escape(source)}\t{_fstab_escape(mountpoint)}\t"
                f"{fstype}\t{options}\t0\t0\n")
    _daemon_reload()
    r = subprocess.run(["mount", mountpoint], capture_output=True, text=True)
    if r.returncode != 0:
        _restore_fstab(old)
        cred = _cred_file_for(mountpoint)
        if os.path.exists(cred):
            os.remove(cred)
        _daemon_reload()
        _fail("Mount failed, nothing was saved: " + (r.stderr or r.stdout).strip())
    sys.stdout.write(f"OK: Added and mounted {source} at {mountpoint}\n")


def add_net_smb(server, share, mountpoint, uid, gid,
                user=None, password_file=None, guest=False):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", server):
        _fail(f"Invalid server name: {server!r}")
    _net_validate(share, mountpoint)
    source = f"//{server}/{share}"
    opts = (f"uid={int(uid)},gid={int(gid)},iocharset=utf8,"
            f"file_mode=0664,dir_mode=0775,{NET_BASE_OPTS}")

    if guest:
        opts = "guest," + opts
    else:
        if not user or not password_file:
            _fail("Username and password are required (or use guest access)")
        try:
            with open(password_file) as f:
                password = f.read().rstrip("\n")
        except OSError as e:
            _fail(f"Cannot read password file: {e}")
        finally:
            try:
                os.remove(password_file)
            except OSError:
                pass
        if "\n" in user:
            _fail("Invalid username")
        os.makedirs(NET_CRED_DIR, mode=0o700, exist_ok=True)
        cred = _cred_file_for(mountpoint)
        fd = os.open(cred, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"username={user}\npassword={password}\n")
        opts = f"credentials={cred}," + opts

    _net_add_common(source, mountpoint, "cifs", opts)


def add_net_nfs(source, mountpoint):
    if not re.fullmatch(r"[A-Za-z0-9._-]+:/[^\n\t]*", source):
        _fail(f"NFS source must look like server:/path (got {source!r})")
    _net_validate(source, mountpoint)
    _net_add_common(source, mountpoint, "nfs", NET_BASE_OPTS)


def add_net_ssh(source, mountpoint, uid, gid, key_file):
    """SSHFS: любой Linux-сервер как папка. Для fstab нужен SSH-ключ —
    пароль sshfs умеет спрашивать только интерактивно."""
    if shutil.which("sshfs") is None:
        _fail("sshfs is not installed (needed for SSH drives)")
    if not re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:[^\n\t]*", source):
        _fail(f"SSH source must look like user@server:/path (got {source!r})")
    _net_validate(source, mountpoint)
    if not key_file or not os.path.isfile(key_file):
        _fail(f"SSH key file not found: {key_file!r} — create one with "
              "ssh-keygen and install it: ssh-copy-id user@server")
    if "," in key_file or " " in key_file:
        _fail("SSH key path must not contain spaces or commas")
    opts = (f"allow_other,reconnect,ServerAliveInterval=15,"
            f"IdentityFile={key_file},StrictHostKeyChecking=accept-new,"
            f"uid={int(uid)},gid={int(gid)},{NET_BASE_OPTS}")
    _net_add_common(source, mountpoint, "fuse.sshfs", opts)


def _dav_secrets_remove(url):
    """Убирает строку данного URL из secrets davfs2; возвращает старое содержимое."""
    old = None
    if os.path.exists(DAV_SECRETS):
        with open(DAV_SECRETS) as f:
            old = f.read()
        with open(DAV_SECRETS, 'w') as f:
            for line in old.splitlines(keepends=True):
                if line.split() and line.split()[0] == url:
                    continue
                f.write(line)
    return old


def add_net_dav(url, mountpoint, uid, gid, user, password_file):
    """WebDAV (Nextcloud/ownCloud/облака) через davfs2."""
    if shutil.which("mount.davfs") is None:
        _fail("davfs2 is not installed (needed for WebDAV)")
    if not re.fullmatch(r"https?://[^\s]+", url):
        _fail(f"WebDAV address must start with http(s):// (got {url!r})")
    _net_validate(url, mountpoint)
    if not user or not password_file:
        _fail("Username and password are required for WebDAV")
    try:
        with open(password_file) as f:
            password = f.read().rstrip("\n")
    except OSError as e:
        _fail(f"Cannot read password file: {e}")
    finally:
        try:
            os.remove(password_file)
        except OSError:
            pass
    if '"' in user + password or "\n" in user:
        _fail("Quotes are not allowed in WebDAV username/password")

    # пароль — в root-only secrets самого davfs2, в fstab он не попадает
    os.makedirs(os.path.dirname(DAV_SECRETS), exist_ok=True)
    old_secrets = _dav_secrets_remove(url)
    fd = os.open(DAV_SECRETS, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(f'{url} "{user}" "{password}"\n')
    os.chmod(DAV_SECRETS, 0o600)

    opts = f"uid={int(uid)},gid={int(gid)},{NET_BASE_OPTS}"
    old_fstab = _read_fstab()
    _remove_fstab_by_field(url, 0)
    _remove_fstab_by_field(mountpoint, 1)
    os.makedirs(mountpoint, exist_ok=True)
    with open(FSTAB_PATH, 'a') as f:
        f.write(f"{_fstab_escape(url)}\t{_fstab_escape(mountpoint)}\t"
                f"davfs\t{opts}\t0\t0\n")
    _daemon_reload()
    r = subprocess.run(["mount", mountpoint], capture_output=True, text=True)
    if r.returncode != 0:
        _restore_fstab(old_fstab)
        if old_secrets is not None:
            with open(DAV_SECRETS, 'w') as f:
                f.write(old_secrets)
        elif os.path.exists(DAV_SECRETS):
            os.remove(DAV_SECRETS)
        _daemon_reload()
        _fail("Mount failed, nothing was saved: " + (r.stderr or r.stdout).strip())
    sys.stdout.write(f"OK: Added and mounted {url} at {mountpoint}\n")


def remove_net(mountpoint):
    """Убирает сетевой диск: размонтирует, чистит fstab и файл пароля.
    Данные на сервере не трогаются."""
    esc = _fstab_escape(mountpoint)
    # выключаем automount-юнит, иначе он снова смонтирует при обращении
    unit = subprocess.run(["systemd-escape", "-p", "--suffix=automount", mountpoint],
                          capture_output=True, text=True).stdout.strip()
    if unit:
        subprocess.run(["systemctl", "stop", unit], capture_output=True)
    subprocess.run(["umount", mountpoint], capture_output=True)

    # найдём строку, чтобы удалить и пароль, если он был
    if os.path.exists(FSTAB_PATH):
        with open(FSTAB_PATH) as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[1] == esc \
                        and parts[2] in ("cifs", "nfs", "nfs4", "davfs", "fuse.sshfs"):
                    m = re.search(r"credentials=([^,\s]+)", parts[3])
                    if m and os.path.exists(m.group(1)):
                        os.remove(m.group(1))
                    if parts[2] == "davfs":
                        _dav_secrets_remove(parts[0].replace("\\040", " "))
    _remove_fstab_by_field(mountpoint, 1)
    _daemon_reload()
    sys.stdout.write(f"OK: Removed network drive at {mountpoint}\n")


def mount_path(mountpoint):
    r = subprocess.run(["mount", mountpoint], capture_output=True, text=True)
    if r.returncode != 0:
        _fail((r.stderr or r.stdout).strip() or "mount failed")
    sys.stdout.write(f"OK: Mounted {mountpoint}\n")


# ── Разметка дисков (профи-режим) ──────────────────────────────────

def _run_or_fail(cmd, input_text=None, ok_codes=(0,)):
    r = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
    if r.returncode not in ok_codes:
        _fail((r.stderr or r.stdout).strip() or f"{cmd[0]} failed ({r.returncode})")
    return r


def _settle():
    subprocess.run(["udevadm", "settle"], capture_output=True)


def _check_disk(disk):
    """Диск существует, это блочное устройство типа disk."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", disk):
        _fail(f"Invalid device name: {disk!r}")
    dev = f"/dev/{disk}"
    try:
        st = os.stat(dev)
    except OSError:
        _fail(f"{dev} does not exist")
    if not stat.S_ISBLK(st.st_mode):
        _fail(f"{dev} is not a block device")
    dev_type = subprocess.run(["lsblk", "-ndo", "TYPE", dev],
                              capture_output=True, text=True).stdout.strip()
    # loop разрешён: это образы дисков (и на них же гоняются тесты разметки)
    if dev_type not in ("disk", "loop"):
        _fail(f"{dev} is not a whole disk (type: {dev_type or 'unknown'})")
    # у целого устройства PARTN пуст, у раздела (в т.ч. loop0p1) — номер
    partn = subprocess.run(["lsblk", "-ndo", "PARTN", dev],
                           capture_output=True, text=True).stdout.strip()
    if partn:
        _fail(f"{dev} is a partition, not a whole disk")
    return dev


def _lsblk_json(dev):
    r = _run_or_fail(["lsblk", "-J", "-o", "NAME,TYPE,PARTN,FSTYPE,MOUNTPOINTS", dev])
    return json.loads(r.stdout).get("blockdevices", [])


def _disk_children(disk):
    devices = _lsblk_json(f"/dev/{disk}")
    return devices[0].get("children", []) if devices else []


def _part_node(disk, partnum):
    for child in _disk_children(disk):
        if child.get("partn") == partnum or str(child.get("partn")) == str(partnum):
            return child["name"]
    _fail(f"Partition #{partnum} not found on /dev/{disk}")


def make_table(disk, table):
    """Новая таблица разделов — уничтожает ВСЁ на диске."""
    dev = _check_disk(disk)
    if table not in ("gpt", "dos"):
        _fail(f"Unsupported partition table type: {table} (use gpt or dos)")
    # Ни один раздел диска не должен быть смонтирован/активен
    for child in _disk_children(disk):
        if any(m for m in child.get("mountpoints", []) if m):
            _fail(f"/dev/{child['name']} is mounted — unmount everything on {dev} first")
        check_format_target(child["name"])
    if subprocess.run(["findmnt", "-S", dev], capture_output=True).returncode == 0:
        _fail(f"{dev} is mounted — unmount it first")
    _run_or_fail(["sfdisk", "--wipe", "always", dev], input_text=f"label: {table}\n")
    _settle()
    sys.stdout.write(f"OK: Created {table} partition table on {dev}\n")


def create_partition(disk, start_mib, size_mib, fstype, label=None):
    """Создаёт раздел в свободном месте; данные существующих разделов не трогает."""
    dev = _check_disk(disk)
    start_mib, size_mib = int(start_mib), int(size_mib)
    if size_mib < 1:
        _fail("Partition size must be at least 1 MiB")
    before = {c["name"] for c in _disk_children(disk)}
    _run_or_fail(["sfdisk", "--append", dev],
                 input_text=f"start={start_mib}MiB,size={size_mib}MiB\n")
    _settle()
    new = [c["name"] for c in _disk_children(disk) if c["name"] not in before]
    if len(new) != 1:
        _fail(f"Could not identify the new partition (found: {new})")
    node = new[0]
    sys.stdout.write(f"OK: Created partition /dev/{node}\n")
    if fstype and fstype != "none":
        format_partition(node, fstype, label)


def delete_partition(disk, partnum):
    dev = _check_disk(disk)
    node = _part_node(disk, partnum)
    # Те же проверки, что при форматировании: не смонтирован, не swap, не занят
    check_format_target(node)
    _run_or_fail(["sfdisk", "--delete", dev, str(partnum)])
    _settle()
    sys.stdout.write(f"OK: Deleted partition #{partnum} (/dev/{node}) from {dev}\n")


RESIZE_UNSUPPORTED = ("vfat", "exfat", "f2fs", "xfs")  # xfs растёт только смонтированной, FAT не умеет


def _fsck_ext(part_dev):
    # 0 = чисто, 1 = ошибки исправлены; больше — реальная проблема
    _run_or_fail(["e2fsck", "-f", "-y", part_dev], ok_codes=(0, 1))


def _btrfs_resize(part_dev, size_arg):
    tmp = tempfile.mkdtemp(prefix="eq-resize-")
    try:
        _run_or_fail(["mount", part_dev, tmp])
        try:
            _run_or_fail(["btrfs", "filesystem", "resize", size_arg, tmp])
        finally:
            subprocess.run(["umount", tmp], capture_output=True)
    finally:
        os.rmdir(tmp)


def resize_partition(disk, partnum, new_mib):
    dev = _check_disk(disk)
    node = _part_node(disk, partnum)
    check_format_target(node)
    part_dev = f"/dev/{node}"
    new_mib = int(new_mib)
    if new_mib < 1:
        _fail("New size must be at least 1 MiB")

    fstype = subprocess.run(["lsblk", "-ndo", "FSTYPE", part_dev],
                            capture_output=True, text=True).stdout.strip()
    if fstype in RESIZE_UNSUPPORTED:
        _fail(f"Resizing {fstype} is not supported — copy the data, "
              "recreate the partition and copy back")
    if fstype == "swap":
        _fail("Refusing to resize swap")

    with open(f"/sys/class/block/{node}/size") as f:
        cur_mib = int(f.read()) * 512 // (1024 * 1024)
    if new_mib == cur_mib:
        sys.stdout.write("OK: Size unchanged\n")
        return
    grow = new_mib > cur_mib

    def sfdisk_resize():
        _run_or_fail(["sfdisk", "-N", str(partnum), dev],
                     input_text=f",{new_mib}MiB\n")
        _settle()

    if grow:
        # Сначала раздел, потом файловая система заполняет его целиком
        sfdisk_resize()
        if fstype in ("ext2", "ext3", "ext4"):
            _fsck_ext(part_dev)
            _run_or_fail(["resize2fs", part_dev])
        elif fstype == "ntfs":
            _run_or_fail(["ntfsresize", "-f", part_dev])
        elif fstype == "btrfs":
            _btrfs_resize(part_dev, "max")
        # без ФС — достаточно раздела
    else:
        # Сначала ужимаем файловую систему, только потом раздел
        if fstype in ("ext2", "ext3", "ext4"):
            _fsck_ext(part_dev)
            _run_or_fail(["resize2fs", part_dev, f"{new_mib}M"])
        elif fstype == "ntfs":
            _run_or_fail(["ntfsresize", "-f", "-s",
                          str(new_mib * 1024 * 1024), part_dev])
        elif fstype == "btrfs":
            _btrfs_resize(part_dev, str(new_mib * 1024 * 1024))
        elif fstype:
            _fail(f"Shrinking {fstype} is not supported")
        sfdisk_resize()

    sys.stdout.write(f"OK: Resized {part_dev} to {new_mib} MiB\n")


def _label_and_flags(rest):
    """Выделяет из хвоста аргументов метку и значение --keep-uuid."""
    rest = list(rest)
    keep = None
    if "--keep-uuid" in rest:
        i = rest.index("--keep-uuid")
        if i + 1 >= len(rest):
            _fail("--keep-uuid requires a value")
        keep = rest[i + 1]
        del rest[i:i + 2]
    return (rest[0] if rest else None), keep


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(1)

    cmd = args[0]
    try:
        if cmd == "--rm-fstab" and len(args) == 2:
            remove_from_fstab(args[1])
        elif cmd == "--add-fstab" and len(args) == 5:
            add_to_fstab(args[1], args[2], args[3], args[4])
        elif cmd == "--mount" and len(args) == 3:
            mount_partition(args[1], args[2])
        elif cmd == "--umount" and len(args) == 2:
            umount_partition(args[1])
        elif cmd == "--fix-perms" and len(args) >= 3:
            fix_permissions(args[1], args[2], recursive="--recursive" in args)
        elif cmd == "--set-label" and len(args) == 4:
            set_label(args[1], args[2], args[3])
        elif cmd == "--format" and len(args) >= 3:
            label, keep = _label_and_flags(args[3:])
            format_partition(args[1], args[2], label, keep)
        elif cmd == "--rm-fstab-and-format" and len(args) >= 4:
            # Запись fstab удаляет сам format_partition — после всех проверок,
            # чтобы отказ форматирования не оставил систему без записи
            label, keep = _label_and_flags(args[4:])
            format_partition(args[2], args[3], label, keep, rm_fstab_uuid=args[1])
        elif cmd == "--add-nofail" and len(args) == 2:
            add_nofail_to_fstab(args[1])
        elif cmd == "--mktable" and len(args) == 3:
            make_table(args[1], args[2])
        elif cmd == "--mkpart" and len(args) >= 5:
            create_partition(args[1], args[2], args[3], args[4],
                             args[5] if len(args) >= 6 else None)
        elif cmd == "--rmpart" and len(args) == 3:
            delete_partition(args[1], args[2])
        elif cmd == "--resizepart" and len(args) == 4:
            resize_partition(args[1], args[2], args[3])
        elif cmd == "--add-net-smb" and len(args) >= 4:
            rest = args[4:]
            def flag(name, has_value=True):
                if name in rest:
                    i = rest.index(name)
                    if has_value:
                        if i + 1 >= len(rest):
                            _fail(f"{name} requires a value")
                        return rest[i + 1]
                    return True
                return None
            add_net_smb(args[1], args[2], args[3],
                        flag("--uid") or 1000, flag("--gid") or 1000,
                        user=flag("--user"),
                        password_file=flag("--password-file"),
                        guest=bool(flag("--guest", has_value=False)))
        elif cmd == "--add-net-nfs" and len(args) == 3:
            add_net_nfs(args[1], args[2])
        elif cmd == "--add-net-ssh" and len(args) >= 3:
            rest = args[3:]
            def sflag(name):
                if name in rest:
                    i = rest.index(name)
                    if i + 1 >= len(rest):
                        _fail(f"{name} requires a value")
                    return rest[i + 1]
                return None
            add_net_ssh(args[1], args[2],
                        sflag("--uid") or 1000, sflag("--gid") or 1000,
                        sflag("--key"))
        elif cmd == "--add-net-dav" and len(args) >= 3:
            rest = args[3:]
            def dflag(name):
                if name in rest:
                    i = rest.index(name)
                    if i + 1 >= len(rest):
                        _fail(f"{name} requires a value")
                    return rest[i + 1]
                return None
            add_net_dav(args[1], args[2],
                        dflag("--uid") or 1000, dflag("--gid") or 1000,
                        dflag("--user"), dflag("--password-file"))
        elif cmd == "--rm-net" and len(args) == 2:
            remove_net(args[1])
        elif cmd == "--mount-path" and len(args) == 2:
            mount_path(args[1])
        else:
            sys.stderr.write("Invalid arguments\n")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
