from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QPushButton)
from .base_options import BaseOptions
from core.locale import tr


class RotateViewOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.setSpacing(14)
        self.layout.addWidget(self._lbl("opts.rotate_view_hint"))

        reset_btn = QPushButton(tr("opts.rotate_view_reset"))
        reset_btn.setObjectName("smallBtn")
        reset_btn.setFixedHeight(26)
        reset_btn.clicked.connect(
            lambda: self.option_changed.emit("reset_view_rotation", True))
        
        self.layout.addWidget(reset_btn)
        self.layout.addStretch()
