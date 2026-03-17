from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QSpinBox)
from PyQt6.QtCore import pyqtSignal
from .base_options import BaseOptions
from core.locale import tr


class CropOptions(BaseOptions):
    apply_crop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._aspect_ratio = 1.0
        
        self._hint_lbl = self._lbl("opts.crop_hint")
        self.layout.addWidget(self._hint_lbl)
        
        self._tf_widget = QWidget()
        tf_layout = QHBoxLayout(self._tf_widget)
        tf_layout.setContentsMargins(0, 0, 0, 0)
        tf_layout.setSpacing(4)
        
        def make_sp(min_v, max_v, suf):
            sp = QSpinBox()
            sp.setRange(min_v, max_v)
            sp.setSuffix(suf)
            sp.setFixedWidth(74)
            sp.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            return sp
            
        self._sp_x = make_sp(-99999, 99999, " px")
        self._sp_y = make_sp(-99999, 99999, " px")
        self._sp_w = make_sp(1, 99999, " px")
        self._sp_h = make_sp(1, 99999, " px")
        
        self._btn_link = QPushButton("🔗")
        self._btn_link.setCheckable(True); self._btn_link.setChecked(False)
        self._btn_link.setFixedSize(24, 24); self._btn_link.setObjectName("smallBtn")
        
        for lbl, w in [("X:", self._sp_x), ("Y:", self._sp_y)]: 
            tf_layout.addWidget(QLabel(lbl)); tf_layout.addWidget(w)
        tf_layout.addSpacing(6)
        tf_layout.addWidget(QLabel("W:")); tf_layout.addWidget(self._sp_w)
        tf_layout.addWidget(self._btn_link)
        tf_layout.addWidget(QLabel("H:")); tf_layout.addWidget(self._sp_h)
        
        self._sp_x.valueChanged.connect(self._on_user_edit)
        self._sp_y.valueChanged.connect(self._on_user_edit)
        self._sp_w.valueChanged.connect(self._on_w_edit)
        self._sp_h.valueChanged.connect(self._on_h_edit)
        
        self.layout.addWidget(self._tf_widget)
        self._tf_widget.setVisible(False)

        self.layout.addSpacing(15)
        self.layout.addWidget(self._lbl("opts.crop_overlay"))
        
        self._overlay_combo = QComboBox()
        self._OVERLAYS = ["none", "thirds", "grid", "diagonal"]
        self._OVERLAY_KEYS = [
            "opts.crop_overlay.none", "opts.crop_overlay.thirds",
            "opts.crop_overlay.grid", "opts.crop_overlay.diagonal"
        ]
        self._overlay_combo.addItems([tr(k) for k in self._OVERLAY_KEYS])
        self._overlay_combo.setCurrentIndex(1) # По умолчанию Правило третей
        self._overlay_combo.currentIndexChanged.connect(
            lambda i: self.option_changed.emit("crop_overlay", self._OVERLAYS[i])
        )
        self.layout.addWidget(self._overlay_combo)
        self.layout.addSpacing(15)
        
        apply_btn = QPushButton(tr("menu.apply_crop"))
        apply_btn.setObjectName("smallBtn")
        apply_btn.setFixedHeight(26)
        apply_btn.clicked.connect(self.apply_crop_requested.emit)
        self.layout.addWidget(apply_btn)
        self.layout.addStretch()

    def _on_w_edit(self, val):
        if self._updating: return
        if self._btn_link.isChecked() and self._aspect_ratio > 0:
            self._updating = True
            self._sp_h.setValue(int(val / self._aspect_ratio))
            self._updating = False
        self._on_user_edit()

    def _on_h_edit(self, val):
        if self._updating: return
        if self._btn_link.isChecked() and self._aspect_ratio > 0:
            self._updating = True
            self._sp_w.setValue(int(val * self._aspect_ratio))
            self._updating = False
        self._on_user_edit()

    def _on_user_edit(self, *_):
        if self._updating: return
        self.option_changed.emit("transform_params", {
            'x': self._sp_x.value(),
            'y': self._sp_y.value(),
            'w': self._sp_w.value(),
            'h': self._sp_h.value()
        })

    def update_params(self, params: dict | None):
        if hasattr(self, "_tf_widget"):
            if params is None:
                self._tf_widget.setVisible(False); self._hint_lbl.setVisible(True)
            else:
                self._tf_widget.setVisible(True); self._hint_lbl.setVisible(False)
                self._updating = True
                w, h = int(params.get('w', 1)), int(params.get('h', 1))
                if h > 0: self._aspect_ratio = w / h
                self._sp_x.setValue(int(params.get('x', 0)))
                self._sp_y.setValue(int(params.get('y', 0)))
                self._sp_w.setValue(w)
                self._sp_h.setValue(h)
                self._updating = False

    def update_from_opts(self, opts: dict):
        val = opts.get("crop_overlay", "thirds")
        if val in self._OVERLAYS:
            self._overlay_combo.blockSignals(True)
            self._overlay_combo.setCurrentIndex(self._OVERLAYS.index(val))
            self._overlay_combo.blockSignals(False)
            
    def retranslate(self):
        if hasattr(super(), "retranslate"):
            super().retranslate()
        idx = self._overlay_combo.currentIndex()
        self._overlay_combo.blockSignals(True)
        self._overlay_combo.clear()
        self._overlay_combo.addItems([tr(k) for k in self._OVERLAY_KEYS])
        self._overlay_combo.setCurrentIndex(idx)
        self._overlay_combo.blockSignals(False)
        if hasattr(self, "_btn_link"):
            self._btn_link.setToolTip(tr("opts.link_aspect"))
