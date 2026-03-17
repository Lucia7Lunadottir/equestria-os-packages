from PyQt6.QtWidgets import QSpinBox, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from .base_options import BaseOptions
from core.locale import tr
from ui.adjustments_dialog import _JumpSlider

class PatchOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.addWidget(self._lbl("opts.patch_hint"))
        self.layout.addSpacing(15)
        self.layout.addWidget(self._lbl("opts.patch.diffusion"))

        self._diff_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._diff_slider.setRange(1, 10)
        self._diff_slider.setFixedWidth(80)
        
        self._diff_spin = QSpinBox()
        self._diff_spin.setRange(1, 10)
        self._diff_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        
        self._diff_slider.valueChanged.connect(self._diff_spin.setValue)
        self._diff_spin.valueChanged.connect(self._diff_slider.setValue)
        self._diff_spin.valueChanged.connect(lambda v: self.option_changed.emit("patch_diffusion", v))
        
        self.layout.addWidget(self._diff_slider)
        self.layout.addWidget(self._diff_spin)
        
        self.layout.addSpacing(15)
        self.layout.addWidget(self._lbl("opts.opacity"))
        
        self._op_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._op_slider.setRange(1, 100)
        self._op_slider.setFixedWidth(80)
        
        self._op_spin = QSpinBox()
        self._op_spin.setRange(1, 100)
        self._op_spin.setSuffix("%")
        self._op_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        
        self._op_slider.valueChanged.connect(self._op_spin.setValue)
        self._op_spin.valueChanged.connect(self._op_slider.setValue)
        self._op_spin.valueChanged.connect(lambda v: self.option_changed.emit("patch_opacity", v / 100.0))
        
        self.layout.addWidget(self._op_slider)
        self.layout.addWidget(self._op_spin)
        self.layout.addStretch()

    def update_from_opts(self, opts: dict):
        self._diff_slider.blockSignals(True)
        self._diff_spin.blockSignals(True)
        self._op_slider.blockSignals(True)
        self._op_spin.blockSignals(True)
        val = opts.get("patch_diffusion", 5)
        self._diff_slider.setValue(val)
        self._diff_spin.setValue(val)
        op = int(opts.get("patch_opacity", 1.0) * 100)
        self._op_slider.setValue(op)
        self._op_spin.setValue(op)
        self._diff_slider.blockSignals(False)
        self._diff_spin.blockSignals(False)
        self._op_slider.blockSignals(False)
        self._op_spin.blockSignals(False)


class SpotHealingOptions(BaseOptions):
    def __init__(self, hint_key="opts.spot_healing_hint", parent=None):
        super().__init__(parent)
        self.layout.addWidget(self._lbl(hint_key))
        self.layout.addSpacing(15)
        self.layout.addWidget(self._lbl("opts.size"))

        self._size_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(1, 500)
        self._size_slider.setFixedWidth(100)
        
        self._size_spin = QSpinBox()
        self._size_spin.setRange(1, 5000)
        self._size_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        
        self._size_slider.valueChanged.connect(self._size_spin.setValue)
        self._size_spin.valueChanged.connect(self._size_slider.setValue)
        self._size_spin.valueChanged.connect(lambda v: self.option_changed.emit("brush_size", v))
        
        self.layout.addWidget(self._size_slider)
        self.layout.addWidget(self._size_spin)
        
        self.layout.addSpacing(15)
        self.layout.addWidget(self._lbl("opts.opacity"))
        
        self._op_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._op_slider.setRange(1, 100)
        self._op_slider.setFixedWidth(80)
        
        self._op_spin = QSpinBox()
        self._op_spin.setRange(1, 100)
        self._op_spin.setSuffix("%")
        self._op_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        
        self._op_slider.valueChanged.connect(self._op_spin.setValue)
        self._op_spin.valueChanged.connect(self._op_slider.setValue)
        self._op_spin.valueChanged.connect(lambda v: self.option_changed.emit("brush_opacity", v / 100.0))
        
        self.layout.addWidget(self._op_slider)
        self.layout.addWidget(self._op_spin)
        self.layout.addStretch()

    def update_from_opts(self, opts: dict):
        self._size_slider.blockSignals(True)
        self._size_spin.blockSignals(True)
        self._op_slider.blockSignals(True)
        self._op_spin.blockSignals(True)
        size = opts.get("brush_size", 20)
        self._size_slider.setValue(size)
        self._size_spin.setValue(size)
        op = int(opts.get("brush_opacity", 1.0) * 100)
        self._op_slider.setValue(op)
        self._op_spin.setValue(op)
        self._size_slider.blockSignals(False)
        self._size_spin.blockSignals(False)
        self._op_slider.blockSignals(False)
        self._op_spin.blockSignals(False)


class RedEyeOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.addWidget(self._lbl("opts.red_eye_hint"))
        self.layout.addSpacing(15)

        # Размер зрачка
        self.layout.addWidget(self._lbl("opts.red_eye.size"))
        self._size_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(1, 100)
        self._size_slider.setFixedWidth(80)
        self._size_spin = QSpinBox()
        self._size_spin.setRange(1, 100)
        self._size_spin.setSuffix("%")
        self._size_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._size_slider.valueChanged.connect(self._size_spin.setValue)
        self._size_spin.valueChanged.connect(self._size_slider.setValue)
        self._size_spin.valueChanged.connect(lambda v: self.option_changed.emit("red_eye_size", v))
        self.layout.addWidget(self._size_slider)
        self.layout.addWidget(self._size_spin)
        self.layout.addSpacing(15)

        # Степень затемнения
        self.layout.addWidget(self._lbl("opts.red_eye.darken"))
        self._dark_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._dark_slider.setRange(1, 100)
        self._dark_slider.setFixedWidth(80)
        self._dark_spin = QSpinBox()
        self._dark_spin.setRange(1, 100)
        self._dark_spin.setSuffix("%")
        self._dark_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._dark_slider.valueChanged.connect(self._dark_spin.setValue)
        self._dark_spin.valueChanged.connect(self._dark_slider.setValue)
        self._dark_spin.valueChanged.connect(lambda v: self.option_changed.emit("red_eye_darken", v))
        self.layout.addWidget(self._dark_slider)
        self.layout.addWidget(self._dark_spin)
        self.layout.addStretch()

    def update_from_opts(self, opts: dict):
        for w in [self._size_slider, self._size_spin, self._dark_slider, self._dark_spin]:
            w.blockSignals(True)
        s = opts.get("red_eye_size", 50)
        d = opts.get("red_eye_darken", 50)
        self._size_slider.setValue(s); self._size_spin.setValue(s)
        self._dark_slider.setValue(d); self._dark_spin.setValue(d)
        for w in [self._size_slider, self._size_spin, self._dark_slider, self._dark_spin]:
            w.blockSignals(False)