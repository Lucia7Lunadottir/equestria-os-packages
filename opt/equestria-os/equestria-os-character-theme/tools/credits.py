#!/usr/bin/env python3
"""Учёт авторов и лицензий картинок темы (обои и иконки).

Источник правды — credits.json (его правят руками: автор, ссылка, лицензия, статус).
CREDITS.md — читаемая таблица, она всегда получается из credits.json.

    python3 tools/credits.py            # дописать в credits.json новые файлы (статус "unknown") и пересобрать CREDITS.md
    python3 tools/credits.py --check    # ничего не писать; код 1, если есть файлы без записи или файлы-призраки

Уже заполненные записи скрипт не трогает: он только добавляет новые файлы и пересобирает CREDITS.md.

Запись следует за содержимым файла (md5), а не за именем: переименовали файл — данные остаются.
Соглашение об именах: «<Автор> <Персонаж> <номер>.ext» (например, «Hasbro Rarity.png»,
«SambaNeko Fluttershy 0.jpg»). Известные авторы перечислены в FILENAME_AUTHORS: если имя начинается
с такого автора, а в записи автора ещё нет, он подставляется сам.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "credits.json"
OUT = ROOT / "CREDITS.md"
FOLDERS = ("Wallpapers", "MLP Cutiemarks")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# Статусы: что известно о праве использовать картинку.
STATUSES = {
    "unknown": "неизвестно: автор и лицензия не установлены",
    "permission": "есть разрешение автора",
    "free": "свободная лицензия (CC0, CC-BY и т.п.)",
    "own": "своя работа проекта",
    "personal": "автор разрешает личное использование (обычно с указанием автора); для раздачи в ISO нужна проверка лицензии конкретной работы",
    "orphan": "автора не нашли или источник пропал (аккаунт удалён, страница 404): спросить разрешение некому, права автора от этого не исчезают",
    "proprietary": "правообладатель известен (напр. Hasbro), разрешения на раздачу нет",
    "remove": "убрать (автор попросил или лицензия не позволяет)",
}


# Автор из начала имени файла -> (автор, статус, лицензия). Дополняйте, когда находите автора.
FILENAME_AUTHORS = {
    "Hasbro": {"author": "Hasbro (My Little Pony: Equestria Girls)", "status": "proprietary",
               "license": "© Hasbro, все права защищены", "source_url": None, "note": "кадр из сериала (подтверждено владелицей проекта)"},
    "SambaNeko": {"author": "SambaNeko", "status": "personal",
                  "license": "FAQ автора: личное использование с указанием автора и ссылкой; коммерческое — только с разрешения. "
                             "На проверенных работах — CC BY-NC-ND 3.0 (проверено 23.11.2026 по страницам автора)",
                  "source_url": "https://www.deviantart.com/sambaneko/",
                  "note": "условия: https://www.deviantart.com/sambaneko/journal/FAQs-779112352 ; лицензию именно этой картинки на её странице ещё не проверяли"},
    "sushiwacky": {"author": "sushiwacky", "status": "unknown", "license": None, "source_url": None,
                   "note": "автор — по имени файла от владелицы проекта; профиль, источник и лицензия не проверены"},
    "ryuu": {"author": "ryuu (@_ryuu_chan_ на X)", "status": "unknown", "license": None,
             "source_url": "https://x.com/_ryuu_chan_/status/1355895692581998592",
             "note": "пост на X открыть не удалось (нужен вход), условий использования не видели; на картинке подпись «Ryuu»; "
                     "по умолчанию права за автором — нужно разрешение"},
    "bigponymac": {"author": "bigponymac", "status": "unknown", "license": None, "source_url": None,
                   "note": "автор — по имени файла от владелицы проекта; профиль и лицензия не проверены"},
    "CosmicUnicorn": {"author": "CosmicUnicorn", "status": "unknown",
                      "license": "на странице автора условий использования нет; у трёх других его работ — CC BY-NC-ND 3.0; "
                                 "для этой картинки не проверено (23.11.2026)",
                      "source_url": "https://www.deviantart.com/cosmicunicorn/",
                      "note": "страницу самой картинки ещё не нашли"},
}


# Первые слова старых имён (до переименования): это не авторы.
LEGACY_FIRST_WORDS = {"peakpx", "wallpaperflare.com_wallpaper.jpg", "sunset", "applejack", "fluttershy", "pinkie",
                      "rainbow", "rarity", "twilight", "midnight", "canterlot", "sci", "equestria", "slide-0.jpg", "slide-8.jpg"}
CONVENTION = re.compile(r"^(\S+) \S.*\.(jpe?g|png|webp)$", re.IGNORECASE)


def author_from_name(name: str) -> dict | None:
    """Известный автор — по списку; любой другой — по соглашению «<Автор> <Персонаж> <номер>».
    Имя чистится от случайных переводов строки и пробелов по краям."""
    name = " ".join(name.split())
    first = name.split(" ", 1)[0]
    if first in FILENAME_AUTHORS:
        return FILENAME_AUTHORS[first]
    if CONVENTION.match(name) and first.lower() not in LEGACY_FIRST_WORDS and first.lower().split(".")[0] != "peakpx":
        return {"author": first, "status": "unknown", "license": None, "source_url": None,
                "note": "автор — по имени файла от владелицы проекта; источник и лицензия не проверены"}
    return None


def apply_author(entry: dict, info: dict) -> None:
    entry.update(author=info["author"], license=info["license"], status=info["status"])
    if info.get("source_url") and not entry.get("source_url"):
        entry["source_url"] = info["source_url"]
        entry["source"] = entry.get("source") or "deviantart.com"
    stale = (entry.get("note") or "").startswith("сайт-агрегатор;")   # автоматическая догадка, автор теперь известен
    if info.get("note") and (not entry.get("note") or stale):
        entry["note"] = info["note"]


def guess_source(name: str) -> tuple[str | None, str]:
    """Подсказка об источнике по имени файла. Это догадка, а не установленный факт."""
    low = name.lower()
    if re.fullmatch(r"peakpx( \(\d+\))?\.jpe?g", low):
        return "peakpx.com", "сайт-агрегатор; первоисточник и автор не указаны"
    if low.startswith("wallpaperflare.com"):
        return "wallpaperflare.com", "сайт-агрегатор; первоисточник и автор не указаны"
    m = re.match(r"^(d[0-9a-z]{5,7})-[0-9a-f]{8}-", low)
    if m:
        return "deviantart.com", f"имя в стиле DeviantArt (ID {m.group(1)}); автор в имени не указан"
    m = re.search(r"_by_([a-z0-9-]+)_d[0-9a-z]{5,7}\.", low)
    if m:
        return "deviantart.com", f"в имени файла указан автор: {m.group(1)} (проверить на сайте)"
    return None, ""


def scan() -> list[str]:
    files = []
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                files.append(path.relative_to(ROOT).as_posix())
    return files


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def new_entry(rel: str) -> dict:
    source, note = guess_source(Path(rel).name)
    entry = {"author": None, "source": source, "source_url": None, "license": None,
             "status": "unknown", "note": note}
    by_name = author_from_name(Path(rel).name)
    if by_name:
        apply_author(entry, by_name)
    if rel == "MLP Cutiemarks/Equestria_OS.png":
        entry.update(author="Equestria OS", source="логотип системы (equestria-os-branding)",
                     license="свой материал проекта", status="own", note="")
    if rel == "Wallpapers/Canterlot/Equestria-EverFree.jpg":
        entry["note"] = "в имени — Equestria Girls / Everfree; первоисточник не подтверждён"
    if rel == "Wallpapers/Canterlot/slide-0.jpg":
        entry.update(source="wallpaperflare.com", note="ночной замок, на картинке подпись «CANTERLOT»; автор не найден")
    if rel == "Wallpapers/Canterlot/slide-8.jpg":
        entry["note"] = "замок на скале (живопись); скачано без названия сайта, автор не найден"
    return entry


def sync(data: dict, found: dict[str, str]) -> tuple[dict, list, list, list]:
    """Привести записи в соответствие с файлами. found: путь -> md5.
    Возвращает (данные, добавленные, убранные, переименованные)."""
    data = {k: dict(v) for k, v in data.items()}
    for rel, digest in found.items():          # у старых записей md5 ещё нет — дописать
        if rel in data and not data[rel].get("md5"):
            data[rel]["md5"] = digest
    missing = [r for r in found if r not in data]
    ghosts = {k: v for k, v in data.items() if k not in found}
    ghost_by_md5 = {v["md5"]: k for k, v in ghosts.items() if v.get("md5")}
    added, renamed = [], []
    for rel in missing:
        old = ghost_by_md5.pop(found[rel], None)
        if old:                                  # тот же файл под новым именем: данные сохраняются
            data[rel] = data.pop(old)
            ghosts.pop(old)
            renamed.append((old, rel))
            by_name = author_from_name(Path(rel).name)
            if by_name and not data[rel].get("author"):
                apply_author(data[rel], by_name)
        else:
            data[rel] = new_entry(rel)
            data[rel]["md5"] = found[rel]
            added.append(rel)
    for k in ghosts:                             # файла нет и найти его по содержимому нельзя
        data.pop(k, None)
    for rel, entry in data.items():              # автор из имени файла, если в записи его ещё нет
        by_name = author_from_name(Path(rel).name)
        if by_name and not entry.get("author"):
            apply_author(entry, by_name)
    return data, added, list(ghosts), renamed


def load() -> dict:
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def render(data: dict) -> str:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for rel in data:
        if (ROOT / rel).is_file():
            by_hash[md5(ROOT / rel)].append(rel)
    dup_of = {rel: [o for o in group if o != rel] for group in by_hash.values() if len(group) > 1 for rel in group}

    counts: dict[str, int] = defaultdict(int)
    for e in data.values():
        counts[e.get("status", "unknown")] += 1
    lines = ["# Картинки темы: авторы и лицензии", "",
             "Файл собирается из `credits.json` командой `python3 tools/credits.py`. Правьте `credits.json`,",
             "а не эту таблицу. Пустое поле значит «не установлено», а не «свободно».", "",
             "**Почему это важно.** Сайты-агрегаторы (peakpx, Wallpaper Flare) раздают картинки, но не владеют ими:",
             "«бесплатно для личного пользования» относится к их сервису, права остаются у автора.",
             "Имя файла: `<Автор> <Персонаж> <номер>` (например, `Hasbro Rarity.png`); запись следует за содержимым, а не за именем.", "",
             "Публиковать (в ISO, в архивах тем) можно только картинки со статусом `free`, `permission` или `own`;",
             "`proprietary` — это чужие защищённые материалы (например, кадры сериала): автор указан, но разрешения нет.", "",
             "## Итого", ""]
    for status, text in STATUSES.items():
        lines.append(f"- `{status}` — {text}: **{counts.get(status, 0)}**")
    lines += ["", f"Всего картинок: **{len(data)}**. Повторяющихся (одно изображение в нескольких папках): "
                  f"**{sum(1 for r in dup_of)}** файлов.", ""]
    groups: dict[str, list[str]] = defaultdict(list)
    for rel in sorted(data):
        parts = rel.split("/")
        groups[f"{parts[0]} / {parts[1]}" if len(parts) > 2 else parts[0]].append(rel)
    for title, rels in groups.items():
        lines += [f"## {title}", "", "| Файл | Источник | Автор | Лицензия | Статус | Заметка |", "|---|---|---|---|---|---|"]
        for rel in rels:
            e = data[rel]
            note = e.get("note") or ""
            if rel in dup_of:
                note = (note + "; " if note else "") + "то же изображение: " + ", ".join(dup_of[rel][:3]) + ("…" if len(dup_of[rel]) > 3 else "")
            src = e.get("source") or "—"
            if e.get("source_url"):
                src = f"[{src}]({e['source_url']})"
            cells = [f"`{Path(rel).name}`", src, e.get("author") or "—", e.get("license") or "—",
                     f"`{e.get('status', 'unknown')}`", note.replace("|", "/")]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    found = {rel: md5(ROOT / rel) for rel in scan()}
    data, added, ghosts, renamed = sync(load(), found)
    if args.check:
        for f in added:
            print("нет записи:", f)
        for k in ghosts:
            print("файла нет:", k)
        for old, new in renamed:
            print("переименован:", old, "->", new, "(запустите tools/credits.py)")
        return 1 if (added or ghosts or renamed) else 0
    DATA.write_text(json.dumps(dict(sorted(data.items())), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT.write_text(render(data), encoding="utf-8")
    print(f"картинок: {len(data)}, добавлено: {len(added)}, переименовано: {len(renamed)}, убрано: {len(ghosts)}")
    for old, new in renamed:
        print("  переименован:", old, "->", new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
