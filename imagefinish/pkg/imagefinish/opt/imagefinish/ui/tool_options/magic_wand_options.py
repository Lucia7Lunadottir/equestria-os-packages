from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSpinBox, QCheckBox
from PyQt6.QtCore import Qt
from .base_options import BaseOptions
from ui.adjustments_dialog import _JumpSlider
from core.locale import tr

class MagicWandOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Блок чувствительности (Tolerance) ---
        self.layout.addWidget(self._lbl("opts.tolerance"))

        tol_widget = QWidget()
        tol_layout = QHBoxLayout(tol_widget)
        tol_layout.setContentsMargins(0, 0, 0, 0)

        self._tol_slider = _JumpSlider(Qt.Orientation.Horizontal)
        self._tol_slider.setRange(0, 100)
        self._tol_slider.setFixedWidth(80)

        self._tol_spin = QSpinBox()
        self._tol_spin.setRange(0, 100)
        self._tol_spin.setSuffix("%")

        self._tol_slider.valueChanged.connect(self._tol_spin.setValue)
        self._tol_spin.valueChanged.connect(self._tol_slider.setValue)
        self._tol_spin.valueChanged.connect(lambda v: self.option_changed.emit("fill_tolerance", v))

        tol_layout.addWidget(self._tol_slider)
        tol_layout.addWidget(self._tol_spin)
        self.layout.addWidget(tol_widget)

        # --- Галочки (Чекбоксы) ---
        self._aa_cb = QCheckBox(tr("opts.anti_alias"))
        self._aa_cb.setChecked(True)
        self._aa_cb.toggled.connect(lambda v: self.option_changed.emit("anti_alias", v))
        self.layout.addWidget(self._aa_cb)

        self._contig_cb = QCheckBox(tr("opts.contiguous"))
        self._contig_cb.setChecked(True)
        self._contig_cb.toggled.connect(lambda v: self.option_changed.emit("contiguous", v))
        self.layout.addWidget(self._contig_cb)

        self._sample_cb = QCheckBox(tr("opts.sample_all_layers"))
        self._sample_cb.setChecked(False)
        self._sample_cb.toggled.connect(lambda v: self.option_changed.emit("sample_all", v))
        self.layout.addWidget(self._sample_cb)

        self.layout.addStretch()

    def retranslate(self):
        super().retranslate()
        self._aa_cb.setText(tr("opts.anti_alias"))
        self._contig_cb.setText(tr("opts.contiguous"))
        self._sample_cb.setText(tr("opts.sample_all_layers"))

    def update_from_opts(self, opts: dict):
        self._tol_spin.setValue(opts.get("fill_tolerance", 32))
        self._aa_cb.setChecked(opts.get("anti_alias", True))
        self._contig_cb.setChecked(opts.get("contiguous", True))
        self._sample_cb.setChecked(opts.get("sample_all", False))
