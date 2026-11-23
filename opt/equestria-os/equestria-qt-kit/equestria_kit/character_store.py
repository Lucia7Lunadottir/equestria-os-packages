# -*- coding: utf-8 -*-
"""
Хранилище тем персонажей: один JSON-файл на персонажа (drop-in каталоги).

Порядок карточек: сначала встроенные (по имени файла; файлы без номера — после пронумерованных,
по алфавиту), затем свои персонажи пользователя (по имени файла, то есть по номеру создания).
Раскладка (системная часть — от пакета, пользовательская — в домашней папке):

    <система>/characters.d/NN-<id>.json   встроенные персонажи (и персонажи из других пакетов);
                                          порядок карточек — по имени файла, Id — внутри файла
    <пользователь>/characters.d/<id>.json правки встроенных персонажей;
    <пользователь>/characters.d/NN-<id>.json  свои персонажи (номер = порядок создания)

Файл пользователя хранит только ПРАВКИ: поля, которые отличаются от системного
персонажа с тем же Id. Поэтому обновление пакета (новые поля, новые цвета) доходит
до пользователя, а не перекрывается устаревшей полной копией. Значение null в
правке означает «поля нет» (например, пользователь сбросил выбор). Встроенного
персонажа, которого пользователь удалил, помечает файл {"Id": "...", "Deleted": true}.

Старый формат — один общий characters.json со списком "Characters" — по-прежнему
читается, и в системной, и в пользовательской папке (чужие установки, старые версии).
Пользовательский characters.json считается полной копией и сохраняет прежний смысл:
набор персонажей определяет он, а недостающие поля берутся из системных.
Конвертация в новый формат — CharacterStore.migrate_legacy(); старый файл при этом
не удаляется, а переименовывается (characters.json.pre-split). Читатели ничего не
записывают и не конвертируют: это делает только программа-владелец (переключатель тем).

Модуль не зависит от Qt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

LEGACY_FILE = "characters.json"
DROPIN_DIR = "characters.d"
BACKUP_SUFFIX = ".pre-split"

# Встроенные персонажи, которые существовали до разделения файла. Только про них старый полный
# файл пользователя может «сказать», что их удалили: персонажа, добавленного позже, в нём просто
# ещё не было, и скрывать его нельзя.
PRE_SPLIT_BUILTINS = ("sunset", "twilight", "rainbow", "rarity", "pinkie", "applejack", "fluttershy")

DEFAULT_USER_DIR = Path.home() / ".local/share/EquestriaOS/Themes"
DEFAULT_SYSTEM_DIR = Path("/opt/equestria-os/equestria-os-character-theme")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _legacy_entries(path: Path) -> list[dict] | None:
    """Список персонажей из старого общего файла; None — файла нет или он битый."""
    data = _read_json(path)
    chars = data.get("Characters") if isinstance(data, dict) else None
    if not isinstance(chars, list):
        return None
    return [c for c in chars if isinstance(c, dict) and c.get("Id")]


def _dropin_entries(folder: Path) -> list[dict]:
    """Все персонажи из каталога characters.d (битые файлы пропускаются, порядок — по имени)."""
    out = []
    try:
        names = sorted(p for p in folder.iterdir() if p.suffix == ".json" and p.is_file())
    except OSError:
        return out
    for path in names:
        data = _read_json(path)
        if isinstance(data, dict) and data.get("Id"):
            out.append(data)
    return out


def _merge(*layers: dict | None) -> dict:
    """Слияние по полям: верхний слой перекрывает нижний; None в значении убирает поле."""
    merged: dict = {}
    for layer in layers:
        for key, value in (layer or {}).items():
            merged[key] = value
    return {k: v for k, v in merged.items() if v is not None and k != "Deleted"}


def _file_name(char_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(char_id)).strip(".") or "character"


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class CharacterStore:
    def __init__(self, user_dir=None, system_dir=None, legacy_deletable=PRE_SPLIT_BUILTINS):
        self.user_dir = Path(user_dir or DEFAULT_USER_DIR)
        self.system_dir = Path(system_dir or DEFAULT_SYSTEM_DIR)
        self.legacy_deletable = frozenset(legacy_deletable)

    # ── пути ─────────────────────────────────────────────────────────────────
    @property
    def user_legacy(self) -> Path:
        return self.user_dir / LEGACY_FILE

    @property
    def user_dropins(self) -> Path:
        return self.user_dir / DROPIN_DIR

    @property
    def system_legacy(self) -> Path:
        return self.system_dir / LEGACY_FILE

    @property
    def system_dropins(self) -> Path:
        return self.system_dir / DROPIN_DIR

    def signature(self) -> tuple:
        """Меняется, когда меняются данные тем или выбор персонажа (для слежки без Qt)."""
        out = []
        for path in (self.user_dir / "state.json", self.user_legacy, self.user_dropins,
                     self.system_legacy, self.system_dropins):
            try:
                out.append(path.stat().st_mtime_ns)
            except OSError:
                out.append(0)
        return tuple(out)

    # ── чтение ───────────────────────────────────────────────────────────────
    def system_characters(self) -> dict[str, dict]:
        """Встроенные персонажи: старый общий файл пакета, поверх — characters.d."""
        base: dict[str, dict] = {}
        for entry in (_legacy_entries(self.system_legacy) or []) + _dropin_entries(self.system_dropins):
            base[str(entry["Id"])] = _merge(base.get(str(entry["Id"])), entry)
        return base

    def system_character(self, char_id: str) -> dict | None:
        """Заводская версия персонажа (без правок пользователя), если он встроенный."""
        return self.system_characters().get(str(char_id))

    def has_legacy_user_file(self) -> bool:
        return _legacy_entries(self.user_legacy) is not None

    def read(self) -> list[dict]:
        """Итоговый список персонажей: системные, поверх — правки пользователя."""
        base = self.system_characters()
        legacy = _legacy_entries(self.user_legacy)
        legacy_by_id = {str(e["Id"]): e for e in (legacy or [])}
        dropins = {str(e["Id"]): e for e in _dropin_entries(self.user_dropins)}
        deleted = {cid for cid, e in dropins.items() if e.get("Deleted")}
        if legacy is not None:
            # Старый полный файл: встроенного, которого в нём нет, удалил пользователь — но только если
            # он существовал, когда файл писали (PRE_SPLIT_BUILTINS); новый встроенный просто ещё не попал в файл.
            deleted |= {cid for cid in base if cid in self.legacy_deletable and cid not in legacy_by_id}
        ids = list(base)
        ids += [i for i in legacy_by_id if i not in base]
        ids += [i for i in dropins if i not in base and i not in legacy_by_id]
        return [_merge(base.get(cid), legacy_by_id.get(cid), dropins.get(cid)) for cid in ids if cid not in deleted]

    # ── запись (только программа-владелец) ───────────────────────────────────
    def write(self, characters: list[dict]) -> None:
        """Сохранить полный список персонажей как правки пользователя. Если ещё остался
        старый общий файл, сначала он конвертируется (иначе он продолжил бы перекрывать)."""
        if self.has_legacy_user_file():
            self.migrate_legacy()
        self._write_dropins(characters)

    def migrate_legacy(self) -> bool:
        """Конвертировать пользовательский characters.json в характеры по файлам.
        Старый файл сохраняется как characters.json.pre-split. True — конвертация была."""
        entries = _legacy_entries(self.user_legacy)
        if entries is None:
            return False     # нет файла или он битый: ничего не трогаем
        # Итог чтения уже учитывает и правки, и удалённых, и новых встроенных; его и записываем.
        self._write_dropins(self.read())
        backup = self.user_legacy.with_name(LEGACY_FILE + BACKUP_SUFFIX)
        if backup.exists():
            backup = backup.with_name(f"{LEGACY_FILE}{BACKUP_SUFFIX}-{time.strftime('%Y%m%d%H%M%S')}")
        os.replace(self.user_legacy, backup)
        return True

    def _write_dropins(self, characters: list[dict]) -> None:
        base = self.system_characters()
        wanted: dict[str, dict] = {}   # id -> содержимое файла правки
        for c in characters:
            cid = str(c.get("Id") or "").strip()
            if not cid:
                continue
            if cid in base:
                override = {k: v for k, v in c.items() if k not in ("Id", "Deleted") and base[cid].get(k) != v}
                override.update({k: None for k in base[cid] if k not in c and k != "Id"})   # поле убрали
                if override:
                    wanted[cid] = {"Id": cid, **override}
            else:
                wanted[cid] = {k: v for k, v in c.items() if k != "Deleted"}
        for cid in base:   # встроенного убрали из списка — пометить удалённым
            if cid not in {str(c.get("Id") or "").strip() for c in characters}:
                wanted[cid] = {"Id": cid, "Deleted": True}

        folder = self.user_dropins
        folder.mkdir(parents=True, exist_ok=True)
        existing = {}                   # id -> путь существующего файла
        for path in sorted(folder.glob("*.json")):
            data = _read_json(path)
            if isinstance(data, dict) and data.get("Id"):
                existing[str(data["Id"])] = path
        for cid, data in wanted.items():
            path = existing.get(cid)
            if path is None:
                # Свой персонаж получает следующий номер: карточки остаются в порядке создания.
                # Правки встроенных порядок не меняют (их место задаёт системный файл).
                numbered = cid not in base
                path = self._free_path(folder, cid, self._next_number(folder) if numbered else None)
                existing[cid] = path
            _write_atomic(path, data)
        for cid, path in existing.items():   # правка больше не нужна — убрать файл
            if cid not in wanted:
                try:
                    path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _next_number(folder: Path) -> int:
        """Следующий номер для файла своего персонажа (шаг 10 — между ними можно вставлять)."""
        used = [int(m.group(1)) for p in folder.glob("*.json") if (m := re.match(r"^(\d+)-", p.name))]
        return (max(used) + 10) if used else 10

    @staticmethod
    def _free_path(folder: Path, char_id: str, number: int | None = None) -> Path:
        stem = _file_name(char_id) if number is None else f"{number:02d}-{_file_name(char_id)}"
        path = folder / f"{stem}.json"
        if not path.exists():
            return path
        suffix = hashlib.sha1(str(char_id).encode("utf-8")).hexdigest()[:6]
        return folder / f"{stem}-{suffix}.json"
