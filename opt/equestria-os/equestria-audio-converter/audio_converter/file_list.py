"""Панель «Файлы»: список, кнопки, подсказка."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidgetItem, QPushButton,
                             QVBoxLayout, QWidget)

from ._kit import tr
from .widgets import DropList

MEDIA_EXT = "mp3 wav flac ogg opus m4a aac wma aiff mp4 mkv avi mov webm flv wmv m4v ts"


def to_local_path(arg: str) -> str:
    """Аргумент командной строки (путь или file://…) -> абсолютный путь."""
    if arg.startswith("file://"):
        return QUrl(arg).toLocalFile()
    return str(Path(arg).expanduser().resolve())


class FileList(QWidget):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.list = DropList()
        self.list.setMinimumHeight(150)
        self.list.dropped.connect(self.add_files)
        add = QPushButton(tr("file_list.add_files"))
        add.clicked.connect(self._pick)
        rm = QPushButton(tr("common.remove"))
        rm.clicked.connect(self._remove_selected)
        clr = QPushButton(tr("file_list.clear"))
        clr.clicked.connect(self.clear)
        row = QHBoxLayout()
        row.addWidget(add, 1)
        row.addWidget(rm)
        row.addWidget(clr)
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.list)
        v.addLayout(row)
        v.addWidget(self.hint)
        self._refresh()

    def count(self) -> int:
        return self.list.count()

    def item(self, i: int) -> QListWidgetItem:
        return self.list.item(i)

    def path(self, i: int) -> str:
        return self.list.item(i).data(Qt.ItemDataRole.UserRole)

    def add_files(self, paths) -> None:
        have = {self.path(i) for i in range(self.count())}
        for p in paths:
            if p in have or not Path(p).is_file():
                continue
            it = QListWidgetItem(Path(p).name)
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            self.list.addItem(it)
            have.add(p)
        self._refresh()

    def clear(self) -> None:
        self.list.clear()
        self._refresh()

    def _pick(self) -> None:
        exts = " ".join(f"*.{e}" for e in MEDIA_EXT.split())
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("file_list.choose_files"), str(Path.home()), tr("file_list.audio_video_all_files", exts))
        self.add_files(paths)

    def _remove_selected(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self._refresh()

    def _refresh(self) -> None:
        n = self.count()
        self.hint.setText(tr("file_list.files", n) if n else
                          tr("file_list.drag_files_here_press_add"))
        self.changed.emit()
