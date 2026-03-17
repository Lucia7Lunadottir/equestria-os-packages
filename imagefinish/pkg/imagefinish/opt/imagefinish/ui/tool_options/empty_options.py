from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel)
from .base_options import BaseOptions


class EmptyOptions(BaseOptions):
    def __init__(self, tr_key:str, parent=None):
        super().__init__(parent)
        self.layout.addWidget(self._lbl(tr_key))
        self.layout.addStretch()
