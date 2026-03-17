from PyQt6.QtWidgets import QComboBox
from .base_options import BaseOptions
from core.locale import tr

class FrameOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.addWidget(self._lbl("opts.shape"))
        self._combo = QComboBox()
        self._combo.addItem(tr("opts.shape.rect"), "rect")
        self._combo.addItem(tr("opts.shape.ellipse"), "ellipse")
        self._combo.currentIndexChanged.connect(lambda i: self.option_changed.emit("frame_shape", self._combo.currentData()))
        self.layout.addWidget(self._combo)
        self.layout.addStretch()

    def update_from_opts(self, opts: dict):
        shape = opts.get("frame_shape", "rect")
        idx = self._combo.findData(shape)
        if idx >= 0:
            self._combo.blockSignals(True); self._combo.setCurrentIndex(idx); self._combo.blockSignals(False)

    def retranslate(self):
        self._combo.setItemText(0, tr("opts.shape.rect")); self._combo.setItemText(1, tr("opts.shape.ellipse"))
        super().retranslate()