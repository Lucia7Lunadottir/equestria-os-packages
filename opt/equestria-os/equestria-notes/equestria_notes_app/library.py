"""notes: library."""
from __future__ import annotations

import os
import re
from PyQt6.QtCore import QFile
from .localization import tr
from .markdown import count_tasks
from .paths import EXTS, FILES, GLOBAL
from .storage import note_title, preview_of, read_text, write_text


EMPTY_HINT = tr("library.select_note_left_create_new")


class NoteLibrary:
    """Заметки без интерфейса: источники (папка «Заметки», свои папки, история
    отдельных файлов), список заметок с кэшем и поиском, создание, переименование
    и удаление файлов. Окно (MainWindow) только показывает это и задаёт вопросы."""

    def __init__(self, cfg: dict, gdir):
        self.cfg, self.gdir = cfg, gdir
        self.cache: dict = {}

    # --- источники
    @property
    def source(self) -> str:
        return self.cfg["source"]

    @source.setter
    def source(self, value: str) -> None:
        self.cfg["source"] = value or GLOBAL

    def source_dir(self):
        """Папка текущего источника; None — для истории отдельных файлов."""
        s = self.source
        return str(self.gdir) if s == GLOBAL else (None if s == FILES else s)

    def source_entries(self) -> list:
        """[(подпись, id, подсказка)] для выпадающего списка источников."""
        names: dict = {}
        for p in self.cfg["folders"]:
            names.setdefault(os.path.basename(p.rstrip("/")) or p, []).append(p)
        out = [(tr("library.notes_documents"), GLOBAL, str(self.gdir))]
        for p in self.cfg["folders"]:
            base = os.path.basename(p.rstrip("/")) or p
            label = base if len(names[base]) == 1 else f"{base} ({os.path.basename(os.path.dirname(p.rstrip('/')))})"
            out.append(("⚠ " + label if not os.path.isdir(p) else label, p, p))
        out.append((tr("library.separate_files_history"), FILES, None))
        return out

    def add_folder(self, d: str) -> None:
        d = os.path.normpath(d)
        if os.path.normpath(str(self.gdir)) == d:
            self.source = GLOBAL
        else:
            if d not in self.cfg["folders"]:
                self.cfg["folders"].append(d)
            self.source = d

    def remove_current_folder(self) -> None:
        p = self.source
        self.cfg["folders"] = [f for f in self.cfg["folders"] if f != p]
        self.source = GLOBAL

    def clear_files(self) -> None:
        self.cfg["files"] = []

    def remember_file(self, p: str) -> None:
        self.cfg["files"] = ([p] + [f for f in self.cfg["files"] if f != p])[:100]

    def forget_file(self, p: str) -> None:
        self.cfg["files"] = [f for f in self.cfg["files"] if f != p]

    # --- список заметок
    def info(self, path: str) -> dict:
        try:
            st = os.stat(path)
        except OSError:
            return {"path": path, "title": note_title(path), "missing": True, "mtime": 0, "tasks": (0, 0),
                    "preview": "", "text_l": ""}
        c = self.cache.get(path)
        if c and c[0] == st.st_mtime and c[1] == st.st_size:
            return c[2]
        text = ""
        if st.st_size <= 1_000_000:
            try:
                text = read_text(path)
            except OSError:
                pass
        info = {"path": path, "title": note_title(path), "missing": False, "mtime": st.st_mtime,
                "tasks": count_tasks(text), "preview": preview_of(text), "text_l": text[:200_000].lower()}
        self.cache[path] = (st.st_mtime, st.st_size, info)
        return info

    def notes(self, query: str = "") -> list:
        """Заметки текущего источника (папки — свежие сверху, история — по порядку)."""
        src = self.source
        paths: list = []
        if src == FILES:
            paths = list(self.cfg["files"])
        else:
            d = str(self.gdir) if src == GLOBAL else src
            try:
                for e in os.scandir(d):
                    if e.is_file() and not e.name.startswith(".") and e.name.lower().endswith(EXTS):
                        paths.append(e.path)
            except OSError:
                pass
        infos = [self.info(p) for p in paths]
        if src != FILES:
            infos.sort(key=lambda i: i["mtime"], reverse=True)
        q = query.strip().lower()
        if q:
            infos = [i for i in infos if q in i["title"].lower() or q in i["text_l"]]
        return infos

    # --- файлы
    def create_note(self) -> str:
        """Новая заметка в текущей папке (или в «Заметках»). Путь к файлу; OSError — не вышло."""
        d = self.source_dir()
        if d is None or not os.path.isdir(d):
            d = str(self.gdir)
            self.source = GLOBAL
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        base, n = tr("common.new_note"), 1
        path = os.path.join(d, base + ".md")
        while os.path.exists(path):
            n += 1
            path = os.path.join(d, f"{base} {n}.md")
        write_text(path, tr("library.new_note"))
        return path

    @staticmethod
    def safe_name(name: str) -> str:
        return re.sub(r'[\\/:*?"<>|]', "_", name).strip()

    def rename(self, path: str, new_stem: str) -> str:
        """Переименовать файл; FileExistsError — имя занято, OSError — ошибка ФС."""
        new = os.path.join(os.path.dirname(path), new_stem + os.path.splitext(path)[1])
        if os.path.exists(new):
            raise FileExistsError(new)
        os.rename(path, new)
        self.cfg["files"] = [new if f == path else f for f in self.cfg["files"]]
        if self.cfg.get("last") == path:
            self.cfg["last"] = new
        return new

    def delete(self, path: str) -> None:
        """В корзину, а если корзины нет — удалить (подтверждение спрашивает окно). OSError — не вышло."""
        res = QFile.moveToTrash(path)
        ok = res[0] if isinstance(res, tuple) else bool(res)
        if not ok:
            os.remove(path)
        self.forget_file(path)
