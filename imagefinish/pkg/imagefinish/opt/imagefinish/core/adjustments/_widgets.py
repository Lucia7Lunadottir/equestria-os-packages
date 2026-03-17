"""Shared UI widgets used by multiple adjustment dialogs."""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter

from core.locale import tr
from ui.adjustments_dialog import _JumpSlider


class _FSliderRow(QHBoxLayout):
    """Like _SliderRow but the value label is divided by *divisor* and
    shown with *decimals* decimal places."""

    def __init__(self, label: str, lo: int, hi: int,
                 default: int = 0, divisor: float = 1.0, decimals: int = 0):
        super().__init__()
        self._default  = default
        self._divisor  = divisor
        self._decimals = decimals
        fmt = f"{{:.{decimals}f}}"

        lbl = QLabel(label)
        lbl.setFixedWidth(90)

        self._slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(lo, hi)
        self._slider.setValue(default)

        self._val_lbl = QLabel(fmt.format(default / divisor))
        self._val_lbl.setFixedWidth(48)
        self._val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._slider.valueChanged.connect(
            lambda v: self._val_lbl.setText(fmt.format(v / divisor)))

        self.addWidget(lbl)
        self.addWidget(self._slider)
        self.addWidget(self._val_lbl)

    def value(self) -> float:
        return self._slider.value() / self._divisor

    def reset(self):
        self._slider.blockSignals(True)
        self._slider.setValue(self._default)
        self._slider.blockSignals(False)
        fmt = f"{{:.{self._decimals}f}}"
        self._val_lbl.setText(fmt.format(self._default / self._divisor))

    @property
    def valueChanged(self):
        return self._slider.valueChanged


class _ColorButton(QPushButton):
    """Small button showing a solid colour swatch; click opens QColorDialog."""

    colorChanged = pyqtSignal(QColor)

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self._refresh_style()
        self.setFixedSize(36, 24)
        self.clicked.connect(self._pick)

    def _refresh_style(self):
        c = self._color
        rgba = f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha()})"
        self.setStyleSheet(
            f"QPushButton {{ background-color: {rgba}; border: 1px solid #585b70; border-radius: 3px; }}")

    def _pick(self):
        from ui.hsv_picker import ColorPickerDialog
        c = ColorPickerDialog.get_color(self._color, self.window(), tr("adj.choose_color"))
        if c is not None:
            self._color = c
            self._refresh_style()
            self.colorChanged.emit(c)

    def color(self) -> QColor:
        return self._color

    def set_color(self, c: QColor):
        """Programmatic colour change — does NOT emit colorChanged."""
        self._color = c
        self._refresh_style()


class _GradientPreview(QLabel):
    """Horizontal gradient bar showing shadow→highlight mapping."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shadow    = QColor(0, 0, 0)
        self._highlight = QColor(255, 255, 255)
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_colors(self, shadow: QColor, highlight: QColor):
        self._shadow    = shadow
        self._highlight = highlight
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, self._shadow)
        grad.setColorAt(1.0, self._highlight)
        p.fillRect(self.rect(), grad)
        p.end()
