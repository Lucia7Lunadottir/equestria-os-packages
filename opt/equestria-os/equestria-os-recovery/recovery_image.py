"""
Образ восстановления: что внутри ISO (IsoInspector) и что уже установлено
в /var/lib/equestria-recovery (RecoveryState, ImageStatus).

ISO читается через bsdtar, без монтирования — работает и без root.
"""
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field, asdict

from recovery_paths import STATE_DIR, ISO_NAME, STATE_FILE, GRUB_ENTRY_CFG

# Параметры ядра, которые знает только загрузчик самого ISO: их подставляем сами.
_OWN_OPTIONS = ("archisobasedir=", "archisosearchuuid=", "archisolabel=",
                "archisodevice=", "img_dev=", "img_loop=", "img_label=", "img_flags=",
                "copytoram=")
_ISO_NAME = re.compile(r"^equestria-os-(\d{4}\.\d{2}\.\d{2})-x86_64\.iso$")


class IsoError(Exception):
    """ISO не подходит как среда восстановления. args[0] — ключ перевода."""


@dataclass
class IsoInfo:
    version: str
    kernel: str                  # путь внутри ISO, например /arch/boot/x86_64/vmlinuz-linux-lts
    initrds: list = field(default_factory=list)
    options: str = ""            # остальные параметры ядра из loopback.cfg образа
    rootfs_size: int = 0         # airootfs.sfs — столько займёт копия в памяти


class IsoInspector:
    """Проверяет, что файл — live-ISO Equestria OS (archiso), и достаёт параметры загрузки."""

    LOOPBACK_CFG = "boot/grub/loopback.cfg"
    VERSION_FILE = "arch/version"
    ROOTFS = "arch/x86_64/airootfs.sfs"

    def inspect(self, path: str) -> IsoInfo:
        if not os.path.isfile(path):
            raise IsoError("error.iso_missing")
        listing = self._listing(path)
        if self.LOOPBACK_CFG not in listing or self.ROOTFS not in listing:
            raise IsoError("error.iso_not_archiso")
        cfg = self._read(path, self.LOOPBACK_CFG)
        kernel, initrds, options = self._parse_loopback(cfg)
        # В live-меню флешки (UEFI) стоит LTS-ядро — берём его же, если оно есть
        lts_kernel = kernel.replace("vmlinuz-linux", "vmlinuz-linux-lts") if not kernel.endswith("-lts") else kernel
        lts_initrds = [i.replace("initramfs-linux.img", "initramfs-linux-lts.img") for i in initrds]
        lts_main = [i for i in lts_initrds if "initramfs" in i]
        # микрокод тут не учитываем: его в образе может не быть (встроен хуком microcode)
        if lts_kernel.lstrip("/") in listing and lts_main and all(i.lstrip("/") in listing for i in lts_main):
            kernel, initrds = lts_kernel, lts_initrds
        # микрокод может отсутствовать — это не ошибка, просто не передаём его
        initrds = [i for i in initrds if i.lstrip("/") in listing]
        if kernel.lstrip("/") not in listing or not any("initramfs" in i for i in initrds):
            raise IsoError("error.iso_no_kernel")
        version = self._read(path, self.VERSION_FILE).strip() or "?"
        return IsoInfo(version=version, kernel=kernel, initrds=initrds,
                       options=options, rootfs_size=listing.get(self.ROOTFS, 0))

    # ── bsdtar ────────────────────────────────────────────────────────────────

    @staticmethod
    def _listing(path: str) -> dict:
        """{путь внутри ISO: размер}."""
        r = subprocess.run(["bsdtar", "-tvf", path], capture_output=True, text=True)
        if r.returncode != 0:
            raise IsoError("error.iso_unreadable")
        files = {}
        for line in r.stdout.splitlines():
            parts = line.split(None, 8)
            if len(parts) == 9:
                try:
                    files[parts[8].lstrip("./")] = int(parts[4])
                except ValueError:
                    pass
        return files

    @staticmethod
    def _read(path: str, member: str) -> str:
        r = subprocess.run(["bsdtar", "-xOf", path, member], capture_output=True)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""

    @staticmethod
    def _parse_loopback(cfg: str):
        """Первый пункт loopback.cfg: ядро, initrd и «свои» параметры образа."""
        kernel, initrds, options = "", [], []
        for raw in cfg.splitlines():
            line = raw.strip()
            if not kernel and line.startswith("linux "):
                try:
                    tokens = shlex.split(line)[1:]
                except ValueError:
                    tokens = line.split()[1:]
                kernel, rest = tokens[0], tokens[1:]
                options = [t for t in rest if not t.startswith(_OWN_OPTIONS) and "${" not in t]
            elif kernel and not initrds and line.startswith("initrd "):
                initrds = line.split()[1:]
                break
        if not kernel:
            raise IsoError("error.iso_not_archiso")
        return kernel, initrds, " ".join(options)


def version_from_filename(name: str) -> str:
    m = _ISO_NAME.match(os.path.basename(name))
    return m.group(1) if m else ""


@dataclass
class RecoveryState:
    """state.json рядом с установленным ISO (пишет только root-бэкенд)."""
    version: str = ""
    size: int = 0
    md5: str = ""
    source: str = ""            # имя файла на SourceForge или путь, откуда взят
    installed_at: str = ""
    rootfs_size: int = 0
    grub_error: str = ""        # ключ ошибки, если пункт в GRUB добавить не удалось
    iso_dir: str = ""           # папка с образом; "" — /var/lib/equestria-recovery
    auto_fallback: bool = True  # открывать восстановление после неудачных загрузок
    env_file: str = ""          # файл окружения GRUB (разовый переход, счётчик)
    one_shot_ok: bool = False   # GRUB может записать env_file
    auto_ok: bool = False       # счётчик работает (пункты Linux вызывают load_video)

    @property
    def directory(self) -> str:
        return self.iso_dir or STATE_DIR

    @property
    def iso_path(self) -> str:
        return os.path.join(self.directory, ISO_NAME)

    @classmethod
    def load(cls, path: str | None = None) -> "RecoveryState":
        path = path or STATE_FILE
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: str | None = None) -> None:
        path = path or STATE_FILE
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)


def mem_total() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return 0


def copytoram_fits(rootfs_size: int, ram: int | None = None) -> bool:
    """archiso копирует airootfs.sfs в tmpfs размером 75% памяти; сверху нужен запас
    на саму live-среду и ремонт (≈2 ГиБ)."""
    ram = mem_total() if ram is None else ram
    if not rootfs_size or not ram:
        return False
    return rootfs_size <= ram * 0.75 and ram - rootfs_size >= 2 * 1024 ** 3


@dataclass
class ImageStatus:
    """Снимок для окна: что установлено и готово ли к загрузке."""
    present: bool
    state: RecoveryState
    file_size: int
    entry_installed: bool
    ram: int
    location_missing: bool = False   # образ на другом разделе, а тот сейчас не подключён

    @classmethod
    def current(cls) -> "ImageStatus":
        state = RecoveryState.load()
        path = state.iso_path
        present = os.path.isfile(path)
        missing = bool(state.iso_dir) and not present and not os.path.ismount(os.path.dirname(state.iso_dir))
        return cls(
            present=present,
            state=state,
            file_size=os.path.getsize(path) if present else 0,
            entry_installed=os.path.isfile(GRUB_ENTRY_CFG),
            ram=mem_total(),
            location_missing=missing,
        )

    @property
    def ready(self) -> bool:
        return self.present and self.entry_installed and not self.state.grub_error

    @property
    def copies_to_ram(self) -> bool:
        return copytoram_fits(self.state.rootfs_size, self.ram)
