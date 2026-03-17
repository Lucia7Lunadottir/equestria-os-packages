from PyQt6.QtWidgets import QPushButton
from .base_options import BaseOptions
from core.locale import tr

class ColorSamplerOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clear_btn = QPushButton(tr("opts.clear_markers"))
        self.clear_btn.clicked.connect(lambda: self.option_changed.emit("sampler_clear", True))
        self.layout.addWidget(self.clear_btn)
        self.layout.addStretch()
    def retranslate(self):
        self.clear_btn.setText(tr("opts.clear_markers"))
        super().retranslate()
        
class RulerOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clear_btn = QPushButton(tr("opts.clear_ruler"))
        self.clear_btn.clicked.connect(lambda: self.option_changed.emit("ruler_clear", True))
        self.layout.addWidget(self.clear_btn)
        self.layout.addStretch()
    def retranslate(self):
        self.clear_btn.setText(tr("opts.clear_ruler"))
        super().retranslate()