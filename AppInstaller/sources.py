"""Проверка обновлений пакетов .deb/.rpm в репозиториях производителей.

Работает от пользователя (без root): читает индекс репозитория, находит новейшую
версию пакета, скачивает файл и сверяет контрольную сумму из индекса. Ставит его
потом обычный мастер установки (foreign_bridge.py через pkexec).
"""
from __future__ import annotations

import gzip
import hashlib
import lzma
import os
import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from pkgmeta import ARCH_DEB, ARCH_RPM, compare_versions

USER_AGENT = "Equestria-OS-Installer/2.0"
TIMEOUT = 30


@dataclass
class Candidate:
    version: str
    url: str
    sha256: str
    filename: str


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


class Repository(ABC):
    """Репозиторий производителя; индекс скачивается один раз за проверку."""

    def __init__(self, source: dict):
        self.source = source
        self._index = None

    @staticmethod
    def for_source(source: dict) -> "Repository":
        kinds = {"apt": AptRepository, "yum": YumRepository}
        if source.get("type") not in kinds:
            raise ValueError(f"unknown source type: {source.get('type')}")
        return kinds[source["type"]](source)

    def key(self) -> tuple:
        return tuple(sorted((k, v) for k, v in self.source.items() if k != "package"))

    def latest(self, package: str) -> Candidate | None:
        if self._index is None:
            self._index = self._load_index()
        found = [c for name, c in self._index if name == package]
        best = None
        for c in found:
            if best is None or compare_versions(c.version, best.version) > 0:
                best = c
        return best

    @abstractmethod
    def _load_index(self) -> list[tuple[str, Candidate]]: ...


class AptRepository(Repository):
    """Debian/Ubuntu: dists/<suite>/<component>/binary-amd64/Packages(.xz|.gz)."""

    def _load_index(self):
        s = self.source
        base = f"{s['url']}/dists/{s['suite']}/{s['component']}/binary-{ARCH_DEB}/Packages"
        text = None
        for suffix, unpack in ((".xz", lzma.decompress), (".gz", gzip.decompress), ("", lambda b: b)):
            try:
                text = unpack(_get(base + suffix)).decode("utf-8", "replace")
                break
            except Exception:  # noqa: BLE001 — пробуем следующий формат индекса
                continue
        if text is None:
            raise OSError(f"no Packages index at {base}")
        out = []
        for block in text.split("\n\n"):
            fields = {}
            for line in block.splitlines():
                if ":" in line and not line.startswith(" "):
                    k, _, v = line.partition(":")
                    fields[k.strip()] = v.strip()
            if {"Package", "Version", "Filename"} <= fields.keys():
                out.append((fields["Package"], Candidate(fields["Version"], f"{s['url']}/{fields['Filename']}",
                                                          fields.get("SHA256", ""), os.path.basename(fields["Filename"]))))
        return out


class YumRepository(Repository):
    """Fedora/RHEL: repodata/repomd.xml → primary.xml.gz."""

    NS = {"repo": "http://linux.duke.edu/metadata/repo", "common": "http://linux.duke.edu/metadata/common"}

    def _load_index(self):
        url = self.source["url"]
        repomd = ET.fromstring(_get(f"{url}/repodata/repomd.xml"))
        loc = next(d.find("repo:location", self.NS).get("href")
                   for d in repomd.findall("repo:data", self.NS) if d.get("type") == "primary")
        raw = _get(f"{url}/{loc}")
        if loc.endswith(".gz"):
            raw = gzip.decompress(raw)
        elif loc.endswith(".xz"):
            raw = lzma.decompress(raw)
        root = ET.fromstring(raw)
        out = []
        for pkg in root.findall("common:package", self.NS):
            if pkg.findtext("common:arch", namespaces=self.NS) not in (ARCH_RPM, "noarch"):
                continue
            v = pkg.find("common:version", self.NS)
            version = f"{v.get('ver')}-{v.get('rel')}"
            if v.get("epoch") not in (None, "0"):
                version = f"{v.get('epoch')}:{version}"
            checksum = pkg.find("common:checksum", self.NS)
            href = pkg.find("common:location", self.NS).get("href")
            out.append((pkg.findtext("common:name", namespaces=self.NS),
                        Candidate(version, f"{url}/{href}",
                                  checksum.text if checksum is not None and checksum.get("type") == "sha256" else "",
                                  os.path.basename(href))))
        return out


def download(candidate: Candidate, dest_dir: Path, progress=None) -> Path:
    """Скачать пакет; при несовпадении SHA256 из индекса — ошибка, файл удаляется."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / candidate.filename
    req = urllib.request.Request(candidate.url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if candidate.sha256 and digest.hexdigest() != candidate.sha256.lower():
        dest.unlink(missing_ok=True)
        raise OSError("checksum mismatch")
    return dest
