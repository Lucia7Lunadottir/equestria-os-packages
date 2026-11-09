"""calc: widgets."""
from __future__ import annotations

import re
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget
)
from .localization import live_i18n, tr


def mk(text, name="", cb=None, expand=True, h=44) -> QPushButton:
    b = live_i18n.call(QPushButton, text)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if name:
        b.setObjectName(name)
    if expand:
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        b.setMinimumHeight(h)
    if cb:
        b.clicked.connect(lambda _=False, t=text: cb(t))
    return b


def fit(label: QLabel, text: str, error: bool = False, px: int = 44) -> None:
    n = len(text)
    size = px if n <= 11 else int(px * .7) if n <= 16 else int(px * .5) if n <= 26 else int(px * .36)
    label.setProperty("error", error)
    label.setStyleSheet(f"font-size: {size}px;")
    label.style().unpolish(label)
    label.style().polish(label)
    live_i18n.call(label.setText, text)


def right_label(name: str, minh: int) -> QLabel:
    lab = live_i18n.call(QLabel, "")
    lab.setObjectName(name)
    lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lab.setMinimumHeight(minh)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return lab


def single_group(e: str) -> bool:
    """Строка вида −( … ) — одна скобочная группа целиком."""
    if not (e.startswith("−(") and e.endswith(")")):
        return False
    depth = 0
    for i, ch in enumerate(e[1:], 1):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0 and i != len(e) - 1:
            return False
    return depth == 0


def toggle_neg(e: str, num: str) -> str:
    if single_group(e):
        return e[2:-1]
    if re.fullmatch(num, e):
        return "−" + e
    if re.fullmatch("−" + num, e):
        return e[1:]
    return f"−({e})"


class HistoryPanel(QWidget):
    picked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.list = QListWidget()
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(lambda it: self.picked.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.empty = live_i18n.call(QLabel, tr("widgets.history_empty"))
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clear_btn = mk(tr("widgets.clear_history"), "small", expand=False)
        self.clear_btn.clicked.connect(self.clear)
        v.addWidget(self.list, 1)
        v.addWidget(self.empty, 1)
        v.addWidget(self.clear_btn)
        self._sync()

    def add(self, text: str, result: str) -> None:
        it = live_i18n.call(QListWidgetItem, text)
        it.setData(Qt.ItemDataRole.UserRole, result)
        self.list.insertItem(0, it)
        self._sync()

    def clear(self) -> None:
        self.list.clear()
        self._sync()

    def _sync(self) -> None:
        has = self.list.count() > 0
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        self.clear_btn.setEnabled(has)


class PageBase(QWidget):
    """Общее для экранов: текст результата для Ctrl+C и обработка клавиш."""
    pref = (420, 700)
    minimum = (360, 600)

    def copy_text(self) -> str | None:
        return None

    def key(self, e) -> bool:
        return False
