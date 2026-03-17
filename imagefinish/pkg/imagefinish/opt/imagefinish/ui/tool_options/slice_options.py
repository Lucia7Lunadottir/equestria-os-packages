from PyQt6.QtWidgets import QPushButton
from .base_options import BaseOptions
from core.locale import tr

class SliceOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clear_btn = QPushButton(tr("opts.clear_slices"))
        self.clear_btn.setObjectName("smallBtn")
        self.clear_btn.clicked.connect(lambda: self.option_changed.emit("clear_slices", True))
        self.layout.addWidget(self.clear_btn)
        self.layout.addStretch()

    def retranslate(self):
        self.clear_btn.setText(tr("opts.clear_slices"))
        super().retranslate()