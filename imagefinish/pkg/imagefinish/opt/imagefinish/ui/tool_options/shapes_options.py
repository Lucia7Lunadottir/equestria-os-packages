import os
import glob
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel,
                             QSpinBox, QComboBox, QCheckBox)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from .base_options import BaseOptions
from core.locale import tr
from core.adjustments._widgets import _ColorButton
from ui.adjustments_dialog import _JumpSlider


def _hslider(minimum: int, maximum: int, value: int):
    s = _JumpSlider(Qt.Orientation.Horizontal)
    s.setMinimum(minimum)
    s.setMaximum(maximum)
    s.setValue(value)
    s.setFixedWidth(120)
    return s


class ShapesOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.setSpacing(14)
        
        self._SHAPE_VALUES = ["rect", "ellipse", "triangle", "polygon", "line", "star", "arrow", "cross"]
        _SHAPE_KEYS = (
            "opts.shape.rect", "opts.shape.ellipse", "opts.shape.triangle",
            "opts.shape.polygon", "opts.shape.line", "opts.shape.star",
            "opts.shape.arrow", "opts.shape.cross",
        )
        self._combo = QComboBox()
        self._combo.addItems([tr(k) for k in _SHAPE_KEYS])
        
        self._custom_shapes = []
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shapes_dir = os.path.join(base_dir, "shapes")
        if os.path.exists(shapes_dir):
            for f in sorted(glob.glob(os.path.join(shapes_dir, "*.json"))):
                name = os.path.splitext(os.path.basename(f))[0]
                self._combo.addItem(name)
                self._custom_shapes.append(f)

        sides_lbl = self._lbl("opts.shape.sides")
        sides_sp = QSpinBox()
        sides_sp.setRange(3, 20)
        sides_sp.setValue(6)
        sides_sp.setFixedWidth(44)
        sides_sp.valueChanged.connect(lambda v: self.option_changed.emit("shape_sides", v))
        sides_lbl.setVisible(False)
        sides_sp.setVisible(False)

        angle_lbl = self._lbl("opts.shape.angle")
        angle_sp = QSpinBox()
        angle_sp.setRange(0, 359)
        angle_sp.setValue(0)
        angle_sp.setFixedWidth(50)
        angle_sp.setSuffix("°")
        angle_sp.setWrapping(True)
        angle_sp.valueChanged.connect(lambda v: self.option_changed.emit("shape_angle", v))
        
        self._angle_random_cb = QCheckBox(tr("opts.angle_random"))
        self._angle_random_cb.toggled.connect(lambda v: self.option_changed.emit("shape_angle_random", v))

        def _on_shape_change(i):
            shape = self._SHAPE_VALUES[i] if i < len(self._SHAPE_VALUES) else "custom:" + self._custom_shapes[i - len(self._SHAPE_VALUES)]
            self.option_changed.emit("shape_type", shape)
            sides_lbl.setVisible(shape == "polygon")
            sides_sp.setVisible(shape == "polygon")
            angle_lbl.setVisible(shape != "line")
            angle_sp.setVisible(shape != "line")

        self._combo.currentIndexChanged.connect(_on_shape_change)

        sl = _hslider(1, 50, 2)
        sp = QSpinBox()
        sp.setRange(1, 50)
        sp.setValue(2)
        sl.valueChanged.connect(sp.setValue)
        sp.valueChanged.connect(sl.setValue)
        sp.valueChanged.connect(lambda v: self.option_changed.emit("brush_size", v))

        fill_cb = QCheckBox(tr("opts.shape.fill"))
        fill_cb.setChecked(False)
        fill_cb.toggled.connect(lambda v: self.option_changed.emit("shape_fill", v))

        self.layout.addWidget(self._lbl("opts.shape"))
        self.layout.addWidget(self._combo)
        self.layout.addWidget(sides_lbl)
        self.layout.addWidget(sides_sp)
        self.layout.addWidget(angle_lbl)
        self.layout.addWidget(angle_sp)
        self.layout.addWidget(self._angle_random_cb)
        self.layout.addWidget(fill_cb)
        
        self.layout.addWidget(self._lbl("opts.shape.color"))
        self._color_btn = _ColorButton(QColor(0, 0, 0))
        self._color_btn.colorChanged.connect(lambda c: self.option_changed.emit("shape_color", c))
        self.layout.addWidget(self._color_btn)

        self.layout.addWidget(self._lbl("opts.stroke"))
        self.layout.addWidget(sl)
        self.layout.addWidget(sp)
        self.layout.addStretch()
        
    def add_custom_shape(self, path, name):
        self._combo.addItem(name)
        self._custom_shapes.append(path)
        self._combo.setCurrentIndex(self._combo.count() - 1)

    def update_from_opts(self, opts: dict):
        color = opts.get("shape_color", QColor(0, 0, 0))
        if hasattr(self, "_color_btn"):
            self._color_btn.blockSignals(True)
            self._color_btn.set_color(color)
            self._color_btn.blockSignals(False)
