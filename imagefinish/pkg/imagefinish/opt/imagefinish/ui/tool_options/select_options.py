from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel)
from .base_options import BaseOptions


class SelectOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.addWidget(self._lbl("opts.select_hint"))
        self.layout.addStretch()
