"""Строки интерфейса на 10 языках из localization.csv (ключ, en, ru, de, ...)."""
from __future__ import annotations

import csv
import os


class Localizer:
    def __init__(self, path: str):
        self.strings: dict[str, dict[str, str]] = {}
        self.languages: list[str] = []
        self._load(path)
        from equestria_kit.i18n import detect_language
        sys_code = detect_language()
        self.lang = sys_code if sys_code in self.languages else "en"

    def _load(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                rows = list(csv.reader(f))
        except OSError:
            return
        if not rows:
            return
        self.languages = [h.strip() for h in rows[0][1:]]
        for row in rows[1:]:
            if row and row[0].strip():
                self.strings[row[0].strip()] = {
                    lang: text.strip().replace("\\n", "\n")
                    for lang, text in zip(self.languages, row[1:])}

    def has(self, key: str) -> bool:
        return key in self.strings

    def t(self, key: str, *args) -> str:
        texts = self.strings.get(key, {})
        text = texts.get(self.lang) or texts.get("en") or key
        for i, arg in enumerate(args):
            text = text.replace("{%d}" % i, str(arg))
        return text
