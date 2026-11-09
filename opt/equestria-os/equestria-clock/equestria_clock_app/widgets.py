"""clock: widgets."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIntValidator, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget
)
from pathlib import Path
from .localization import live_i18n, tr
from .sound import BUILTIN_SOUNDS
from .style import THEME


class Switch(QAbstractButton):
    """Переключатель вкл/выкл."""

    def __init__(self, checked: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(THEME["accent"] if on else THEME["surface2"]))
        p.drawRoundedRect(self.rect(), 13, 13)
        p.setBrush(QColor(THEME["base"] if on else THEME["text"]))
        x = self.width() - 23 if on else 3
        p.drawEllipse(x, 3, 20, 20)


class RingWidget(QWidget):
    """Круг с прогрессом и крупным текстом в середине."""

    def __init__(self):
        super().__init__()
        self.fraction = 1.0
        self.text = "00:00"
        self.sub = ""
        self.color_key = "accent"
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_state(self, fraction, text, sub="", color_key="accent"):
        self.fraction, self.text, self.sub, self.color_key = fraction, text, sub, color_key
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 24
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        pen = QPen(QColor(THEME["surface1"]), max(8.0, side * 0.045))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(rect)
        if self.fraction > 0:
            pen.setColor(QColor(THEME[self.color_key]))
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, -int(360 * 16 * min(1.0, self.fraction)))
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(int(side * (0.2 if len(self.text) <= 5 else 0.14)))
        p.setFont(f)
        p.setPen(QColor(THEME["text"]))
        live_i18n.call(p.drawText, rect, Qt.AlignmentFlag.AlignCenter, self.text)
        if self.sub:
            f2 = QFont(self.font())
            f2.setPixelSize(max(11, int(side * 0.06)))
            p.setFont(f2)
            p.setPen(QColor(THEME["subtext"]))
            live_i18n.call(p.drawText, rect.translated(0, side * 0.17), Qt.AlignmentFlag.AlignCenter, self.sub)


class PadSpin(QSpinBox):
    def textFromValue(self, v: int) -> str:
        return live_i18n.format_text('{0:02d}', v)


class _NumEdit(QLineEdit):
    """Поле числа: колесо мыши и стрелки ↑/↓ меняют значение."""

    def __init__(self, field):
        super().__init__()
        self._field = field

    def wheelEvent(self, e):
        self._field.step(1 if e.angleDelta().y() > 0 else -1)
        e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Up:
            self._field.step(1)
        elif e.key() == Qt.Key.Key_Down:
            self._field.step(-1)
        else:
            super().keyPressEvent(e)


class TimeField(QWidget):
    """Число с кнопками ▲ ▼ (часы, минуты, секунды)."""
    changed = pyqtSignal()

    def __init__(self, maximum: int, wrap: bool = False, caption: str = ""):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        up, down = live_i18n.call(QPushButton, "▲"), live_i18n.call(QPushButton, "▼")
        for b in (up, down):
            b.setObjectName("step")
            b.setAutoRepeat(True)
            b.setAutoRepeatDelay(400)
            b.setAutoRepeatInterval(80)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.maximum = maximum
        self.wrap = wrap
        self.edit = _NumEdit(self)
        self.edit.setObjectName("bigedit")
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setMaxLength(len(str(maximum)))
        self.edit.setValidator(QIntValidator(0, maximum, self))
        live_i18n.call(self.edit.setText, "00")
        self.edit.textEdited.connect(lambda _: self.changed.emit())
        self.edit.editingFinished.connect(lambda: self.setValue(self.value()))
        up.clicked.connect(lambda: self.step(1))
        down.clicked.connect(lambda: self.step(-1))
        v.addWidget(up)
        v.addWidget(self.edit)
        v.addWidget(down)
        if caption:
            c = live_i18n.call(QLabel, caption)
            c.setObjectName("subtle")
            c.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(c)

    def value(self) -> int:
        try:
            return max(0, min(self.maximum, int(self.edit.text() or 0)))
        except ValueError:
            return 0

    def setValue(self, v: int) -> None:
        v = max(0, min(self.maximum, int(v)))
        old = self.edit.text()
        live_i18n.call(self.edit.setText, live_i18n.format_text('{0:02d}', v))
        if old != self.edit.text():
            self.changed.emit()

    def step(self, d: int) -> None:
        v = self.value() + d
        if self.wrap:
            v = 0 if v > self.maximum else (self.maximum if v < 0 else v)
        self.setValue(v)


class SoundPicker(QWidget):
    """Выбор мелодии: встроенные или свой файл + кнопка прослушивания."""
    changed = pyqtSignal()

    def __init__(self, win, allow_default: bool):
        super().__init__()
        self.win = win
        self._previewing = False
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.combo = QComboBox()
        if allow_default:
            live_i18n.call(self.combo.addItem, tr("widgets.as_settings"), "")
        for key, (name, _, _) in BUILTIN_SOUNDS.items():
            live_i18n.call(self.combo.addItem, name, live_i18n.format_text('builtin:{0}', key))
        live_i18n.call(self.combo.addItem, tr("widgets.custom_file"), "__file__")
        self._prev = 0
        self.combo.activated.connect(self._activated)
        self.btn = live_i18n.call(QPushButton, "▶")
        self.btn.setObjectName("icon")
        live_i18n.call(self.btn.setToolTip, tr("widgets.listen"))
        self.btn.clicked.connect(self._preview)
        h.addWidget(self.combo, 1)
        h.addWidget(self.btn)
        win.player.stateChanged.connect(self._state)

    def value(self) -> str:
        v = self.combo.currentData()
        return "" if v == "__file__" else (v or "")

    def _is_custom(self, data) -> bool:
        return bool(data) and not str(data).startswith("builtin:") and data != "__file__"

    def set_value(self, v: str) -> None:
        if self._is_custom(v):
            for i in reversed(range(self.combo.count())):
                if self._is_custom(self.combo.itemData(i)):
                    self.combo.removeItem(i)
            self.combo.insertItem(self.combo.count() - 1, Path(v).name, v)
        idx = self.combo.findData(v)
        self.combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._prev = self.combo.currentIndex()

    def _activated(self, i: int) -> None:
        if self.combo.itemData(i) == "__file__":
            path, _ = QFileDialog.getOpenFileName(
                self, tr("widgets.choose_melody"), str(Path.home()),
                tr("widgets.audio_mp3_ogg_wav_flac"))
            if path:
                self.set_value(path)
            else:
                self.combo.setCurrentIndex(self._prev)
        self._prev = self.combo.currentIndex()
        self.changed.emit()

    def _preview(self) -> None:
        if self._previewing:
            self.win.player.stop()
            return
        self._previewing = True
        live_i18n.call(self.btn.setText, "■")
        self.win.player.play(self.value() or self.win.settings["sound"],
                             self.win.settings["volume"], loop=False)

    def _state(self, playing: bool) -> None:
        if not playing:
            self._previewing = False
        live_i18n.call(self.btn.setText, "■" if (playing and self._previewing) else "▶")


def card_row(title: str, widget: QWidget | None = None, hint: str = "") -> QFrame:
    c = QFrame()
    c.setObjectName("card")
    v = QVBoxLayout(c)
    v.setContentsMargins(18, 14, 18, 14)
    v.setSpacing(8)
    top = QHBoxLayout()
    t = live_i18n.call(QLabel, title)
    t.setObjectName("rowname")
    top.addWidget(t, 1)
    v.addLayout(top)
    if hint:
        h = live_i18n.call(QLabel, hint)
        h.setObjectName("subtle")
        h.setWordWrap(True)
        v.addWidget(h)
    if widget is not None:
        v.addWidget(widget)
    return c
