"""
hsv_picker.py — Красивый кастомный HSV Color Picker.

Содержит:
  - HueSaturationMap   : квадратное поле Saturation (X) × Value (Y) для выбранного Hue
  - HueSlider          : вертикальная/горизонтальная радуга для выбора Hue
  - AlphaSlider        : ползунок прозрачности
  - ColorPickerDialog  : полный диалог с превью, hex-полем и числовыми полями HSV/RGB
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QSpinBox, QPushButton, QWidget,
                             QDialogButtonBox, QSizePolicy)
from PyQt6.QtCore    import Qt, QPoint, QRect, pyqtSignal, QSize
from PyQt6.QtGui     import (QPainter, QColor, QLinearGradient, QConicalGradient,
                             QRadialGradient, QImage, QPixmap, QPen, QBrush)
import math


# ─────────────────────────────────────────────────────────────────────────────
class HueSaturationMap(QWidget):
    """
    Квадрат: ось X = Saturation (0→1), ось Y = Value (1→0 сверху вниз).
    Hue задаётся снаружи. Клик/перетаскивание меняет S и V.
    """
    sv_changed = pyqtSignal(float, float)   # (saturation, value)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue   = 0.0
        self._sat   = 1.0
        self._val   = 1.0
        self.setFixedSize(220, 220)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._cache: QPixmap | None = None
        self._cache_hue: float = -1.0

    # ── Public ────────────────────────────────────────────────────────────────
    def set_hue(self, hue: float):
        if abs(hue - self._hue) > 0.001:
            self._hue = hue
            self._cache = None
            self.update()

    def set_sv(self, s: float, v: float):
        self._sat = s
        self._val = v
        self.update()

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _build_cache(self):
        """
        Строим карту S×V двумя градиентами поверх базового цвета — без
        Python-цикла по пикселям, работает мгновенно.

        1. Заливаем чистым Hue-цветом (S=1, V=1).
        2. Белый градиент слева-направо (белый→прозрачный) = ось Saturation.
        3. Чёрный градиент снизу-вверх (чёрный→прозрачный) = ось Value.
        """
        w, h = self.width(), self.height()
        pix = QPixmap(w, h)

        p = QPainter(pix)

        # 1. Base hue
        base = QColor.fromHsvF(self._hue, 1.0, 1.0)
        p.fillRect(0, 0, w, h, base)

        # 2. White → transparent (left to right) → adds white = lowers saturation
        white_grad = QLinearGradient(0, 0, w, 0)
        white_grad.setColorAt(0, QColor(255, 255, 255, 255))
        white_grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(0, 0, w, h, white_grad)

        # 3. Transparent → black (top to bottom) → lowers value
        black_grad = QLinearGradient(0, 0, 0, h)
        black_grad.setColorAt(0, QColor(0, 0, 0, 0))
        black_grad.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(0, 0, w, h, black_grad)

        p.end()
        self._cache = pix
        self._cache_hue = self._hue

    def paintEvent(self, _e):
        if self._cache is None or self._cache_hue != self._hue:
            self._build_cache()

        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        # cursor circle
        cx = int(self._sat  * (self.width()  - 1))
        cy = int((1.0 - self._val) * (self.height() - 1))
        pen_out = QPen(Qt.GlobalColor.black, 2)
        pen_in  = QPen(Qt.GlobalColor.white, 1)
        p.setPen(pen_out)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPoint(cx, cy), 7, 7)
        p.setPen(pen_in)
        p.drawEllipse(QPoint(cx, cy), 6, 6)
        p.end()

    # ── Mouse ─────────────────────────────────────────────────────────────────
    def _update_from_pos(self, pos: QPoint):
        s = max(0.0, min(1.0, pos.x() / (self.width()  - 1)))
        v = max(0.0, min(1.0, 1.0 - pos.y() / (self.height() - 1)))
        self._sat, self._val = s, v
        self.update()
        self.sv_changed.emit(s, v)

    def mousePressEvent(self, e):
        self._update_from_pos(e.pos())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._update_from_pos(e.pos())


# ─────────────────────────────────────────────────────────────────────────────
class HueSlider(QWidget):
    """Горизонтальная полоса всех оттенков (0–360°)."""
    hue_changed = pyqtSignal(float)   # 0.0 – 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def set_hue(self, h: float):
        self._hue = h
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rainbow gradient
        grad = QLinearGradient(0, 0, self.width(), 0)
        for stop in range(7):
            grad.setColorAt(stop / 6, QColor.fromHsvF(stop / 6, 1.0, 1.0))
        p.fillRect(self.rect(), grad)

        # Border
        p.setPen(QPen(QColor(40, 40, 60), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Cursor
        cx = int(self._hue * (self.width() - 1))
        p.setPen(QPen(Qt.GlobalColor.black, 2))
        p.drawLine(cx, 0, cx, self.height())
        p.setPen(QPen(Qt.GlobalColor.white, 1))
        p.drawLine(cx, 1, cx, self.height() - 1)
        p.end()

    def _update_from_x(self, x: int):
        h = max(0.0, min(1.0, x / (self.width() - 1)))
        # clamp to avoid 1.0 which wraps back to red
        h = min(h, 0.9999)
        self._hue = h
        self.update()
        self.hue_changed.emit(h)

    def mousePressEvent(self, e):
        self._update_from_x(e.pos().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._update_from_x(e.pos().x())


# ─────────────────────────────────────────────────────────────────────────────
class AlphaSlider(QWidget):
    """Ползунок прозрачности (0–255) с шахматной подложкой."""
    alpha_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alpha = 255
        self._color = QColor(255, 0, 0)
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def set_color(self, c: QColor):
        self._color = c
        self.update()

    def set_alpha(self, a: int):
        self._alpha = a
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)

        # Checker
        tile = 8
        for tx in range(0, self.width(), tile):
            for ty in range(0, self.height(), tile):
                shade = QColor(200, 200, 200) if (tx // tile + ty // tile) % 2 == 0 else QColor(240, 240, 240)
                p.fillRect(tx, ty, tile, tile, shade)

        # Color gradient transparent→opaque
        c_transp = QColor(self._color)
        c_transp.setAlpha(0)
        c_opaque = QColor(self._color)
        c_opaque.setAlpha(255)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0, c_transp)
        grad.setColorAt(1, c_opaque)
        p.fillRect(self.rect(), grad)

        p.setPen(QPen(QColor(40, 40, 60), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        cx = int(self._alpha / 255 * (self.width() - 1))
        p.setPen(QPen(Qt.GlobalColor.black, 2))
        p.drawLine(cx, 0, cx, self.height())
        p.setPen(QPen(Qt.GlobalColor.white, 1))
        p.drawLine(cx, 1, cx, self.height() - 1)
        p.end()

    def _update_from_x(self, x: int):
        a = max(0, min(255, int(x / (self.width() - 1) * 255)))
        self._alpha = a
        self.update()
        self.alpha_changed.emit(a)

    def mousePressEvent(self, e):
        self._update_from_x(e.pos().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._update_from_x(e.pos().x())


# ─────────────────────────────────────────────────────────────────────────────
class ColorPreview(QWidget):
    """Прямоугольник «старый цвет | новый цвет» с шахматной подложкой."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._old = QColor(0, 0, 0)
        self._new = QColor(0, 0, 0)
        self.setFixedHeight(32)

    def set_old(self, c: QColor): self._old = c; self.update()
    def set_new(self, c: QColor): self._new = c; self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        w = self.width()
        tile = 8
        for side, color, x0 in [("old", self._old, 0), ("new", self._new, w // 2)]:
            for tx in range(x0, x0 + w // 2, tile):
                for ty in range(0, self.height(), tile):
                    shade = QColor(200, 200, 200) if ((tx - x0) // tile + ty // tile) % 2 == 0 else QColor(240, 240, 240)
                    p.fillRect(tx, ty, tile, tile, shade)
            p.fillRect(x0, 0, w // 2, self.height(), color)
        p.setPen(QPen(QColor(40, 40, 60), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.drawLine(w // 2, 0, w // 2, self.height())
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
def _spin(lo: int, hi: int, val: int, width: int = 58) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(val)
    s.setFixedWidth(width)
    return s


def _label(text: str) -> QLabel:
    l = QLabel(text)
    l.setFixedWidth(22)
    l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    l.setStyleSheet("color: #a6adc8; font-size: 12px;")
    return l


# ─────────────────────────────────────────────────────────────────────────────
class ColorPickerDialog(QDialog):
    """
    Полный HSV color picker.
    Использование:
        dlg = ColorPickerDialog(initial_color, parent)
        if dlg.exec():
            color = dlg.color()
    """

    def __init__(self, initial: QColor = None, parent=None, title: str = "Pick Color"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(270, 460)

        if initial is None:
            initial = QColor(0, 0, 0)
        self._color = QColor(initial)
        self._old_color = QColor(initial)
        self._updating = False

        self._build_ui()
        self._load_color(self._color)

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # SV map
        self._sv_map = HueSaturationMap()
        self._sv_map.sv_changed.connect(self._on_sv_changed)
        root.addWidget(self._sv_map, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Hue slider
        root.addWidget(QLabel("Hue", styleSheet="color:#a6adc8;font-size:11px;"))
        self._hue_slider = HueSlider()
        self._hue_slider.hue_changed.connect(self._on_hue_changed)
        root.addWidget(self._hue_slider)

        # Alpha slider
        root.addWidget(QLabel("Alpha", styleSheet="color:#a6adc8;font-size:11px;"))
        self._alpha_slider = AlphaSlider()
        self._alpha_slider.alpha_changed.connect(self._on_alpha_changed)
        root.addWidget(self._alpha_slider)

        # Preview
        self._preview = ColorPreview()
        self._preview.set_old(self._old_color)
        root.addWidget(self._preview)

        # ── HSV row ───────────────────────────────────────────────────────────
        hsv_row = QHBoxLayout()
        hsv_row.setSpacing(4)
        self._spin_h = _spin(0, 359, 0)
        self._spin_s = _spin(0, 255, 0)
        self._spin_v = _spin(0, 255, 255)
        for lbl, sp in [("H", self._spin_h), ("S", self._spin_s), ("V", self._spin_v)]:
            hsv_row.addWidget(_label(lbl))
            hsv_row.addWidget(sp)
        hsv_row.addStretch()
        root.addLayout(hsv_row)

        # ── RGB row ───────────────────────────────────────────────────────────
        rgb_row = QHBoxLayout()
        rgb_row.setSpacing(4)
        self._spin_r = _spin(0, 255, 0)
        self._spin_g = _spin(0, 255, 0)
        self._spin_b = _spin(0, 255, 0)
        for lbl, sp in [("R", self._spin_r), ("G", self._spin_g), ("B", self._spin_b)]:
            rgb_row.addWidget(_label(lbl))
            rgb_row.addWidget(sp)
        rgb_row.addStretch()
        root.addLayout(rgb_row)

        # ── Alpha + Hex row ───────────────────────────────────────────────────
        hex_row = QHBoxLayout()
        hex_row.setSpacing(4)
        self._spin_a = _spin(0, 255, 255)
        hex_row.addWidget(_label("A"))
        hex_row.addWidget(self._spin_a)
        hex_row.addSpacing(8)
        hex_label = QLabel("#")
        hex_label.setStyleSheet("color:#a6adc8; font-size:13px;")
        self._hex_edit = QLineEdit()
        self._hex_edit.setMaxLength(8)
        self._hex_edit.setFixedWidth(80)
        self._hex_edit.setPlaceholderText("RRGGBBAA")
        hex_row.addWidget(hex_label)
        hex_row.addWidget(self._hex_edit)
        hex_row.addStretch()
        root.addLayout(hex_row)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        # Wire spin/hex signals
        self._spin_h.valueChanged.connect(self._on_hsv_spin)
        self._spin_s.valueChanged.connect(self._on_hsv_spin)
        self._spin_v.valueChanged.connect(self._on_hsv_spin)
        self._spin_r.valueChanged.connect(self._on_rgb_spin)
        self._spin_g.valueChanged.connect(self._on_rgb_spin)
        self._spin_b.valueChanged.connect(self._on_rgb_spin)
        self._spin_a.valueChanged.connect(self._on_alpha_spin)
        self._hex_edit.editingFinished.connect(self._on_hex_edit)

    # ── Load a colour into all widgets ───────────────────────────────────────
    def _load_color(self, c: QColor):
        self._updating = True
        h, s, v, a = c.hsvHue(), c.hsvSaturation(), c.value(), c.alpha()
        if h < 0:
            h = 0  # achromatic

        self._sv_map.set_hue(h / 359.0)
        self._sv_map.set_sv(s / 255.0, v / 255.0)
        self._hue_slider.set_hue(h / 359.0)
        self._alpha_slider.set_color(c)
        self._alpha_slider.set_alpha(a)
        self._preview.set_new(c)

        self._spin_h.setValue(h)
        self._spin_s.setValue(s)
        self._spin_v.setValue(v)
        self._spin_r.setValue(c.red())
        self._spin_g.setValue(c.green())
        self._spin_b.setValue(c.blue())
        self._spin_a.setValue(a)

        hex_str = f"{c.red():02X}{c.green():02X}{c.blue():02X}"
        if a < 255:
            hex_str += f"{a:02X}"
        self._hex_edit.setText(hex_str)
        self._updating = False

    def _apply(self, c: QColor):
        self._color = c
        self._load_color(c)

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_hue_changed(self, h: float):
        if self._updating:
            return
        c = QColor.fromHsvF(h, self._color.hsvSaturationF(),
                            self._color.valueF(), self._color.alphaF())
        self._apply(c)

    def _on_sv_changed(self, s: float, v: float):
        if self._updating:
            return
        hue = self._color.hsvHueF()
        if hue < 0:
            hue = 0.0
        c = QColor.fromHsvF(hue, s, v, self._color.alphaF())
        self._apply(c)

    def _on_alpha_changed(self, a: int):
        if self._updating:
            return
        c = QColor(self._color)
        c.setAlpha(a)
        self._apply(c)

    def _on_hsv_spin(self):
        if self._updating:
            return
        c = QColor.fromHsv(self._spin_h.value(), self._spin_s.value(),
                           self._spin_v.value(), self._spin_a.value())
        self._apply(c)

    def _on_rgb_spin(self):
        if self._updating:
            return
        c = QColor(self._spin_r.value(), self._spin_g.value(),
                   self._spin_b.value(), self._spin_a.value())
        self._apply(c)

    def _on_alpha_spin(self):
        if self._updating:
            return
        c = QColor(self._color)
        c.setAlpha(self._spin_a.value())
        self._apply(c)

    def _on_hex_edit(self):
        if self._updating:
            return
        text = self._hex_edit.text().strip().lstrip("#")
        try:
            if len(text) == 6:
                r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
                c = QColor(r, g, b, self._color.alpha())
            elif len(text) == 8:
                r, g, b, a = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), int(text[6:8], 16)
                c = QColor(r, g, b, a)
            else:
                return
            self._apply(c)
        except ValueError:
            pass

    # ── Result ────────────────────────────────────────────────────────────────
    def color(self) -> QColor:
        return self._color

    # ── Static helper ─────────────────────────────────────────────────────────
    @staticmethod
    def get_color(initial: QColor = None, parent=None, title: str = "Pick Color") -> QColor | None:
        """Returns picked QColor or None if cancelled."""
        dlg = ColorPickerDialog(initial, parent, title)
        if dlg.exec():
            return dlg.color()
        return None
