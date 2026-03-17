from PyQt6.QtWidgets import QSpinBox
from PyQt6.QtCore import Qt
from .base_options import BaseOptions
from ui.adjustments_dialog import _JumpSlider

class MagneticLassoOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout.addWidget(self._lbl("opts.mag.width"))
        self._w_sl, self._w_sp = self._make_slider(1, 256, 10, " px")
        self._w_sl.valueChanged.connect(lambda v: self.option_changed.emit("mag_width", v))
        self.layout.addWidget(self._w_sl); self.layout.addWidget(self._w_sp)

        self.layout.addSpacing(10)
        self.layout.addWidget(self._lbl("opts.mag.contrast"))
        self._c_sl, self._c_sp = self._make_slider(1, 100, 10, "%")
        self._c_sl.valueChanged.connect(lambda v: self.option_changed.emit("mag_contrast", v))
        self.layout.addWidget(self._c_sl); self.layout.addWidget(self._c_sp)

        self.layout.addSpacing(10)
        self.layout.addWidget(self._lbl("opts.mag.freq"))
        self._f_sl, self._f_sp = self._make_slider(0, 100, 57, "")
        self._f_sl.valueChanged.connect(lambda v: self.option_changed.emit("mag_freq", v))
        self.layout.addWidget(self._f_sl); self.layout.addWidget(self._f_sp)

        self.layout.addStretch()

    def _make_slider(self, min_val, max_val, default_val, suffix):
        sl = _JumpSlider(Qt.Orientation.Horizontal)
        sl.setRange(min_val, max_val)
        sl.setValue(default_val)
        sl.setFixedWidth(80)
        sp = QSpinBox()
        sp.setRange(min_val, max_val)
        sp.setValue(default_val)
        sp.setSuffix(suffix)
        sp.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        sl.valueChanged.connect(sp.setValue)
        sp.valueChanged.connect(sl.setValue)
        return sl, sp