from PyQt6.QtWidgets import QWidget, QHBoxLayout
from PyQt6.QtCore import pyqtSignal


class BaseOptions(QWidget):
    option_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self._auto_labels = []   # list of (QLabel, key) for auto-retranslation

    def _lbl(self, key: str):
        from core.locale import tr
        from PyQt6.QtWidgets import QLabel
        lbl = QLabel(tr(key))
        lbl.setObjectName("optLabel")
        self._auto_labels.append((lbl, key))
        return lbl

    def retranslate(self):
        from core.locale import tr
        for lbl, key in self._auto_labels:
            lbl.setText(tr(key))
