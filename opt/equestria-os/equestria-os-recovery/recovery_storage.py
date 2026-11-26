"""
Где что лежит на дисках установленной системы.

* StorageLocation / StorageLocations — куда можно положить ISO: системный раздел
  (/var/lib/equestria-recovery) или другой раздел из fstab, лучше на другом диске.
  Тогда повреждение системного раздела не мешает загрузить среду восстановления,
  а в режиме «мало памяти» системный раздел остаётся свободным для fsck.
* env_location() — куда положить файл окружения GRUB (разовый переход и счётчик
  неудачных загрузок): GRUB пишет только на ext2/3/4 и FAT без LUKS/LVM/RAID.

Всё здесь работает без root (findmnt, lsblk, statvfs): окно показывает варианты, а
бэкенд от root проверяет выбранный вариант тем же кодом.
"""
import json
import os
import subprocess
from dataclasses import dataclass

from recovery_paths import (
    STATE_DIR, ISO_NAME, OTHER_DIR_NAME, ISO_FS, GRUB_DIR, ENV_NAME, ESP_ENV_DIR,
)

# Точки, куда образ класть нельзя или бессмысленно
_EXCLUDED_TARGETS = ("/boot", "/boot/efi", "/efi", "/tmp", "/var/tmp", "/var/cache",
                     "/var/log", "/swap")
# Слои, которые не прочитает initramfs образа (у archiso нет хуков lvm2/encrypt/mdadm)
_LAYERED_SOURCES = ("/dev/mapper/", "/dev/md", "/dev/dm-")
_GRUB_WRITABLE = {"ext2": "ext2", "ext3": "ext2", "ext4": "ext2", "vfat": "fat"}


def _run(*cmd) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return ""
    return r.stdout if r.returncode == 0 else ""


def _findmnt_json(*args) -> list:
    out = _run("findmnt", "-J", "-l", *args)
    try:
        return json.loads(out).get("filesystems", []) if out else []
    except ValueError:
        return []


def _clean_source(source: str) -> str:
    """/dev/nvme1n1p2[/@data] → /dev/nvme1n1p2 (findmnt так пишет подтома Btrfs)."""
    return (source or "").split("[", 1)[0]


def mount_of(path: str) -> dict:
    """Точка монтирования, на которой лежит path: target, source, fstype, uuid."""
    rows = _findmnt_json("-o", "TARGET,SOURCE,FSTYPE,UUID", "-T", path)
    if not rows:
        return {}
    row = rows[0]
    row["source"] = _clean_source(row.get("source", ""))
    return row


def parent_disk(device: str) -> str:
    return _run("lsblk", "-ndo", "PKNAME", device).strip() or os.path.basename(device)


def free_bytes(path: str) -> int:
    try:
        st = os.statvfs(path)
    except OSError:
        return 0
    return st.f_bavail * st.f_frsize


# ── место для ISO ─────────────────────────────────────────────────────────────

@dataclass
class StorageLocation:
    key: str            # "default" или точка монтирования другого раздела
    mount: str          # точка монтирования
    directory: str      # папка с образом
    device: str
    uuid: str
    fstype: str
    free: int
    system: bool        # тот же раздел, что и система
    other_disk: bool    # другой физический диск

    @property
    def iso_path(self) -> str:
        return os.path.join(self.directory, ISO_NAME)


class StorageLocations:
    """Список мест, куда можно положить ISO. Первый элемент — системный раздел."""

    def __init__(self):
        self._root = mount_of("/")
        self._root_disk = parent_disk(self._root["source"]) if self._root.get("source") else ""

    def default(self) -> StorageLocation | None:
        m = mount_of(STATE_DIR if os.path.isdir(STATE_DIR) else "/var/lib")
        if not m:
            return None
        return StorageLocation(
            key="default", mount=m.get("target", "/"), directory=STATE_DIR,
            device=m.get("source", ""), uuid=m.get("uuid") or "", fstype=m.get("fstype", ""),
            free=free_bytes(m.get("target", "/")), system=True,
            other_disk=bool(self._root_disk) and parent_disk(m.get("source", "")) != self._root_disk)

    def all(self) -> list:
        out = []
        default = self.default()
        if default:
            out.append(default)
        seen = {default.uuid} if default and default.uuid else set()
        seen.add(self._root.get("uuid") or "")
        mounted = {row.get("target"): row for row in _findmnt_json("-o", "TARGET,SOURCE,FSTYPE,UUID")}
        for entry in _findmnt_json("--fstab", "-o", "TARGET,OPTIONS"):
            target = entry.get("target") or ""
            opts = (entry.get("options") or "").split(",")
            if not target.startswith("/") or target == "/" or target in _EXCLUDED_TARGETS \
                    or "noauto" in opts:
                continue
            row = mounted.get(target)
            if not row:
                continue                        # из fstab, но сейчас не подключён
            source = _clean_source(row.get("source", ""))
            uuid = row.get("uuid") or ""
            if row.get("fstype") not in ISO_FS or not source.startswith("/dev/") \
                    or source.startswith(_LAYERED_SOURCES) or not uuid or uuid in seen:
                continue
            seen.add(uuid)
            out.append(StorageLocation(
                key=target, mount=target, directory=os.path.join(target, OTHER_DIR_NAME),
                device=source, uuid=uuid, fstype=row.get("fstype", ""), free=free_bytes(target),
                system=False, other_disk=bool(self._root_disk) and parent_disk(source) != self._root_disk))
        return out

    def find(self, key: str) -> StorageLocation | None:
        return next((loc for loc in self.all() if loc.key == key), None)

    @staticmethod
    def key_for_dir(directory: str) -> str:
        if not directory or os.path.normpath(directory) == STATE_DIR:
            return "default"
        return os.path.dirname(os.path.normpath(directory))


# ── окружение GRUB ────────────────────────────────────────────────────────────

def grub_can_write(path: str) -> bool:
    """Сможет ли GRUB записать файл окружения на раздел, где лежит path."""
    m = mount_of(path)
    if not m:
        return False
    source = m.get("source", "")
    return m.get("fstype") in _GRUB_WRITABLE and not source.startswith(_LAYERED_SOURCES)


def esp_mount() -> str:
    """Где смонтирован EFI-раздел (FAT): /boot/efi, /efi или /boot."""
    for target in ("/boot/efi", "/efi", "/boot"):
        if os.path.ismount(target) and mount_of(target).get("fstype") == "vfat":
            return target
    return ""


def env_location() -> str:
    """Путь файла окружения в системе или "" — тогда ни разовый переход, ни
    автозапуск восстановления невозможны."""
    if os.path.isdir(GRUB_DIR) and grub_can_write(GRUB_DIR):
        return os.path.join(GRUB_DIR, ENV_NAME)
    esp = esp_mount()
    if esp and grub_can_write(esp):
        return os.path.join(esp, ESP_ENV_DIR, ENV_NAME)
    return ""
