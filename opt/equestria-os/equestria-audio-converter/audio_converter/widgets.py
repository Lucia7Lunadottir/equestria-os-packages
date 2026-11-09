"""Мелкие общие виджеты."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QComboBox, QListWidget


from ._kit import tr
from .localization import catalog


def combo(items, current: str | None = None) -> QComboBox:
    c = QComboBox()
    c.setMinimumHeight(34)
    # длинные пункты («Подкаст и голос — …») не должны раздвигать окно вбок
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(6)
    for key in items:
        c.addItem(tr(key), key)
    pick_text(c, current)
    return c


def pick_data(box: QComboBox, value) -> None:
    """Выбрать пункт по данным; если такого нет — оставить как есть."""
    i = box.findData(value)
    if i >= 0:
        box.setCurrentIndex(i)


def pick_text(box: QComboBox, value) -> None:
    # Accept old settings that stored a translated label, then persist stable keys.
    for i in range(box.count()):
        key = box.itemData(i)
        if value == key or value == box.itemText(i) or any(
            entries.get(key) == value for entries in catalog.translations.values()
            if key is not None and value is not None
        ):
            box.setCurrentIndex(i)
            return


def set_error(widget, bad: bool) -> None:
    """Подсветить поле красным (свойство error в QSS)."""
    widget.setProperty("error", bad)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class DropList(QListWidget):
    """Список файлов, в который можно перетащить файлы мышью."""
    dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, e) -> None:
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dragMoveEvent(self, e) -> None:
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dropEvent(self, e) -> None:
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
            e.acceptProposedAction()
