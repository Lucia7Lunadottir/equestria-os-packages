from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel,
                             QSpinBox, QCheckBox)
from PyQt6.QtCore import Qt
from .base_options import BaseOptions
from core.locale import tr
from ui.adjustments_dialog import _JumpSlider


def _hslider(minimum: int, maximum: int, value: int):
    s = _JumpSlider(Qt.Orientation.Horizontal)
    s.setMinimum(minimum)
    s.setMaximum(maximum)
    s.setValue(value)
    s.setFixedWidth(120)
    return s


class FillOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.setSpacing(14)

        self._sl = _hslider(0, 255, 32)
        self._sp = QSpinBox()
        self._sp.setRange(0, 255)
        self._sp.setValue(32)
        self._sl.valueChanged.connect(self._sp.setValue)
        self._sp.valueChanged.connect(self._sl.setValue)
        self._sp.valueChanged.connect(lambda v: self.option_changed.emit("fill_tolerance", v))

        self._contiguous_cb = QCheckBox(tr("opts.contiguous"))
        self._contiguous_cb.setChecked(True)
        self._contiguous_cb.toggled.connect(lambda v: self.option_changed.emit("fill_contiguous", v))

        self.layout.addWidget(self._lbl("opts.tolerance"))
        self.layout.addWidget(self._sl)
        self.layout.addWidget(self._sp)
        self.layout.addWidget(self._contiguous_cb)
        self.layout.addStretch()

    def update_from_opts(self, opts: dict):
        for w in [self._sl, self._sp, self._contiguous_cb]:
            w.blockSignals(True)

        tol = opts.get("fill_tolerance", 32)
        self._sl.setValue(tol)
        self._sp.setValue(tol)
        self._contiguous_cb.setChecked(bool(opts.get("fill_contiguous", True)))

        for w in [self._sl, self._sp, self._contiguous_cb]:
            w.blockSignals(False)

    def retranslate(self):
        self._contiguous_cb.setText(tr("opts.contiguous"))
        if hasattr(super(), "retranslate"):
            super().retranslate()
