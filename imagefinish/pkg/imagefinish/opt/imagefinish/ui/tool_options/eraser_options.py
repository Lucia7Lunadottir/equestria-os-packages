from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel,
                             QSlider, QSpinBox)
from PyQt6.QtCore import Qt
from .base_options import BaseOptions


def _hslider(minimum: int, maximum: int, value: int) -> QSlider:
    s = QSlider(Qt.Orientation.Horizontal)
    s.setMinimum(minimum)
    s.setMaximum(maximum)
    s.setValue(value)
    s.setFixedWidth(120)
    return s


class EraserOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.setSpacing(14)

        sl = _hslider(1, 200, 20)
        sp = QSpinBox()
        sp.setRange(1, 200)
        sp.setValue(20)
        sl.valueChanged.connect(sp.setValue)
        sp.valueChanged.connect(sl.setValue)
        sp.valueChanged.connect(lambda v: self.option_changed.emit("brush_size", v))

        self.layout.addWidget(self._lbl("opts.size"))
        self.layout.addWidget(sl)
        self.layout.addWidget(sp)
        self.layout.addStretch()
