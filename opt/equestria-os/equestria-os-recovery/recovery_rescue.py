"""
Ремонт установленной системы из live-среды (root; окно мастера зовёт через sudo).

  equestria-recovery-rescue scan                       найти установленные системы
  equestria-recovery-rescue fscheck <dev> [--repair]   проверить ФС (раздел не смонтирован)
  equestria-recovery-rescue mount <dev> [--subvol S]   смонтировать в /mnt/equestria-rescue
  equestria-recovery-rescue diagnose                   найти поломки
  equestria-recovery-rescue fix <id> [args…]           исправить (список — FIXES)
  equestria-recovery-rescue umount

Обычные строки stdout — журнал для окна. Результат scan/diagnose — последняя строка
`json <данные>`. Код выхода 0 — успех; ошибка — `error <ключ> [подробности]` в stderr.

Архитектура: каждая проверка — подкласс Check (run → список Problem), каждое
исправление — подкласс Fix (run). Новая проверка/исправление = новый класс
в CHECKS/FIXES, мастер подхватывает их сам.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict

from recovery_paths import (RESCUE_MNT, RESCUE_RUN, RESCUE_STATE, ONE_SHOT_VAR, FAILS_VAR,
                            STATE_FILE, GRUB_DIR, ENV_NAME, ESP_ENV_DIR)

ROOT_FS = ("ext4", "btrfs", "xfs", "f2fs")
SEPARATE_MOUNTS = ("/boot", "/boot/efi", "/efi", "/usr", "/var")
GIB = 1024 ** 3
MIB = 1024 ** 2


class RescueError(Exception):
    """args[0] — ключ перевода."""


# ── процессы ──────────────────────────────────────────────────────────────────

def log(*parts) -> None:
    print(*parts, flush=True)


def run(*cmd, check=False) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RescueError("error.command", " ".join(cmd), r.stderr.strip())
    return r


def stream(*cmd) -> int:
    """Запустить и пересылать вывод в журнал построчно."""
    log("$", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", bufsize=1)
    for line in proc.stdout:
        log(line.rstrip("\n"))
    return proc.wait()


def chroot(*cmd) -> int:
    return stream("arch-chroot", RESCUE_MNT, *cmd)


def chroot_capture(*cmd) -> subprocess.CompletedProcess:
    return run("arch-chroot", RESCUE_MNT, *cmd)


# ── блочные устройства ────────────────────────────────────────────────────────

def block_devices() -> list:
    r = run("lsblk", "-J", "-b", "-o", "NAME,PATH,FSTYPE,UUID,LABEL,SIZE,TYPE,MOUNTPOINTS,PKNAME")
    try:
        tree = json.loads(r.stdout)["blockdevices"]
    except (ValueError, KeyError):
        return []
    flat = []

    def walk(nodes):
        for n in nodes:
            flat.append(n)
            walk(n.get("children") or [])
    walk(tree)
    return flat


def mountpoints_of(dev: dict) -> list:
    return [m for m in (dev.get("mountpoints") or []) if m]


def live_medium_source() -> str:
    """Раздел флешки, с которой запущена live-среда (его не предлагаем)."""
    r = run("findmnt", "-n", "-o", "SOURCE", "/run/archiso/bootmnt")
    return r.stdout.strip()


def parse_fstab(text: str) -> list:
    entries = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        parts = line.split()
        if len(parts) >= 4:
            entries.append({"spec": parts[0], "mp": parts[1], "fstype": parts[2], "opts": parts[3]})
    return entries


def subvol_of(opts: str) -> str:
    for opt in opts.split(","):
        if opt.startswith("subvol="):
            return opt.split("=", 1)[1].lstrip("/")
    return ""


def resolve_spec(spec: str) -> str:
    """UUID=… / LABEL=… / PARTUUID=… → /dev/…"""
    if "=" in spec and not spec.startswith("/"):
        key, value = spec.split("=", 1)
        r = run("blkid", "-o", "device", "-t", f"{key}={value.strip(chr(34))}")
        return r.stdout.split("\n")[0].strip()
    return spec


# ── поиск систем ──────────────────────────────────────────────────────────────

@dataclass
class InstalledSystem:
    device: str
    fstype: str
    uuid: str
    size: int
    subvol: str = ""
    name: str = ""
    busy: bool = False        # раздел держит live-среда (образ запущен с него без copytoram)

    @property
    def title(self) -> str:
        return self.name or "Linux"


class SystemScanner:
    PROBE = os.path.join(RESCUE_RUN, "probe")

    def scan(self) -> list:
        skip = live_medium_source()
        found = []
        for dev in block_devices():
            if dev.get("type") not in ("part", "disk", "lvm", "crypt") or dev.get("fstype") not in ROOT_FS:
                continue
            if dev.get("path") == skip:
                continue
            try:
                found.extend(self._probe(dev))
            except (OSError, RescueError) as e:
                log("scan:", dev.get("path"), e)
        return found

    def _probe(self, dev: dict) -> list:
        mounted = mountpoints_of(dev)
        busy = any(m.startswith("/run/archiso") for m in mounted)
        if mounted and dev["fstype"] != "btrfs":
            return self._look(dev, mounted[0], busy)
        os.makedirs(self.PROBE, exist_ok=True)
        opts = "ro,subvolid=5" if dev["fstype"] == "btrfs" else "ro"
        if run("mount", "-o", opts, dev["path"], self.PROBE).returncode != 0:
            return []
        try:
            return self._look(dev, self.PROBE, busy)
        finally:
            run("umount", self.PROBE)

    def _look(self, dev: dict, top: str, busy: bool) -> list:
        candidates = [""]
        if dev["fstype"] == "btrfs":
            candidates += sorted(d for d in os.listdir(top)
                                 if not d.startswith(".") and os.path.isdir(os.path.join(top, d)))
        out = []
        for sub in candidates:
            root = os.path.join(top, sub)
            if not os.path.isfile(os.path.join(root, "etc/fstab")) or \
               not os.path.isdir(os.path.join(root, "usr/lib/modules")):
                continue
            fstab = parse_fstab(_read(os.path.join(root, "etc/fstab")))
            root_entry = next((e for e in fstab if e["mp"] == "/"), None)
            if dev["fstype"] == "btrfs" and sub:
                # снимки (save-point, timeshift) — копии системы; настоящий корень тот,
                # чей fstab монтирует «/» именно из этого подтома
                if not root_entry or subvol_of(root_entry["opts"]) != sub:
                    continue
            out.append(InstalledSystem(
                device=dev["path"], fstype=dev["fstype"], uuid=dev.get("uuid") or "",
                size=int(dev.get("size") or 0), subvol=sub, busy=busy,
                name=_os_name(root)))
        return out


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _os_name(root: str) -> str:
    for line in _read(os.path.join(root, "etc/os-release")).splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


# ── монтирование ──────────────────────────────────────────────────────────────

@dataclass
class TargetState:
    device: str = ""
    fstype: str = ""
    subvol: str = ""
    remounted: str = ""                       # точка live-среды, переведённая в rw
    mounted: list = field(default_factory=list)
    failed: list = field(default_factory=list)  # точки из fstab, которые не смонтировались
    esp: str = ""                              # где в системе EFI-раздел (/boot/efi, /efi, /boot)

    @classmethod
    def load(cls) -> "TargetState":
        try:
            with open(RESCUE_STATE, encoding="utf-8") as f:
                return cls(**json.load(f))
        except (OSError, ValueError, TypeError):
            raise RescueError("error.not_mounted")

    def save(self) -> None:
        os.makedirs(RESCUE_RUN, exist_ok=True)
        with open(RESCUE_STATE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f)


class TargetMount:
    def mount(self, device: str, subvol: str) -> TargetState:
        if os.path.ismount(RESCUE_MNT):
            self.umount()
        fstype = run("blkid", "-o", "value", "-s", "TYPE", device).stdout.strip()
        state = TargetState(device=device, fstype=fstype, subvol=subvol)
        # Live-среда без copytoram держит этот раздел только на чтение (там лежит ISO).
        # Переводим её точку в rw — иначе ext4 не даст смонтировать раздел второй раз на запись.
        for m in self._mounts_of(device):
            if m.startswith("/run/archiso"):
                if run("mount", "-o", "remount,rw", m).returncode == 0:
                    state.remounted = m
                    log("remount rw:", m)
        os.makedirs(RESCUE_MNT, exist_ok=True)
        opts = ["rw"] + ([f"subvol={subvol}"] if subvol else [])
        r = run("mount", "-o", ",".join(opts), device, RESCUE_MNT)
        if r.returncode != 0:
            raise RescueError("error.mount_root", r.stderr.strip())
        state.mounted.append("/")
        log("mount", device, "→", RESCUE_MNT)

        fstab = parse_fstab(_read(os.path.join(RESCUE_MNT, "etc/fstab")))
        for e in sorted((e for e in fstab if e["mp"] in SEPARATE_MOUNTS), key=lambda e: e["mp"].count("/")):
            if "noauto" in e["opts"].split(","):
                continue
            src = resolve_spec(e["spec"])
            target = RESCUE_MNT + e["mp"]
            keep = [o for o in e["opts"].split(",") if not o.startswith("x-") and o not in ("defaults", "nofail")]
            os.makedirs(target, exist_ok=True)
            cmd = ["mount", "-t", e["fstype"]] + (["-o", ",".join(keep)] if keep else []) + [src or e["spec"], target]
            if src and run(*cmd).returncode == 0:
                state.mounted.append(e["mp"])
                log("mount", src, "→", target)
            else:
                state.failed.append(e["mp"])
                log("mount failed:", e["spec"], e["mp"])
            if e["fstype"] == "vfat" and e["mp"] in ("/boot/efi", "/efi", "/boot"):
                state.esp = e["mp"]
        state.save()
        clear_one_shot()
        return state

    @staticmethod
    def _mounts_of(device: str) -> list:
        r = run("findmnt", "-n", "-o", "TARGET", "-S", device)
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]

    def umount(self) -> None:
        try:
            state = TargetState.load()
        except RescueError:
            state = None
        run("sync")
        if os.path.ismount(RESCUE_MNT):
            r = run("umount", "-R", RESCUE_MNT)
            if r.returncode != 0:
                raise RescueError("error.umount", r.stderr.strip())
        if state and state.remounted:
            run("mount", "-o", "remount,ro", state.remounted)
        try:
            os.remove(RESCUE_STATE)
        except FileNotFoundError:
            pass


def clear_one_shot() -> None:
    """Систему чинят — значит, разовый переход уже не нужен, а счёт неудачных загрузок
    начинается заново (GRUB сам это делает, но если он не смог записать файл — делаем мы).
    Файл окружения — в /boot/grub или на EFI-разделе (см. recovery_storage.env_location)."""
    if not shutil.which("grub-editenv"):
        return
    candidates = [os.path.join(GRUB_DIR, ENV_NAME)]
    for esp in ("boot/efi", "efi", "boot"):
        candidates.append(os.path.join("/", esp, ESP_ENV_DIR, ENV_NAME))
    try:
        with open(os.path.join(RESCUE_MNT, STATE_FILE.lstrip("/")), encoding="utf-8") as f:
            recorded = json.load(f).get("env_file") or ""
        if recorded:
            candidates.insert(0, recorded)
    except (OSError, ValueError, AttributeError):
        pass
    for rel in dict.fromkeys(candidates):
        env = os.path.join(RESCUE_MNT, rel.lstrip("/"))
        if not os.path.isfile(env):
            continue
        listed = [ln.split("=", 1)[0] for ln in run("grub-editenv", env, "list").stdout.splitlines()]
        present = [v for v in (ONE_SHOT_VAR, FAILS_VAR) if v in listed]
        if present:
            run("grub-editenv", env, "unset", *present)
            log("grub env:", ", ".join(present), "cleared in", rel)


# ── проверки ──────────────────────────────────────────────────────────────────

@dataclass
class Problem:
    key: str                         # problem.<…> — текст в окне
    severity: str = "error"          # error | warning
    args: list = field(default_factory=list)
    fix: str = ""                    # id из FIXES, "" — исправить автоматически нельзя
    fix_args: list = field(default_factory=list)


class Check:
    id = ""

    def run(self, state: TargetState) -> list:
        raise NotImplementedError


def target(*parts) -> str:
    return os.path.join(RESCUE_MNT, *[p.lstrip("/") for p in parts])


def installed_kernels() -> list:
    """[(pkgbase, версия модулей)] по /usr/lib/modules/*/pkgbase."""
    out = []
    for pkgbase_file in sorted(glob.glob(target("usr/lib/modules/*/pkgbase"))):
        out.append((_read(pkgbase_file).strip(), os.path.basename(os.path.dirname(pkgbase_file))))
    return [(p, v) for p, v in out if p]


class MountCheck(Check):
    id = "mounts"

    def run(self, state):
        return [Problem("problem.mount_failed", args=[mp]) for mp in state.failed]


class FreeSpaceCheck(Check):
    id = "space"

    def run(self, state):
        out = []
        root = os.statvfs(RESCUE_MNT)
        free_root = root.f_bavail * root.f_frsize
        if free_root < 2 * GIB:
            out.append(Problem("problem.root_full", args=[_gib(free_root)], fix="clean-cache"))
        boot = target("boot")
        if "/boot" in state.mounted and os.path.isdir(boot):
            b = os.statvfs(boot)
            free_boot = b.f_bavail * b.f_frsize
            if free_boot < 150 * MIB:
                fix = "remove-fallback" if glob.glob(target("boot/initramfs-*-fallback.img")) else ""
                out.append(Problem("problem.boot_full", args=[f"{free_boot // MIB}"], fix=fix))
        return out


class PacmanLockCheck(Check):
    id = "pacman-lock"

    def run(self, state):
        if os.path.exists(target("var/lib/pacman/db.lck")):
            return [Problem("problem.pacman_lock", fix="unlock")]
        return []


class KernelCheck(Check):
    """Ядро и initramfs в /boot — ровно то, что сломалось при переполненном /tmp."""
    id = "kernel"

    def run(self, state):
        kernels = installed_kernels()
        if not kernels:
            return [Problem("problem.no_kernel", fix="finish-update")]
        out = []
        for pkgbase, ver in kernels:
            mod_dir = target("usr/lib/modules", ver)
            image = target("boot", f"vmlinuz-{pkgbase}")
            src = os.path.join(mod_dir, "vmlinuz")
            if not os.path.isfile(image):
                out.append(Problem("problem.kernel_missing", args=[pkgbase], fix="rebuild-boot"))
            elif os.path.isfile(src) and not _same_file(src, image):
                out.append(Problem("problem.kernel_mismatch", args=[pkgbase], fix="rebuild-boot"))
            if not os.path.isfile(os.path.join(mod_dir, "modules.dep")):
                out.append(Problem("problem.modules_broken", args=[pkgbase, ver], fix="rebuild-boot"))
            initrd = target("boot", f"initramfs-{pkgbase}.img")
            if not os.path.isfile(initrd) or os.path.getsize(initrd) < MIB:
                out.append(Problem("problem.initramfs_missing", args=[pkgbase], fix="rebuild-boot"))
            elif shutil.which("lsinitcpio") and run("lsinitcpio", "-a", initrd).returncode != 0:
                out.append(Problem("problem.initramfs_broken", args=[pkgbase], fix="rebuild-boot"))
        return out


class PackageFilesCheck(Check):
    """Пакеты с пропавшими файлами (обновление оборвалось на середине)."""
    id = "packages"
    IGNORE = ("/usr/share/doc/", "/usr/share/man/", "/usr/share/info/", "/usr/share/locale/",
              "/usr/share/help/", "/usr/share/gtk-doc/")

    def run(self, state):
        out = []
        if os.path.exists(target("var/lib/pacman/db.lck")):
            return out  # pacman откажется работать; сначала снимем блокировку
        r = chroot_capture("pacman", "-Qk")
        broken = set()
        for line in (r.stdout + r.stderr).splitlines():
            m = re.match(r"^warning: (\S+): (/\S+) \(", line)
            if m and not m.group(2).startswith(self.IGNORE):
                broken.add(m.group(1))
        foreign = set(chroot_capture("pacman", "-Qmq").stdout.split())
        repo = sorted(broken - foreign)
        if repo:
            out.append(Problem("problem.files_missing", args=[len(repo), ", ".join(repo[:10])],
                               fix="reinstall", fix_args=repo))
        if broken & foreign:
            out.append(Problem("problem.foreign_broken", severity="warning",
                               args=[", ".join(sorted(broken & foreign)[:10])]))
        db = chroot_capture("pacman", "-Dk")
        if db.returncode != 0:
            lines = (db.stdout + db.stderr).strip().splitlines()
            out.append(Problem("problem.pacman_db", severity="warning",
                               args=[lines[-1] if lines else ""]))
        return out


class BootloaderCheck(Check):
    id = "bootloader"

    def run(self, state):
        if not glob.glob(target("var/lib/pacman/local/grub-[0-9]*")):
            return []  # не GRUB (systemd-boot и т.п.) — тут не чиним
        out = []
        cfg = target("boot/grub/grub.cfg")
        if not os.path.isfile(cfg) or os.path.getsize(cfg) == 0:
            out.append(Problem("problem.grub_cfg", fix="repair-grub"))
        if os.path.isdir("/sys/firmware/efi"):
            if not state.esp:
                out.append(Problem("problem.no_esp", severity="warning"))
            elif not glob.glob(target(state.esp, "EFI/*/grubx64.efi")) and \
                    not os.path.isfile(target(state.esp, "EFI/BOOT/BOOTX64.EFI")):
                out.append(Problem("problem.grub_efi", fix="repair-grub"))
        return out


CHECKS = (MountCheck(), FreeSpaceCheck(), PacmanLockCheck(), KernelCheck(),
          BootloaderCheck(), PackageFilesCheck())


def _same_file(a: str, b: str) -> bool:
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(MIB), fb.read(MIB)
            if x != y:
                return False
            if not x:
                return True


def _gib(n: int) -> str:
    return f"{n / GIB:.1f}"


# ── исправления ───────────────────────────────────────────────────────────────

class Fix:
    id = ""
    needs_network = False

    def run(self, state: TargetState, args: list) -> int:
        raise NotImplementedError


class UnlockFix(Fix):
    id = "unlock"

    def run(self, state, args):
        os.remove(target("var/lib/pacman/db.lck"))
        log("removed /var/lib/pacman/db.lck")
        return 0


class CleanCacheFix(Fix):
    """Удаляет из кэша pacman пакеты, которые сейчас не установлены (pacman -Sc)."""
    id = "clean-cache"

    def run(self, state, args):
        return chroot("pacman", "-Sc", "--noconfirm")


class RemoveFallbackFix(Fix):
    id = "remove-fallback"

    def run(self, state, args):
        for path in glob.glob(target("boot/initramfs-*-fallback.img")):
            os.remove(path)
            log("removed", path[len(RESCUE_MNT):])
        return 0


class RebuildBootFix(Fix):
    """Заново кладёт ядра в /boot и пересобирает все initramfs."""
    id = "rebuild-boot"

    def run(self, state, args):
        if "/boot" in state.failed:
            log("/boot is not mounted")
            return 1
        rc = 0
        for pkgbase, ver in installed_kernels():
            mod_dir = target("usr/lib/modules", ver)
            if not os.path.isfile(os.path.join(mod_dir, "modules.dep")):
                rc |= chroot("depmod", ver)
            src = os.path.join(mod_dir, "vmlinuz")
            if os.path.isfile(src):
                # без reflink/дыр: на Btrfs GRUB недочитывал «дырявое» ядро
                rc |= stream("cp", "--reflink=never", "--sparse=never", src,
                             target("boot", f"vmlinuz-{pkgbase}"))
        rc |= chroot("mkinitcpio", "-P")
        run("sync")
        return rc


class ReinstallFix(Fix):
    """Доустанавливает пакеты с пропавшими файлами (вместе с полным обновлением —
    частичные обновления в Arch ломают систему)."""
    id = "reinstall"
    needs_network = True

    def run(self, state, args):
        if not args:
            return 0
        return chroot("pacman", "-Syu", "--noconfirm", *args)


class FinishUpdateFix(Fix):
    id = "finish-update"
    needs_network = True

    def run(self, state, args):
        return chroot("pacman", "-Syu", "--noconfirm")


class RepairGrubFix(Fix):
    id = "repair-grub"

    def run(self, state, args):
        rc = 0
        if os.path.isdir("/sys/firmware/efi"):
            if not state.esp:
                log("EFI partition not found in /etc/fstab")
                return 1
            esp = state.esp
            ids = [os.path.basename(os.path.dirname(p))
                   for p in glob.glob(target(esp, "EFI/*/grubx64.efi"))
                   if os.path.basename(os.path.dirname(p)).upper() != "BOOT"]
            boot_id = ids[0] if ids else "Equestria"
            rc |= chroot("grub-install", "--target=x86_64-efi", f"--efi-directory={esp}",
                         f"--bootloader-id={boot_id}", "--recheck")
            fallback = target(esp, "EFI/BOOT/BOOTX64.EFI")
            if not os.path.isfile(fallback) or b"GRUB" in _head(fallback):
                # запасной путь EFI/BOOT — для прошивок, которые теряют записи NVRAM
                rc |= chroot("grub-install", "--target=x86_64-efi", f"--efi-directory={esp}",
                             "--removable", "--recheck")
        else:
            boot_src = run("findmnt", "-n", "-o", "SOURCE", target("boot")).stdout.strip() or state.device
            disk = run("lsblk", "-n", "-o", "PKNAME", boot_src).stdout.strip().split("\n")[0]
            if not disk:
                log("disk of", boot_src, "not found")
                return 1
            rc |= chroot("grub-install", "--target=i386-pc", "--recheck", f"/dev/{disk}")
        rc |= chroot("grub-mkconfig", "-o", "/boot/grub/grub.cfg")
        run("sync")
        return rc


class BtrfsScrubFix(Fix):
    id = "btrfs-scrub"

    def run(self, state, args):
        return stream("btrfs", "scrub", "start", "-B", RESCUE_MNT)


def _head(path: str, size: int = 4 * MIB) -> bytes:
    with open(path, "rb") as f:
        return f.read(size)


FIXES = {f.id: f for f in (UnlockFix(), CleanCacheFix(), RemoveFallbackFix(), RebuildBootFix(),
                           ReinstallFix(), FinishUpdateFix(), RepairGrubFix(), BtrfsScrubFix())}


# ── проверка файловой системы (до монтирования) ──────────────────────────────

class FilesystemChecker:
    """Возврат: 0 — ошибок нет, 1 — ошибки исправлены, 4 — найдены ошибки (нужен --repair)."""

    def check(self, device: str, repair: bool) -> int:
        fstype = run("blkid", "-o", "value", "-s", "TYPE", device).stdout.strip()
        if run("findmnt", "-n", "-S", device).stdout.strip():
            raise RescueError("error.fs_busy")
        if fstype in ("ext2", "ext3", "ext4"):
            rc = stream("e2fsck", "-f", "-y" if repair else "-n", device)
            return 0 if rc == 0 else (1 if rc in (1, 2) and repair else 4)
        if fstype == "btrfs":
            # автоматический ремонт Btrfs опасен — только проверка
            return 0 if stream("btrfs", "check", "--readonly", device) == 0 else 4
        if fstype == "xfs":
            rc = stream("xfs_repair", *([] if repair else ["-n"]), device)
            return 0 if rc == 0 else (1 if repair else 4)
        if fstype == "f2fs":
            rc = stream("fsck.f2fs", "-f" if repair else "--dry-run", device)
            return 0 if rc == 0 else (1 if repair else 4)
        raise RescueError("error.fs_unsupported", fstype)


# ── командная строка ──────────────────────────────────────────────────────────

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="equestria-recovery-rescue")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    fs = sub.add_parser("fscheck")
    fs.add_argument("device")
    fs.add_argument("--repair", action="store_true")
    m = sub.add_parser("mount")
    m.add_argument("device")
    m.add_argument("--subvol", default="")
    sub.add_parser("diagnose")
    f = sub.add_parser("fix")
    f.add_argument("id", choices=sorted(FIXES))
    f.add_argument("args", nargs="*")
    sub.add_parser("umount")
    a = p.parse_args(argv)

    if os.geteuid() != 0:
        print("error error.not_root", file=sys.stderr)
        return 2
    try:
        if a.cmd == "scan":
            log("json", json.dumps([asdict(s) for s in SystemScanner().scan()]))
        elif a.cmd == "fscheck":
            return FilesystemChecker().check(a.device, a.repair)
        elif a.cmd == "mount":
            log("json", json.dumps(asdict(TargetMount().mount(a.device, a.subvol))))
        elif a.cmd == "diagnose":
            state = TargetState.load()
            problems = []
            for check in CHECKS:
                log("check:", check.id)
                try:
                    problems += check.run(state)
                except OSError as e:
                    log("check failed:", check.id, e)
            log("json", json.dumps([asdict(pr) for pr in problems]))
        elif a.cmd == "fix":
            return 0 if FIXES[a.id].run(TargetState.load(), a.args) == 0 else 3
        elif a.cmd == "umount":
            TargetMount().umount()
    except RescueError as e:
        print("error", *e.args, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
