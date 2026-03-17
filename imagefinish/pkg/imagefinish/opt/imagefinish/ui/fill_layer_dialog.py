from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QDialogButtonBox, QWidget)
from PyQt6.QtGui import QColor, QPixmap, QIcon
from PyQt6.QtCore import Qt
from core.locale import tr


class FillLayerDialog(QDialog):

    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("fill_layer.title"))
        self.setMinimumWidth(300)

        self.layer = layer
        self.canvas_refresh = canvas_refresh
        self._original_data = dict(layer.fill_data) if layer.fill_data else {}
        self._data = dict(self._original_data) if self._original_data else {"type": "solid",
                                                                            "color": QColor(128, 128, 128)}

        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(tr("fill_layer.type")))
        self._type_combo = QComboBox()
        self._type_combo.addItem(tr("fill_layer.solid"),    "solid")
        self._type_combo.addItem(tr("fill_layer.gradient"), "gradient")
        cur = self._data.get("type", "solid")
        idx = next((i for i in range(self._type_combo.count())
                    if self._type_combo.itemData(i) == cur), 0)
        self._type_combo.setCurrentIndex(idx)
        type_row.addWidget(self._type_combo, 1)
        lo.addLayout(type_row)

        # ── Solid color ──────────────────────────────────────────────────
        self._solid_widget = QWidget()
        sr = QHBoxLayout(self._solid_widget)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.addWidget(QLabel(tr("fill_layer.color")))
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(48, 24)
        self._color = self._data.get("color", QColor(128, 128, 128))
        if not isinstance(self._color, QColor):
            self._color = QColor(128, 128, 128)
        self._update_color_btn()
        self._color_btn.clicked.connect(self._pick_color)
        sr.addWidget(self._color_btn)
        sr.addStretch()
        lo.addWidget(self._solid_widget)

        # ── Gradient ─────────────────────────────────────────────────────
        self._grad_widget = QWidget()
        gr = QHBoxLayout(self._grad_widget)
        gr.setContentsMargins(0, 0, 0, 0)
        gr.addWidget(QLabel(tr("fill_layer.color1")))
        self._c1_btn = QPushButton()
        self._c1_btn.setFixedSize(48, 24)
        self._color1 = self._data.get("color1", QColor(0, 0, 0))
        if not isinstance(self._color1, QColor):
            self._color1 = QColor(0, 0, 0)
        self._update_c1_btn()
        self._c1_btn.clicked.connect(self._pick_color1)
        gr.addWidget(self._c1_btn)
        gr.addWidget(QLabel(tr("fill_layer.color2")))
        self._c2_btn = QPushButton()
        self._c2_btn.setFixedSize(48, 24)
        self._color2 = self._data.get("color2", QColor(255, 255, 255))
        if not isinstance(self._color2, QColor):
            self._color2 = QColor(255, 255, 255)
        self._update_c2_btn()
        self._c2_btn.clicked.connect(self._pick_color2)
        gr.addWidget(self._c2_btn)
        gr.addStretch()
        lo.addWidget(self._grad_widget)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lo.addWidget(btns)

        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed()

    # ── Color buttons ─────────────────────────────────────────────────────

    def _update_color_btn(self):
        pix = QPixmap(44, 20)
        pix.fill(self._color)
        self._color_btn.setIcon(QIcon(pix))
        self._color_btn.setIconSize(pix.size())

    def _update_c1_btn(self):
        pix = QPixmap(44, 20)
        pix.fill(self._color1)
        self._c1_btn.setIcon(QIcon(pix))
        self._c1_btn.setIconSize(pix.size())

    def _update_c2_btn(self):
        pix = QPixmap(44, 20)
        pix.fill(self._color2)
        self._c2_btn.setIcon(QIcon(pix))
        self._c2_btn.setIconSize(pix.size())

    def _pick_color(self):
        from ui.hsv_picker import ColorPickerDialog
        c = ColorPickerDialog.get_color(self._color, self, tr("adj.choose_color"))
        if c is not None:
            self._color = c
            self._update_color_btn()
            self._trigger_preview()

    def _pick_color1(self):
        from ui.hsv_picker import ColorPickerDialog
        c = ColorPickerDialog.get_color(self._color1, self, tr("adj.choose_color"))
        if c is not None:
            self._color1 = c
            self._update_c1_btn()
            self._trigger_preview()

    def _pick_color2(self):
        from ui.hsv_picker import ColorPickerDialog
        c = ColorPickerDialog.get_color(self._color2, self, tr("adj.choose_color"))
        if c is not None:
            self._color2 = c
            self._update_c2_btn()
            self._trigger_preview()

    def _on_type_changed(self):
        t = self._type_combo.currentData()
        self._solid_widget.setVisible(t == "solid")
        self._grad_widget.setVisible(t == "gradient")
        self.adjustSize()
        self._trigger_preview()

    # ── Result ────────────────────────────────────────────────────────────

    def result_data(self) -> dict:
        t = self._type_combo.currentData()
        if t == "gradient":
            return {"type": "gradient", "color1": self._color1, "color2": self._color2}
        return {"type": "solid", "color": self._color}

    def _trigger_preview(self):
        self.layer.fill_data = self.result_data()
        self.canvas_refresh()

    def accept(self):
        self.layer.fill_data = self.result_data()
        super().accept()

    def reject(self):
        self.layer.fill_data = self._original_data
        self.canvas_refresh()
        super().reject()
