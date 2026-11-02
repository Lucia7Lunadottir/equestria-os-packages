"""Сведения о пакетах .deb/.rpm — без установки и без запуска их скриптов.

Общий модуль для foreign_bridge.py (работает от root через pkexec) и для окна
установщика (работает от пользователя): имя, версия, скрипты пакета и источник
обновлений.

Источник обновлений. В Debian/Ubuntu и Fedora пакет сам подключает репозиторий
производителя своим установочным скриптом, и дальше его обновляет системный
менеджер пакетов. Здесь скрипты НЕ выполняются (безопасность), поэтому адрес
репозитория вынимается из их текста, а для пакетов, у которых его там нет, —
из небольшого справочника известных программ (KNOWN_SOURCES).
"""
from __future__ import annotations

import io
import os
import re
import struct
import subprocess
import tarfile
import tempfile

ARCH_DEB, ARCH_RPM = "amd64", "x86_64"


# ─── Версии ───────────────────────────────────────────────────────────────

def _order(c: str) -> int:
    if c == "~":
        return -1
    if c.isdigit():
        return 0
    if c.isalpha():
        return ord(c)
    return ord(c) + 256


def _cmp_part(a: str, b: str) -> int:
    """Сравнение по алгоритму dpkg: чередуются нецифровые и цифровые куски."""
    while a or b:
        na = re.match(r"[^\d]*", a).group()
        nb = re.match(r"[^\d]*", b).group()
        for i in range(max(len(na), len(nb))):
            ca = _order(na[i]) if i < len(na) else 0
            cb = _order(nb[i]) if i < len(nb) else 0
            if ca != cb:
                return -1 if ca < cb else 1
        a, b = a[len(na):], b[len(nb):]
        da = re.match(r"\d*", a).group()
        db = re.match(r"\d*", b).group()
        ia, ib = int(da or 0), int(db or 0)
        if ia != ib:
            return -1 if ia < ib else 1
        a, b = a[len(da):], b[len(db):]
    return 0


def compare_versions(a: str, b: str) -> int:
    """-1 / 0 / 1. Понимает эпоху «1:» и ревизию «-1» (deb и rpm)."""
    def split(v):
        epoch, _, rest = v.rpartition(":") if ":" in v else ("0", "", v)
        upstream, _, rev = rest.rpartition("-") if "-" in rest else (rest, "", "")
        return int(epoch or 0) if epoch.isdigit() else 0, upstream, rev
    ea, ua, ra = split(a)
    eb, ub, rb = split(b)
    if ea != eb:
        return -1 if ea < eb else 1
    return _cmp_part(ua, ub) or _cmp_part(ra, rb)


UNKNOWN_VERSION = "0"


# ─── Источники обновлений ─────────────────────────────────────────────────

def apt_source(url: str, suite: str, component: str, package: str) -> dict:
    return {"type": "apt", "url": url.rstrip("/"), "suite": suite, "component": component, "package": package}


def yum_source(url: str, package: str) -> dict:
    return {"type": "yum", "url": url.rstrip("/"), "package": package}


# Пакеты, которые подключают репозиторий так, что из скрипта адрес не достать
# (или пакет уже установлен старой версией установщика). Проверено 2026-11-02.
# files — по какому файлу узнать программу, если имя пакета неизвестно.
KNOWN_SOURCES = {
    "unityhub": (apt_source("https://hub.unity3d.com/linux/repos/deb", "stable", "main", "unityhub"), "/usr/bin/unityhub"),
    "opera-gx-stable": (apt_source("https://deb.opera.com/opera-gx-stable", "stable", "non-free", "opera-gx-stable"), "/usr/bin/opera-gx"),
    "opera-stable": (apt_source("https://deb.opera.com/opera-stable", "stable", "non-free", "opera-stable"), "/usr/bin/opera"),
    "google-chrome-stable": (apt_source("https://dl.google.com/linux/chrome/deb", "stable", "main", "google-chrome-stable"), "/usr/bin/google-chrome-stable"),
    "code": (apt_source("https://packages.microsoft.com/repos/code", "stable", "main", "code"), "/usr/share/code/code"),
    "microsoft-edge-stable": (apt_source("https://packages.microsoft.com/repos/edge", "stable", "main", "microsoft-edge-stable"), "/usr/bin/microsoft-edge-stable"),
    "brave-browser": (apt_source("https://brave-browser-apt-release.s3.brave.com", "stable", "main", "brave-browser"), "/usr/bin/brave-browser"),
    "vivaldi-stable": (apt_source("https://repo.vivaldi.com/archive/deb", "stable", "main", "vivaldi-stable"), "/usr/bin/vivaldi-stable"),
    "yandex-browser-stable": (apt_source("https://repo.yandex.ru/yandex-browser/deb", "stable", "main", "yandex-browser-stable"), "/usr/bin/yandex-browser-stable"),
}

_APT_LINE = re.compile(r"deb\s+(?:\[[^\]]*\]\s+)?(https?://[^\s\"'$]+)\s+([\w.-]+)\s+([\w.-]+)")
_YUM_BASEURL = re.compile(r"baseurl\s*=\s*(https?://[^\s\"'$]+)")


def detect_source(name: str, fmt: str, scripts: str, files: list[str] | None = None) -> dict | None:
    """Источник обновлений: из текста скриптов пакета, иначе из справочника."""
    if fmt == "deb":
        m = _APT_LINE.search(scripts)
        if m:
            return apt_source(m.group(1), m.group(2), m.group(3), name)
    else:
        m = _YUM_BASEURL.search(scripts)
        if m:
            return yum_source(m.group(1), name)
    if name in KNOWN_SOURCES:
        return dict(KNOWN_SOURCES[name][0])
    for known, (source, marker) in KNOWN_SOURCES.items():
        if files and marker in files:
            return dict(source)
    return None


def known_name(files: list[str]) -> str | None:
    """Имя пакета по характерному файлу — для записей старых версий установщика."""
    return next((n for n, (_s, marker) in KNOWN_SOURCES.items() if marker in files), None)


# ─── Чтение пакетов ───────────────────────────────────────────────────────

class PackageInfo:
    def __init__(self, name: str, version: str, fmt: str, scripts: str = ""):
        self.name, self.version, self.format, self.scripts = name, version, fmt, scripts

    def source(self, files: list[str] | None = None) -> dict | None:
        return detect_source(self.name, self.format, self.scripts, files)


def _parse_ar(data: bytes) -> dict:
    if data[:8] != b"!<arch>\n":
        raise ValueError("not a valid .deb (bad ar magic)")
    members, pos = {}, 8
    while pos + 60 <= len(data):
        header = data[pos:pos + 60]
        name = header[0:16].decode("ascii", "replace").strip().rstrip("/")
        size = int(header[48:58].decode("ascii", "replace").strip())
        pos += 60
        members[name] = data[pos:pos + size]
        pos += size + (size % 2)
    return members


def _read_tar(blob: bytes, name: str) -> tarfile.TarFile:
    if name.endswith(".zst"):   # tarfile не умеет zstd — распаковываем внешним zstd
        blob = subprocess.run(["zstd", "-dc"], input=blob, capture_output=True, check=True).stdout
        return tarfile.open(fileobj=io.BytesIO(blob), mode="r:")
    return tarfile.open(fileobj=io.BytesIO(blob), mode="r:*")


def read_deb(path: str) -> PackageInfo:
    with open(path, "rb") as f:
        members = _parse_ar(f.read())
    control_name = next((n for n in members if n.startswith("control.tar")), None)
    if not control_name:
        raise ValueError(".deb has no control.tar")
    tar = _read_tar(members[control_name], control_name)
    texts = {}
    for member in tar.getmembers():
        base = os.path.basename(member.name)
        if member.isfile() and base in ("control", "preinst", "postinst"):
            texts[base] = tar.extractfile(member).read().decode("utf-8", "replace")
    control = texts.get("control", "")
    name = re.search(r"^Package:\s*(\S+)", control, re.M)
    version = re.search(r"^Version:\s*(\S+)", control, re.M)
    return PackageInfo(name.group(1) if name else os.path.basename(path),
                       version.group(1) if version else UNKNOWN_VERSION, "deb",
                       texts.get("preinst", "") + "\n" + texts.get("postinst", ""))


# Метки заголовка RPM (rpmtag.h)
_RPM_NAME, _RPM_VERSION, _RPM_RELEASE, _RPM_EPOCH = 1000, 1001, 1002, 1003
_RPM_SCRIPTS = (1023, 1024)   # PREIN, POSTIN


def _rpm_header(data: bytes, offset: int) -> tuple[dict, int]:
    if data[offset:offset + 3] != b"\x8e\xad\xe8":
        raise ValueError("bad RPM header magic")
    nindex, hsize = struct.unpack(">II", data[offset + 8:offset + 16])
    store = offset + 16 + nindex * 16
    tags = {}
    for i in range(nindex):
        tag, typ, off, count = struct.unpack(">IIII", data[offset + 16 + i * 16:offset + 32 + i * 16])
        if typ in (6, 8, 9):   # STRING, STRING_ARRAY, I18NSTRING — первая строка
            end = data.index(b"\x00", store + off)
            tags[tag] = data[store + off:end].decode("utf-8", "replace")
        elif typ == 4:         # INT32
            tags[tag] = struct.unpack(">I", data[store + off:store + off + 4])[0]
    return tags, store + hsize


def read_rpm(path: str) -> PackageInfo:
    with open(path, "rb") as f:
        data = f.read(4 * 1024 * 1024)   # заголовки в начале файла
    if data[:4] != b"\xed\xab\xee\xdb":
        raise ValueError("not an RPM file")
    _sig, end = _rpm_header(data, 96)
    end += (8 - end % 8) % 8            # заголовок пакета выровнен на 8 байт
    tags, _ = _rpm_header(data, end)
    version = f"{tags.get(_RPM_VERSION, UNKNOWN_VERSION)}-{tags.get(_RPM_RELEASE, '0')}"
    if tags.get(_RPM_EPOCH):
        version = f"{tags[_RPM_EPOCH]}:{version}"
    scripts = "\n".join(str(tags.get(t, "")) for t in _RPM_SCRIPTS)
    return PackageInfo(tags.get(_RPM_NAME) or os.path.basename(path), version, "rpm", scripts)


def read_package(path: str) -> PackageInfo:
    if path.endswith(".deb"):
        return read_deb(path)
    if path.endswith(".rpm"):
        return read_rpm(path)
    raise ValueError(f"unsupported package type: {path}")
