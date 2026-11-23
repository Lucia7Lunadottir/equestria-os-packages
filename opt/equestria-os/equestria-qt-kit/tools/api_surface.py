#!/usr/bin/env python3
"""Какие части equestria_kit реально используют приложения (разбор исходников, без запуска).

    python3 tools/api_surface.py            # пересобрать api_surface.json по всему репозиторию
    python3 tools/api_surface.py --check    # код 1, если приложения используют то, чего нет в api_surface.json

api_surface.json — «замок» публичного интерфейса: tests/test_api_surface.py проверяет, что всё перечисленное
в нём по-прежнему есть в библиотеке. Удалить или переименовать то, чем пользуется хоть одно приложение,
нельзя, пока это не исчезнет из всех приложений (см. STABILITY.md).
"""
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
REPO = KIT_ROOT.parent.parent          # equestria-packages/
OUT = KIT_ROOT / "api_surface.json"
SKIP_PARTS = {"pkg", "src", "tests", "__pycache__", "node_modules", ".git", "equestria-qt-kit", "docs"}


def python_files():
    for path in REPO.rglob("*.py"):
        if SKIP_PARTS.isdisjoint(path.relative_to(REPO).parts):
            yield path


def scan_file(path: Path, found: dict) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return
    alias_to_module: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "equestria_kit":
            for a in node.names:
                if a.name == "*":
                    continue
                found[node.module].add(a.name)
                if node.module == "equestria_kit":          # from equestria_kit import qt as kit_qt
                    alias_to_module[a.asname or a.name] = f"equestria_kit.{a.name}"
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == "equestria_kit":
                    found["equestria_kit"].add(a.name.split(".")[1]) if "." in a.name else None
                    if a.asname:
                        alias_to_module[a.asname] = a.name
    for node in ast.walk(tree):                              # kit_qt.something
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in alias_to_module:
            found[alias_to_module[node.value.id]].add(node.attr)


def collect() -> dict:
    found: dict[str, set] = defaultdict(set)
    for path in python_files():
        scan_file(path, found)
    return {m: sorted(n) for m, n in sorted(found.items())}


def main() -> int:
    surface = collect()
    if "--check" in sys.argv:
        try:
            locked = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            locked = {}
        new = {m: sorted(set(n) - set(locked.get(m, []))) for m, n in surface.items()}
        new = {m: n for m, n in new.items() if n}
        for m, n in new.items():
            print(f"новое использование {m}: {', '.join(n)}  (запустите tools/api_surface.py)")
        return 1 if new else 0
    OUT.write_text(json.dumps(surface, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(v) for v in surface.values())
    print(f"модулей: {len(surface)}, используемых имён: {total} → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
