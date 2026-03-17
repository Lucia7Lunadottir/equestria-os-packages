from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSpinBox
from PyQt6.QtCore import Qt
from .base_options import BaseOptions
from core.locale import tr
from ui.adjustments_dialog import _JumpSlider

class BackgroundEraserOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # --- Размер ---
        self.layout.addWidget(self._lbl("opts.size"))
        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        self._size_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(1, 500)
        self._size_slider.setFixedWidth(100)
        self._size_spin = QSpinBox()
        self._size_spin.setRange(1, 5000)
        self._size_slider.valueChanged.connect(self._on_size_slider_change)
        self._size_spin.valueChanged.connect(self._on_size_spin_change)
        size_layout.addWidget(self._size_slider)
        size_layout.addWidget(self._size_spin)
        self.layout.addWidget(size_widget)

        # --- Допуск ---
        self.layout.addWidget(self._lbl("opts.tolerance"))
        tol_widget = QWidget()
        tol_layout = QHBoxLayout(tol_widget)
        tol_layout.setContentsMargins(0, 0, 0, 0)
        self._tol_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._tol_slider.setRange(0, 100)
        self._tol_slider.setFixedWidth(100)
        self._tol_spin = QSpinBox()
        self._tol_spin.setRange(0, 100)
        self._tol_slider.valueChanged.connect(self._tol_spin.setValue)
        self._tol_spin.valueChanged.connect(self._tol_slider.setValue)
        self._tol_spin.valueChanged.connect(lambda v: self.option_changed.emit("fill_tolerance", v))
        tol_layout.addWidget(self._tol_slider)
        tol_layout.addWidget(self._tol_spin)
        self.layout.addWidget(tol_widget)

        self.layout.addStretch()

    def _on_size_slider_change(self, value):
        self._size_spin.blockSignals(True)
        self._size_spin.setValue(value)
        self._size_spin.blockSignals(False)
        self.option_changed.emit("brush_size", value)

    def _on_size_spin_change(self, value):
        self._size_slider.blockSignals(True)
        self._size_slider.setValue(value)
        self._size_slider.blockSignals(False)
        self.option_changed.emit("brush_size", value)

    def update_from_opts(self, opts: dict):
        for w in [self._size_slider, self._size_spin, self._tol_slider, self._tol_spin]:
            w.blockSignals(True)

        size = opts.get("brush_size", 20)
        self._size_slider.setValue(size)
        self._size_spin.setValue(size)
        
        tol = opts.get("fill_tolerance", 32)
        self._tol_slider.setValue(tol)
        self._tol_spin.setValue(tol)

        for w in [self._size_slider, self._size_spin, self._tol_slider, self._tol_spin]:
            w.blockSignals(False)