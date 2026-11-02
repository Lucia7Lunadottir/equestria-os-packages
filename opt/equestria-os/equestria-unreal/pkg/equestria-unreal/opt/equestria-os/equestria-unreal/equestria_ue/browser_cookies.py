"""Перенос входа в Epic из обычных браузеров (Firefox- и Chromium-семейство) — каждый источник отдельный класс."""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

HOSTS = ("epicgames.com", "unrealengine.com")
HOME = Path.home()


@dataclass
class Cookie:
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: int = 0           # unix-секунды, 0 — сессионная
    secure: bool = False
    http_only: bool = False


def _copy_db(src: Path, td: str) -> Path:
    dst = Path(td) / "c.sqlite"
    shutil.copy2(src, dst)
    wal = Path(str(src) + "-wal")
    if wal.exists():
        shutil.copy2(wal, Path(td) / "c.sqlite-wal")
    return dst


def _where(col: str) -> str:
    return " or ".join(f"{col} like '%{h}'" for h in HOSTS)


class CookieSource(ABC):
    def __init__(self, db: Path, label: str):
        self.db, self.label = db, label

    @abstractmethod
    def read(self) -> list:
        """Cookie Epic из этого браузера (пустой список, если нет или не удалось прочитать)."""


class FirefoxSource(CookieSource):
    def read(self) -> list:
        out = []
        with tempfile.TemporaryDirectory() as td:
            try:
                con = sqlite3.connect(str(_copy_db(self.db, td)))
                rows = con.execute("select name, value, host, path, expiry, isSecure, isHttpOnly from moz_cookies "
                                   f"where {_where('host')}").fetchall()
                con.close()
            except (sqlite3.Error, OSError):
                return []
        for n, v, h, p, e, s, ho in rows:
            e = int(e or 0)
            out.append(Cookie(n, v, h, p or "/", e if e < 1e11 else e // 1000, bool(s), bool(ho)))
        return out


class ChromiumSource(CookieSource):
    # метка в связке ключей -> (application для secret-tool, имя «Safe Storage» / папки кошелька KWallet)
    KEYRINGS = [("chrome", "Chrome"), ("chromium", "Chromium"), ("brave", "Brave"), ("vivaldi", "Vivaldi"),
                ("opera", "Opera"), ("microsoft-edge", "Chromium"), ("yandex-browser", "Yandex")]

    @staticmethod
    def _run(cmd: list, inp: bytes | None = None) -> bytes:
        try:
            return subprocess.run(cmd, input=inp, capture_output=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            return b""

    def _passwords(self) -> list:
        """Кандидаты пароля шифрования: связка ключей (libsecret / KWallet), затем «peanuts»."""
        out = []
        for app, label in self.KEYRINGS:
            p = self._run(["secret-tool", "lookup", "application", app]).strip()
            if p:
                out.append(p)
            p = self._run(["kwallet-query", "-r", f"{label} Safe Storage", "-f", f"{label} Keys", "kdewallet"]).strip()
            if p and not p.lower().startswith(b"failed"):
                out.append(p)
        return out + [b"peanuts"]

    def _decrypt(self, enc: bytes, host: str, keys: list) -> str:
        if enc[:3] not in (b"v10", b"v11"):
            return ""
        for pw in keys:
            key = hashlib.pbkdf2_hmac("sha1", pw, b"saltysalt", 1, 16).hex()
            raw = self._run(["openssl", "enc", "-d", "-aes-128-cbc", "-K", key, "-iv", "20" * 16], enc[3:])
            if not raw:
                continue
            if raw[:32] == hashlib.sha256(host.encode()).digest():       # Chromium ≥ 24 добавляет хеш домена
                raw = raw[32:]
            try:
                txt = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if txt.isprintable():
                return txt
        return ""

    def read(self) -> list:
        out = []
        with tempfile.TemporaryDirectory() as td:
            try:
                con = sqlite3.connect(str(_copy_db(self.db, td)))
                rows = con.execute("select host_key, name, value, encrypted_value, path, expires_utc, is_secure, "
                                   f"is_httponly from cookies where {_where('host_key')}").fetchall()
                con.close()
            except (sqlite3.Error, OSError):
                return []
        keys = None
        for host, name, val, enc, path, exp, sec, ho in rows:
            if not val and enc:
                if keys is None:
                    keys = self._passwords()
                val = self._decrypt(bytes(enc), host, keys)
            if not val:
                continue
            ts = int(exp / 1e6 - 11644473600) if exp else 0
            out.append(Cookie(name, val, host, path or "/", max(ts, 0), bool(sec), bool(ho)))
        return out


FIREFOX_GLOBS = [".mozilla/firefox/*/cookies.sqlite", ".librewolf/*/cookies.sqlite", ".zen/*/cookies.sqlite",
                 ".waterfox/*/cookies.sqlite", ".floorp/*/cookies.sqlite",
                 ".var/app/*/.mozilla/firefox/*/cookies.sqlite", ".var/app/*/.librewolf/*/cookies.sqlite",
                 "snap/firefox/common/.mozilla/firefox/*/cookies.sqlite"]
CHROMIUM_GLOBS = [".config/*/*/Network/Cookies", ".config/*/*/Cookies", ".config/*/*/*/Network/Cookies",
                  ".config/*/*/*/Cookies", ".var/app/*/config/*/*/Network/Cookies",
                  ".var/app/*/config/*/*/*/Network/Cookies", "snap/*/common/.config/*/*/Network/Cookies"]


def discover() -> list:
    """Находит профили всех установленных браузеров, у которых есть файл cookie."""
    found = []
    for pat in FIREFOX_GLOBS:
        for p in HOME.glob(pat):
            rel = p.relative_to(HOME).parts
            found.append(FirefoxSource(p, f"{rel[0].strip('.').title()} · {p.parent.name}"))
    seen = set()
    for pat in CHROMIUM_GLOBS:
        for p in HOME.glob(pat):
            if p in seen or "Epic" in p.parts or not p.is_file():
                continue
            seen.add(p)
            parts = p.relative_to(HOME).parts
            i = parts.index("config") + 1 if "config" in parts else 1
            prof = p.parent.parent.name if p.parent.name == "Network" else p.parent.name
            found.append(ChromiumSource(p, f"{parts[i]} · {prof}"))
    found.sort(key=lambda s: s.db.stat().st_mtime, reverse=True)
    return found
