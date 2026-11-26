"""
Откуда берётся ISO: RSS-лента файлов проекта на SourceForge (там же md5 и размер)
и загрузка с докачкой. Работает от обычного пользователя — в его кэш; root нужен
только на последнем шаге (переложить готовый файл в /var/lib).
"""
import hashlib
import os
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from recovery_paths import FEED_URL, DOWNLOAD_URL, APP_ID
from recovery_image import version_from_filename

_MEDIA = "{http://video.search.yahoo.com/mrss/}"
_UA = "equestria-os-recovery"
CHUNK = 1024 * 1024


class SourceError(Exception):
    """args[0] — ключ перевода, args[1:] — подробности."""


@dataclass
class Release:
    name: str
    version: str
    size: int
    md5: str

    @property
    def url(self) -> str:
        return DOWNLOAD_URL.format(name=self.name)


class ReleaseFeed:
    """Самый новый equestria-os-ГГГГ.ММ.ДД-x86_64.iso из ленты."""

    def __init__(self, url: str = FEED_URL, timeout: int = 30):
        self.url, self.timeout = url, timeout

    def latest(self) -> Release:
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
        except OSError as e:
            raise SourceError("error.network", str(e)) from e
        releases = self.parse(data)
        if not releases:
            raise SourceError("error.no_release")
        return max(releases, key=lambda r: r.version)

    @staticmethod
    def parse(data: bytes) -> list:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            raise SourceError("error.feed", str(e)) from e
        out = []
        for item in root.iter("item"):
            name = os.path.basename((item.findtext("title") or "").strip())
            version = version_from_filename(name)
            content = item.find(f"{_MEDIA}content")
            if not version or content is None:
                continue
            md5 = content.find(f"{_MEDIA}hash")
            try:
                size = int(content.get("filesize", "0"))
            except ValueError:
                size = 0
            out.append(Release(name=name, version=version, size=size,
                               md5=(md5.text or "").strip().lower() if md5 is not None else ""))
        return out


def download_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / APP_ID


class Downloader:
    """Скачивает Release в <кэш>/<имя>.part с докачкой, проверяет размер и md5.

    progress(done, total) вызывается примерно раз в мегабайт; cancelled() — опрос
    отмены. Возвращает путь к готовому файлу (без .part).
    """

    def __init__(self, release: Release, target_dir: Path | None = None, timeout: int = 60):
        self.release = release
        self.dir = Path(target_dir or download_dir())
        self.timeout = timeout

    @property
    def final_path(self) -> Path:
        return self.dir / self.release.name

    @property
    def part_path(self) -> Path:
        return self.dir / (self.release.name + ".part")

    def run(self, progress=lambda done, total: None, cancelled=lambda: False) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        rel = self.release
        if self.final_path.exists() and self._verify(self.final_path, progress, cancelled):
            return self.final_path
        self._check_space()

        md5 = hashlib.md5()
        done = 0
        if self.part_path.exists():
            done = self.part_path.stat().st_size
            if rel.size and done > rel.size:
                self.part_path.unlink()
                done = 0
            else:
                # докачка: хэш уже скачанной части считаем заново
                with open(self.part_path, "rb") as f:
                    for block in iter(lambda: f.read(CHUNK), b""):
                        md5.update(block)

        if not rel.size or done < rel.size:
            headers = {"User-Agent": _UA}
            if done:
                headers["Range"] = f"bytes={done}-"
            try:
                req = urllib.request.Request(rel.url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if done and resp.status != 206:
                        # зеркало не умеет докачку — начинаем сначала
                        done, md5 = 0, hashlib.md5()
                    mode = "ab" if done else "wb"
                    with open(self.part_path, mode) as out:
                        while True:
                            if cancelled():
                                raise SourceError("error.cancelled")
                            block = resp.read(CHUNK)
                            if not block:
                                break
                            out.write(block)
                            md5.update(block)
                            done += len(block)
                            progress(done, rel.size)
            except SourceError:
                raise
            except OSError as e:
                raise SourceError("error.network", str(e)) from e

        if rel.size and done != rel.size:
            raise SourceError("error.incomplete", f"{done}/{rel.size}")
        if rel.md5 and md5.hexdigest() != rel.md5:
            self.part_path.unlink(missing_ok=True)
            raise SourceError("error.checksum")
        os.replace(self.part_path, self.final_path)
        return self.final_path

    def _verify(self, path: Path, progress, cancelled) -> bool:
        rel = self.release
        if rel.size and path.stat().st_size != rel.size:
            return False
        if not rel.md5:
            return True
        md5, done = hashlib.md5(), 0
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(CHUNK), b""):
                if cancelled():
                    raise SourceError("error.cancelled")
                md5.update(block)
                done += len(block)
                progress(done, rel.size)
        return md5.hexdigest() == rel.md5

    def _check_space(self) -> None:
        need = self.release.size - (self.part_path.stat().st_size if self.part_path.exists() else 0)
        free = os.statvfs(self.dir)
        if need > 0 and free.f_bavail * free.f_frsize < need + 512 * 1024 ** 2:
            raise SourceError("error.no_space", str(need))

    def discard(self) -> None:
        self.part_path.unlink(missing_ok=True)
