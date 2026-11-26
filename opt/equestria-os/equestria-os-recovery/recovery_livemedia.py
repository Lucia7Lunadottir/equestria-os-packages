"""
Откуда запущена live-среда — чтобы установщик (Calamares) мог сразу положить этот же
ISO в новую систему, без отдельного скачивания.

LiveMedium.detect() различает:
  * файл — среда загружена из ISO-файла (наш пункт «Восстановление», GRUB loopback,
    img_dev/img_loop): берём этот файл;
  * устройство — флешка/диск, записанные из ISO (dd, Ventoy, Etcher), или CD.
    ISO занимает начало устройства, а его точный размер записан в самом образе:
    резервная копия заголовка GPT лежит в последнем секторе ISO (xorriso
    -appended_part_as_gpt). Запасной вариант — размер тома ISO 9660.

RootfsVerifier сверяет airootfs.sfs с контрольной суммой, которую archiso кладёт в
образ (arch/x86_64/airootfs.sha512), — так видно, что копия с флешки целая.
"""
import hashlib
import os
import struct
import subprocess
from dataclasses import dataclass

SECTOR = 512
ISO_BLOCK = 2048
_BOOTMNT = "/run/archiso/bootmnt"
_IMG_DEV = "/run/archiso/img_dev"
_OWN_MNT = "/run/equestria-recovery-medium"


class MediumError(Exception):
    """args[0] — ключ перевода."""


def _cmdline() -> dict:
    try:
        with open("/proc/cmdline", encoding="utf-8") as f:
            args = f.read().split()
    except OSError:
        return {}
    out = {}
    for arg in args:
        key, _, value = arg.partition("=")
        out[key] = value.strip('"')
    return out


def _run(*cmd) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def image_size_on_device(head: bytes, device_size: int) -> int:
    """Размер ISO по первым 40 КиБ устройства. 0 — не похоже на ISO."""
    if len(head) < 17 * ISO_BLOCK:
        return 0
    gpt_size = 0
    if head[SECTOR:SECTOR + 8] == b"EFI PART":
        backup_lba = struct.unpack_from("<Q", head, SECTOR + 32)[0]
        gpt_size = (backup_lba + 1) * SECTOR
    pvd = head[16 * ISO_BLOCK:17 * ISO_BLOCK]
    iso_size = struct.unpack_from("<I", pvd, 80)[0] * ISO_BLOCK if pvd[1:6] == b"CD001" else 0
    if not iso_size:
        return 0
    # GPT образа описывает весь файл (вместе с EFI-разделом после тома ISO 9660)
    size = gpt_size if gpt_size >= iso_size else iso_size
    return size if 0 < size <= device_size else 0


@dataclass
class LiveMedium:
    path: str          # файл ISO или блочное устройство
    size: int          # сколько байт читать
    kind: str          # "file" | "device"
    own_mount: str = ""  # раздел с ISO подключили сами — release() отключит

    @classmethod
    def detect(cls) -> "LiveMedium":
        args = _cmdline()
        loop = args.get("img_loop", "")
        if loop:
            found = cls._from_file(args, loop)
            if found:
                return found
        device = cls._device(args)
        if not device:
            raise MediumError("error.no_live_medium")
        try:
            with open(device, "rb") as f:
                head = f.read(20 * ISO_BLOCK)
                device_size = f.seek(0, os.SEEK_END)
        except OSError:
            raise MediumError("error.no_live_medium")
        size = image_size_on_device(head, device_size)
        if not size:
            raise MediumError("error.no_live_medium")
        return cls(path=device, size=size, kind="device")

    def release(self) -> None:
        if self.own_mount:
            subprocess.run(["umount", self.own_mount], capture_output=True)
            try:
                os.rmdir(self.own_mount)
            except OSError:
                pass
            self.own_mount = ""

    @classmethod
    def _from_file(cls, args: dict, loop: str):
        """Среда загружена из ISO-файла (img_dev/img_loop). С copytoram раздел уже
        отключён — подключаем его сами, только на чтение."""
        top, own = _IMG_DEV, ""
        if not os.path.ismount(_IMG_DEV):
            spec = args.get("img_dev", "")
            if not spec:
                return None
            os.makedirs(_OWN_MNT, exist_ok=True)
            opts = ",".join(["ro"] + ([args["img_flags"]] if args.get("img_flags") else []))
            dev = spec if spec.startswith("/") else ""
            if not dev and "=" in spec:
                key, value = spec.split("=", 1)
                dev = f"/dev/disk/by-{key.lower()}/{value}"
            if subprocess.run(["mount", "-o", opts, dev, _OWN_MNT], capture_output=True).returncode != 0:
                return None
            top = own = _OWN_MNT
        path = os.path.join(top, loop.lstrip("/"))
        if os.path.isfile(path):
            return cls(path=path, size=os.path.getsize(path), kind="file", own_mount=own)
        if own:
            subprocess.run(["umount", own], capture_output=True)
        return None

    @staticmethod
    def _device(args: dict) -> str:
        """Устройство, где ISO начинается с нулевого байта."""
        dev = _run("findmnt", "-n", "-o", "SOURCE", _BOOTMNT)
        if not dev:   # copytoram: флешка уже отключена от bootmnt, но ещё вставлена
            for key, folder in (("archisosearchuuid", "by-uuid"), ("archisolabel", "by-label")):
                if args.get(key) and os.path.exists(f"/dev/disk/{folder}/{args[key]}"):
                    dev = os.path.realpath(f"/dev/disk/{folder}/{args[key]}")
                    break
            else:
                dev = args.get("archisodevice", "")
        if not dev or not os.path.exists(dev):
            return ""
        # том ISO может быть смонтирован с раздела гибридной таблицы — читаем весь диск
        if _run("lsblk", "-ndo", "TYPE", dev) == "part":
            parent = _run("lsblk", "-ndo", "PKNAME", dev)
            if parent:
                dev = f"/dev/{parent}"
        return dev


class RootfsVerifier:
    """Сверяет airootfs.sfs внутри ISO с arch/x86_64/airootfs.sha512."""

    MEMBER = "arch/x86_64/airootfs.sfs"
    SUM = "arch/x86_64/airootfs.sha512"

    def verify(self, iso_path: str) -> bool | None:
        """True — совпало, False — образ испорчен, None — проверить нечем."""
        expected = subprocess.run(["bsdtar", "-xOf", iso_path, self.SUM], capture_output=True)
        if expected.returncode != 0 or not expected.stdout.strip():
            return None
        want = expected.stdout.split()[0].decode("ascii", "replace").lower()
        digest = hashlib.sha512()
        with subprocess.Popen(["bsdtar", "-xOf", iso_path, self.MEMBER], stdout=subprocess.PIPE) as proc:
            assert proc.stdout is not None
            for block in iter(lambda: proc.stdout.read(4 * 1024 * 1024), b""):
                digest.update(block)
        if proc.returncode != 0:
            return False
        return digest.hexdigest() == want
