from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QSpinBox, QDialogButtonBox,
                             QWidget, QFormLayout)
from PyQt6.QtCore import Qt
from core.locale import tr
from ui.adjustments_dialog import _JumpSlider


_ADJ_TYPES = ["brightness_contrast", "hue_saturation", "invert"]


class AdjustmentLayerDialog(QDialog):

    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("adj_layer.title"))
        self.setMinimumWidth(340)

        self.layer = layer
        self.canvas_refresh = canvas_refresh
        self._original_data = dict(layer.adjustment_data) if layer.adjustment_data else {}
        self._data = dict(self._original_data) if self._original_data else {"type": "brightness_contrast",
                                                                            "brightness": 0, "contrast": 0}

        lo = QVBoxLayout(self)
        lo.setSpacing(8)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(tr("adj_layer.type")))
        self._type_combo = QComboBox()
        self._type_combo.addItem(tr("adj_layer.bc"),    "brightness_contrast")
        self._type_combo.addItem(tr("adj_layer.hs"),    "hue_saturation")
        self._type_combo.addItem(tr("adj_layer.invert"), "invert")
        cur = self._data.get("type", "brightness_contrast")
        idx = next((i for i in range(self._type_combo.count())
                    if self._type_combo.itemData(i) == cur), 0)
        self._type_combo.setCurrentIndex(idx)
        type_row.addWidget(self._type_combo, 1)
        lo.addLayout(type_row)

        # ── Params stacks ────────────────────────────────────────────────
        self._bc_widget  = self._make_bc_widget()
        self._hs_widget  = self._make_hs_widget()
        self._inv_widget = QLabel(tr("adj_layer.invert_hint"))
        self._inv_widget.setWordWrap(True)
        lo.addWidget(self._bc_widget)
        lo.addWidget(self._hs_widget)
        lo.addWidget(self._inv_widget)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lo.addWidget(btns)

        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed()

    # ── Param pages ──────────────────────────────────────────────────────

    def _make_bc_widget(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
        self._br_slider, self._br_spin = self._slider_spin(-100, 100,
            self._data.get("brightness", 0))
        self._ct_slider, self._ct_spin = self._slider_spin(-100, 100,
            self._data.get("contrast", 0))
        f.addRow(tr("adj.bc.brightness"), self._pair(self._br_slider, self._br_spin))
        f.addRow(tr("adj.bc.contrast"),   self._pair(self._ct_slider, self._ct_spin))
        return w

    def _make_hs_widget(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
        self._hue_slider, self._hue_spin   = self._slider_spin(-180, 180,
            self._data.get("hue", 0))
        self._sat_slider, self._sat_spin   = self._slider_spin(-100, 100,
            self._data.get("saturation", 0))
        self._lit_slider, self._lit_spin   = self._slider_spin(-100, 100,
            self._data.get("lightness", 0))
        f.addRow(tr("adj.hs.hue"),        self._pair(self._hue_slider, self._hue_spin))
        f.addRow(tr("adj.hs.saturation"), self._pair(self._sat_slider, self._sat_spin))
        f.addRow(tr("adj.hs.lightness"),  self._pair(self._lit_slider, self._lit_spin))
        return w

    # ── Helpers ──────────────────────────────────────────────────────────

    def _slider_spin(self, lo: int, hi: int, val: int):
        sl = _JumpSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(val)
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(val)
        sp.setFixedWidth(60)
        sl.valueChanged.connect(sp.setValue)
        sp.valueChanged.connect(sl.setValue)
        sl.valueChanged.connect(self._trigger_preview)
        return sl, sp

    @staticmethod
    def _pair(slider, spin) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(slider, 1)
        h.addWidget(spin)
        return w

    def _on_type_changed(self):
        t = self._type_combo.currentData()
        self._bc_widget.setVisible(t == "brightness_contrast")
        self._hs_widget.setVisible(t == "hue_saturation")
        self._inv_widget.setVisible(t == "invert")
        self.adjustSize()
        self._trigger_preview()

    # ── Result ───────────────────────────────────────────────────────────

    def result_data(self) -> dict:
        t = self._type_combo.currentData()
        if t == "brightness_contrast":
            return {"type": t,
                    "brightness": self._br_spin.value(),
                    "contrast":   self._ct_spin.value()}
        if t == "hue_saturation":
            return {"type": t,
                    "hue":        self._hue_spin.value(),
                    "saturation": self._sat_spin.value(),
                    "lightness":  self._lit_spin.value()}
        return {"type": "invert"}

    def _trigger_preview(self, *args):
        self.layer.adjustment_data = self.result_data()
        self.canvas_refresh()

    def accept(self):
        self.layer.adjustment_data = self.result_data()
        super().accept()

    def reject(self):
        self.layer.adjustment_data = self._original_data
        self.canvas_refresh()
        super().reject()
