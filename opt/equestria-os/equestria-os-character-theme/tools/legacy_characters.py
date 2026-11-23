#!/usr/bin/env python3
"""Собрать characters.json для старых читателей из characters.d.

    python3 tools/legacy_characters.py characters.d  characters.json

Старые версии equestria-qt-kit (и приложения, запущенные до обновления библиотеки) читают только общий файл.
Источник правды — characters.d; этот файл всегда получается из него (его вызывает PKGBUILD).
Убирать можно не раньше, чем все приложения перейдут на equestria-qt-kit >= 1.6 (см. STABILITY.md библиотеки).
"""
import json
import sys
from pathlib import Path


def build(src: Path) -> dict:
    chars = []
    for path in sorted(Path(src).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("Id"):
            chars.append(data)
    return {"Characters": chars}


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write(__doc__)
        return 2
    Path(sys.argv[2]).write_text(json.dumps(build(Path(sys.argv[1])), indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
