"""
Один источник путей и имён для всех частей Equestria OS Recovery:
окна в установленной системе, root-бэкенда, GRUB-скрипта и мастера в live-среде.
"""
import os

# ── Установленная система: где хранится образ ─────────────────────────────────
STATE_DIR = "/var/lib/equestria-recovery"
ISO_NAME = "equestria-recovery.iso"
ISO_PATH = os.path.join(STATE_DIR, ISO_NAME)      # место по умолчанию (системный раздел)
STATE_FILE = os.path.join(STATE_DIR, "state.json")
# Образ можно держать на другом разделе (другом диске): тогда повреждение системного
# раздела не мешает загрузить среду. Там он лежит в скрытой папке, принадлежащей root.
OTHER_DIR_NAME = ".equestria-recovery"
# Файловые системы, с которых и GRUB, и initramfs образа (archiso_loop_mnt) умеют читать ISO
# (FAT не годится: файл больше 4 ГиБ)
ISO_FS = ("ext2", "ext3", "ext4", "btrfs", "xfs")

# ── GRUB ──────────────────────────────────────────────────────────────────────
GRUB_DIR = "/boot/grub"
GRUB_CFG = os.path.join(GRUB_DIR, "grub.cfg")
GRUB_ENV = os.path.join(GRUB_DIR, "grubenv")
# Пункты меню живут в отдельном файле: при обновлении ISO переписываем только его,
# grub.cfg (и её меню) не пересобираем.
GRUB_ENTRY_CFG = os.path.join(GRUB_DIR, "equestria-recovery.cfg")
GRUB_BLOCK_BEGIN = "### BEGIN equestria-recovery ###"
GRUB_BLOCK_END = "### END equestria-recovery ###"
# Своё окружение GRUB (как grubenv, но только наше): разовый переход и счётчик неудачных
# загрузок. GRUB умеет писать только на ext2/3/4 и FAT без LUKS/LVM/RAID, поэтому файл лежит
# в /boot/grub, а если там нельзя (Btrfs, XFS…) — на EFI-разделе.
ENV_NAME = "equestria-recovery.env"
ESP_ENV_DIR = "EFI/equestria-recovery"
ONE_SHOT_VAR = "equestria_recovery_once"
FAILS_VAR = "eqrec_fails"        # сколько раз подряд обычная загрузка не дошла до конца
LIMIT_VAR = "eqrec_limit"        # после скольких неудач открывать восстановление (0 — никогда)
# Как в Windows: после двух неудачных загрузок подряд. Если save-point сам откатывает
# систему на третьей (Btrfs), даём ему эту попытку и ещё одну загрузку после отката.
FAIL_LIMIT = 2
FAIL_LIMIT_WITH_SAVE_POINT = 4
ENTRY_ID = "equestria-recovery"
ENTRY_ID_NORAM = "equestria-recovery-noram"

# ── Флаг в командной строке ядра: «загружены из пункта восстановления» ────────
CMDLINE_FLAG = "equestria.recovery=1"
REASON_ARG = "equestria.recovery_reason="     # auto — открыли сами после неудачных загрузок

# ── Откуда качать ─────────────────────────────────────────────────────────────
FEED_URL = "https://sourceforge.net/projects/equestria-os/rss?path=/"
DOWNLOAD_URL = "https://downloads.sourceforge.net/project/equestria-os/{name}"

# ── Live-среда: куда монтируется ремонтируемая система ───────────────────────
RESCUE_MNT = "/mnt/equestria-rescue"
RESCUE_RUN = "/run/equestria-rescue"
RESCUE_STATE = os.path.join(RESCUE_RUN, "target.json")

APP_ID = "equestria-os-recovery"
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def is_live() -> bool:
    """Запущены из live-образа archiso (флешка или пункт восстановления)."""
    return os.path.isdir("/run/archiso")


def booted_for_recovery() -> bool:
    """Загрузились именно через пункт «Восстановление» в GRUB."""
    try:
        with open("/proc/cmdline", encoding="utf-8") as f:
            return CMDLINE_FLAG in f.read().split()
    except OSError:
        return False


def recovery_reason() -> str:
    """Почему открылась среда: «auto» (неудачные загрузки), «manual» (кнопка) или ""."""
    try:
        with open("/proc/cmdline", encoding="utf-8") as f:
            for arg in f.read().split():
                if arg.startswith(REASON_ARG):
                    return arg[len(REASON_ARG):]
    except OSError:
        pass
    return ""
