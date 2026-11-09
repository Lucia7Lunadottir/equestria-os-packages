"""notes: storage."""
from __future__ import annotations

import os
import re
from PyQt6.QtCore import QStandardPaths
from pathlib import Path
from .localization import tr


def global_dir() -> Path:
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    base = Path(docs) if docs else Path.home() / "Documents"
    legacy = base / "Заметки"  # имя папки на диске, созданной до локализации, — не терять заметки
    return legacy if legacy.exists() else base / tr("storage.notes")


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().replace("\r\n", "\n")


def write_text(path: str, text: str) -> None:
    tmp = path + ".tmp~"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def note_title(path: str) -> str:
    name = os.path.basename(path)
    return name[:-3] if name.lower().endswith(".md") else name


def preview_of(text: str) -> str:
    for line in text.split("\n"):
        t = re.sub(r"^\s*(#{1,6}\s+|[-*+]\s+(\[[ xX]\]\s+)?|\d+[.)]\s+|>\s*)", "", line)
        t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t).strip()   # картинки в превью не показываем
        if t:
            return t[:70]
    return ""
