"""Программы, установленные из пакетов DEB и RPM: список, проверка обновлений, скачивание.

Такие программы ставятся распаковкой файлов (foreign_bridge.py), и pacman о них
не знает — обновления сами не приходят. Здесь их версии сравниваются с
репозиторием производителя (sources.py); новая версия ставится тем же мастером
установки (install_wizard.py).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal

import pkgmeta
import sources
from ui_common import CACHE_DIR, tr

MANIFEST_DIR = "/var/lib/equestria-installer/foreign"


@dataclass
class InstalledPackage:
    name: str
    version: str
    fmt: str
    manifest: str                       # имя записи для команды uninstall
    source: dict | None
    files: list = field(default_factory=list)
    latest: sources.Candidate | None = None
    error: str = ""

    @property
    def display_version(self) -> str:
        return tr("неизвестна") if self.version == pkgmeta.UNKNOWN_VERSION else self.version

    @property
    def source_text(self) -> str:
        if not self.source:
            return tr("нет источника")
        return urlparse(self.source.get("url", "")).hostname or self.source.get("url", "")

    @property
    def has_update(self) -> bool:
        return self.latest is not None and (self.version == pkgmeta.UNKNOWN_VERSION or
                                            pkgmeta.compare_versions(self.latest.version, self.version) > 0)

    @classmethod
    def load_all(cls) -> list["InstalledPackage"]:
        out = []
        if not os.path.isdir(MANIFEST_DIR):
            return out
        for entry in sorted(os.listdir(MANIFEST_DIR)):
            try:
                with open(os.path.join(MANIFEST_DIR, entry)) as f:
                    m = json.load(f)
            except (OSError, ValueError):
                continue
            files = m.get("files", [])
            # записи старых версий установщика: имя RPM-файла вместо имени пакета, без источника
            name = m["name"] if m["name"] in pkgmeta.KNOWN_SOURCES else (pkgmeta.known_name(files) or m["name"])
            source = m.get("source") or pkgmeta.detect_source(name, m.get("format", "deb"), "", files)
            out.append(cls(name, m.get("version", pkgmeta.UNKNOWN_VERSION), m.get("format", "?"), m["name"], source, files))
        return out


def check_updates(packages: list[InstalledPackage]) -> None:
    """Заполнить latest/error у пакетов; один индекс репозитория на источник."""
    repos = {}
    for p in packages:
        p.latest, p.error = None, ""
        if not p.source:
            continue
        try:
            repo = sources.Repository.for_source(p.source)
            repo = repos.setdefault(repo.key(), repo)
            p.latest = repo.latest(p.source.get("package", p.name))
        except Exception as e:  # noqa: BLE001 — сеть/формат индекса: показываем в строке пакета
            p.error = str(e)


class UpdateCheck(QThread):
    """Индексы репозиториев — в фоне; один индекс на источник за проверку.
    Итог — штатный сигнал finished: он приходит, когда поток уже завершён, и
    ссылку на поток можно отпускать (иначе Qt роняет программу)."""

    def __init__(self, packages: list[InstalledPackage]):
        super().__init__()
        self.packages = packages

    def run(self):
        check_updates(self.packages)


class Download(QThread):
    """Скачивание пакета; итог (path или error) читается по сигналу finished."""
    progress = pyqtSignal(int)

    def __init__(self, candidate: sources.Candidate):
        super().__init__()
        self.candidate = candidate
        self.path, self.error = "", ""

    def run(self):
        try:
            self.path = str(sources.download(self.candidate, Path(CACHE_DIR) / "updates",
                                             lambda done, total: self.progress.emit(int(done * 100 / total) if total else 0)))
        except OSError as e:
            self.error = (tr("Контрольная сумма не совпала — файл повреждён или подменён.")
                          if "checksum" in str(e) else str(e))
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
