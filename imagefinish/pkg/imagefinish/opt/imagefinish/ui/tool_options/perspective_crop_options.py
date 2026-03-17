from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox)
from PyQt6.QtCore import pyqtSignal
from .base_options import BaseOptions
from core.locale import tr


class PerspectiveCropOptions(BaseOptions):
    apply_crop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.addWidget(self._lbl("opts.crop_hint"))
        
        self.layout.addSpacing(15)
        self.layout.addWidget(self._lbl("opts.crop_overlay"))
        
        self._overlay_combo = QComboBox()
        self._OVERLAYS = ["none", "thirds", "grid", "diagonal"]
        self._OVERLAY_KEYS = [
            "opts.crop_overlay.none", "opts.crop_overlay.thirds",
            "opts.crop_overlay.grid", "opts.crop_overlay.diagonal"
        ]
        self._overlay_combo.addItems([tr(k) for k in self._OVERLAY_KEYS])
        self._overlay_combo.setCurrentIndex(1)
        self._overlay_combo.currentIndexChanged.connect(
            lambda i: self.option_changed.emit("crop_overlay", self._OVERLAYS[i])
        )
        self.layout.addWidget(self._overlay_combo)
        self.layout.addSpacing(15)
        
        apply_btn = QPushButton(tr("menu.apply_perspective_crop"))
        apply_btn.setObjectName("smallBtn")
        apply_btn.setFixedHeight(26)
        apply_btn.clicked.connect(self.apply_crop_requested.emit)
        self.layout.addWidget(apply_btn)
        self.layout.addStretch()

    def update_from_opts(self, opts: dict):
        val = opts.get("crop_overlay", "thirds")
        if val in self._OVERLAYS:
            self._overlay_combo.blockSignals(True)
            self._overlay_combo.setCurrentIndex(self._OVERLAYS.index(val))
            self._overlay_combo.blockSignals(False)
            
    def retranslate(self):
        if hasattr(super(), "retranslate"):
            super().retranslate()
        idx = self._overlay_combo.currentIndex()
        self._overlay_combo.blockSignals(True)
        self._overlay_combo.clear()
        self._overlay_combo.addItems([tr(k) for k in self._OVERLAY_KEYS])
        self._overlay_combo.setCurrentIndex(idx)
        self._overlay_combo.blockSignals(False)
