from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel,
                             QSpinBox, QComboBox, QCheckBox)
from PyQt6.QtCore import Qt
from .base_options import BaseOptions
from core.locale import tr
from ui.gradient_editor import GradientPreviewWidget, GradientEditorDialog
from PyQt6.QtGui import QColor
from ui.adjustments_dialog import _JumpSlider


def _hslider(minimum: int, maximum: int, value: int):
    s = _JumpSlider(Qt.Orientation.Horizontal)
    s.setMinimum(minimum)
    s.setMaximum(maximum)
    s.setValue(value)
    s.setFixedWidth(120)
    return s


class GradientOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.setSpacing(14)

        _GTYPE_VALUES = ("linear", "radial")
        _GTYPE_KEYS   = ("opts.gradient.linear", "opts.gradient.radial")
        
        type_combo = QComboBox()
        type_combo.addItems([tr(k) for k in _GTYPE_KEYS])
        type_combo.currentIndexChanged.connect(
            lambda i: self.option_changed.emit(
                "gradient_type", _GTYPE_VALUES[i] if 0 <= i < len(_GTYPE_VALUES) else "linear"))

        self._grad_preview = GradientPreviewWidget()

        def _open_gradient_editor():
            mw = self.window()
            fg = getattr(mw._canvas, 'fg_color', QColor(0,0,0)) if hasattr(mw, '_canvas') else QColor(0,0,0)
            bg = getattr(mw._canvas, 'bg_color', QColor(255,255,255)) if hasattr(mw, '_canvas') else QColor(255,255,255)

            dlg = GradientEditorDialog(self._grad_preview._stops, fg, bg, self)
            if dlg.exec():
                stops = dlg.result_stops()
                self._grad_preview.set_stops(stops)
                self.option_changed.emit("gradient_stops", stops)

        self._grad_preview.clicked.connect(_open_gradient_editor)

        op_sl = _hslider(1, 100, 100)
        op_sp = QSpinBox()
        op_sp.setRange(1, 100)
        op_sp.setValue(100)
        op_sp.setSuffix("%")
        op_sl.valueChanged.connect(op_sp.setValue)
        op_sp.valueChanged.connect(op_sl.setValue)
        op_sp.valueChanged.connect(
            lambda v: self.option_changed.emit("gradient_opacity", v))

        rev_cb = QCheckBox(tr("opts.gradient.reverse"))
        rev_cb.setChecked(False)
        rev_cb.toggled.connect(lambda v: self.option_changed.emit("gradient_reverse", v))

        self.layout.addWidget(self._lbl("opts.gradient.type"))
        self.layout.addWidget(type_combo)
        self.layout.addWidget(self._grad_preview)
        self.layout.addWidget(self._lbl("opts.opacity"))
        self.layout.addWidget(op_sl)
        self.layout.addWidget(op_sp)
        self.layout.addWidget(rev_cb)
        self.layout.addStretch()
