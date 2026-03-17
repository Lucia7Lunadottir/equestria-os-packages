from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QSpinBox, QPushButton, QComboBox, QWidget,
                             QDialogButtonBox, QColorDialog, QFrame)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class NewDocumentDialog(QDialog):
    """Modal dialog to configure a new document."""

    # Preset sizes: (label, width, height)
    PRESETS = [
        ("Custom",          800,  600),
        ("HD 1280×720",    1280,  720),
        ("Full HD 1920×1080", 1920, 1080),
        ("Square 1000×1000", 1000, 1000),
        ("A4 (72dpi)",      595,  842),
        ("A4 (150dpi)",    1240, 1754),
        ("Icon 256×256",    256,  256),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Document")
        self.setModal(True)
        self.setMinimumWidth(320)

        self._bg_color = QColor(255, 255, 255)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Preset dropdown
        preset_row = self._row("Preset:")
        self._preset_combo = QComboBox()
        for label, *_ in self.PRESETS:
            self._preset_combo.addItem(label)
        self._preset_combo.currentIndexChanged.connect(self._on_preset)
        preset_row.layout().addWidget(self._preset_combo)
        layout.addWidget(preset_row)

        # Width
        w_row = self._row("Width:")
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 16384)
        self._width_spin.setValue(800)
        self._width_spin.setSuffix(" px")
        w_row.layout().addWidget(self._width_spin)
        layout.addWidget(w_row)

        # Height
        h_row = self._row("Height:")
        self._height_spin = QSpinBox()
        self._height_spin.setRange(1, 16384)
        self._height_spin.setValue(600)
        self._height_spin.setSuffix(" px")
        h_row.layout().addWidget(self._height_spin)
        layout.addWidget(h_row)

        # Background colour
        bg_row = self._row("Background:")
        self._bg_btn = QPushButton("   ")
        self._bg_btn.setFixedWidth(60)
        self._bg_btn.setStyleSheet(f"background-color: {self._bg_color.name()}; border: 1px solid #45475a; border-radius:4px;")
        self._bg_btn.clicked.connect(self._pick_bg)
        bg_row.layout().addWidget(self._bg_btn)
        layout.addWidget(bg_row)

        # OK / Cancel
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _row(label_text: str) -> QWidget:
        w = QWidget()
        lo = QHBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(90)
        lo.addWidget(lbl)
        return w

    def _on_preset(self, index: int):
        if index == 0:
            return
        _, w, h = self.PRESETS[index]
        self._width_spin.setValue(w)
        self._height_spin.setValue(h)

    def _pick_bg(self):
        c = QColorDialog.getColor(self._bg_color, self, "Background Color")
        if c.isValid():
            self._bg_color = c
            self._bg_btn.setStyleSheet(
                f"background-color: {c.name()}; border: 1px solid #45475a; border-radius:4px;")

    # ---------------------------------------------------------------- result
    def get_width(self) -> int:
        return self._width_spin.value()

    def get_height(self) -> int:
        return self._height_spin.value()

    def get_bg_color(self) -> QColor:
        return self._bg_color
