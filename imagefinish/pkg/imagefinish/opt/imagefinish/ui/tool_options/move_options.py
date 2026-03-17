from PyQt6.QtWidgets import QPushButton, QLabel, QHBoxLayout, QWidget, QDoubleSpinBox
from .base_options import BaseOptions
from core.locale import tr

class MoveOptions(BaseOptions):
    def __init__(self, hint_key="opts.move_hint", parent=None):
        super().__init__(parent)
        self._hint_key = hint_key
        self._hint_lbl = QLabel(tr(self._hint_key))
        self._hint_lbl.setStyleSheet("color: #a6adc8; font-size: 12px; font-weight: bold;")
        self.layout.addWidget(self._hint_lbl)
        
        self.layout.addSpacing(20)
        self._updating = False

        if "move_hint" in hint_key:
            self._align_widget = QWidget()
            align_layout = QHBoxLayout(self._align_widget)
            align_layout.setContentsMargins(0, 0, 0, 0)
            align_layout.setSpacing(2)
            
            def make_btn(icon, tip_key, align_val):
                btn = QPushButton(icon)
                btn.setObjectName("smallBtn")
                btn.setFixedSize(26, 26)
                btn.setToolTip(tr(tip_key))
                btn.clicked.connect(lambda: self.option_changed.emit("align_layer", align_val))
                return btn
                
            self._btn_al = make_btn("├", "opts.align.left", "left")
            self._btn_ac = make_btn("╪", "opts.align.center_h", "center_h")
            self._btn_ar = make_btn("┤", "opts.align.right", "right")
            self._btn_at = make_btn("┬", "opts.align.top", "top")
            self._btn_am = make_btn("╫", "opts.align.center_v", "center_v")
            self._btn_ab = make_btn("┴", "opts.align.bottom", "bottom")
            
            for b in [self._btn_al, self._btn_ac, self._btn_ar]: align_layout.addWidget(b)
            align_layout.addSpacing(4)
            for b in [self._btn_at, self._btn_am, self._btn_ab]: align_layout.addWidget(b)
            
            self.layout.addWidget(self._align_widget)
            
            # --- Блок точной трансформации ---
            self._tf_widget = QWidget()
            tf_layout = QHBoxLayout(self._tf_widget)
            tf_layout.setContentsMargins(0, 0, 0, 0)
            tf_layout.setSpacing(4)
            
            def make_dsb(min_val, max_val, suffix=""):
                dsb = QDoubleSpinBox()
                dsb.setRange(min_val, max_val); dsb.setDecimals(1); dsb.setSuffix(suffix)
                dsb.setFixedWidth(64); dsb.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
                return dsb
                
            self._sp_x, self._sp_y = make_dsb(-9999, 9999, " px"), make_dsb(-9999, 9999, " px")
            self._sp_w, self._sp_h = make_dsb(-999, 999, " %"), make_dsb(-999, 999, " %")
            self._sp_a = make_dsb(-360, 360, " °")
            
            self._btn_link = QPushButton("🔗")
            self._btn_link.setCheckable(True); self._btn_link.setChecked(True)
            self._btn_link.setFixedSize(24, 24); self._btn_link.setObjectName("smallBtn")
            
            for lbl, w in [("X:", self._sp_x), ("Y:", self._sp_y)]: 
                tf_layout.addWidget(QLabel(lbl)); tf_layout.addWidget(w)
            tf_layout.addSpacing(6)
            tf_layout.addWidget(QLabel("W:")); tf_layout.addWidget(self._sp_w)
            tf_layout.addWidget(self._btn_link)
            tf_layout.addWidget(QLabel("H:")); tf_layout.addWidget(self._sp_h)
            tf_layout.addSpacing(6)
            tf_layout.addWidget(QLabel("∠:")); tf_layout.addWidget(self._sp_a)
            
            self.layout.addWidget(self._tf_widget)
            self._tf_widget.setVisible(False)
            
            self._sp_x.valueChanged.connect(self._on_user_edit)
            self._sp_y.valueChanged.connect(self._on_user_edit)
            self._sp_a.valueChanged.connect(self._on_user_edit)
            self._sp_w.valueChanged.connect(self._on_w_edit)
            self._sp_h.valueChanged.connect(self._on_h_edit)
            self.layout.addSpacing(10)

        self._apply_btn = QPushButton("✔ " + tr("opts.apply"))
        self._apply_btn.setObjectName("smallBtn")
        self._apply_btn.clicked.connect(lambda: self.option_changed.emit("move_apply", True))
        self.layout.addWidget(self._apply_btn)

        self._cancel_btn = QPushButton("✖ " + tr("opts.cancel"))
        self._cancel_btn.setObjectName("smallBtn")
        self._cancel_btn.clicked.connect(lambda: self.option_changed.emit("move_cancel", True))
        self.layout.addWidget(self._cancel_btn)
        
        self.layout.addStretch()
        
    def _on_w_edit(self, val):
        if self._updating: return
        if self._btn_link.isChecked():
            self._updating = True; self._sp_h.setValue(val); self._updating = False
        self._on_user_edit()
        
    def _on_h_edit(self, val):
        if self._updating: return
        if self._btn_link.isChecked():
            self._updating = True; self._sp_w.setValue(val); self._updating = False
        self._on_user_edit()
        
    def _on_user_edit(self, *_):
        if self._updating: return
        params = {'x': self._sp_x.value(), 'y': self._sp_y.value(), 'w': self._sp_w.value(), 'h': self._sp_h.value(), 'angle': self._sp_a.value()}
        self.option_changed.emit("transform_params", params)
        
    def update_params(self, params: dict | None):
        if not hasattr(self, "_tf_widget"): return
        if params is None:
            self._tf_widget.setVisible(False); self._align_widget.setVisible(True)
            return
        self._tf_widget.setVisible(True); self._align_widget.setVisible(False)
        self._updating = True
        self._sp_x.setValue(params.get('x', 0)); self._sp_y.setValue(params.get('y', 0))
        self._sp_w.setValue(params.get('w', 100)); self._sp_h.setValue(params.get('h', 100))
        self._sp_a.setValue(params.get('angle', 0))
        self._updating = False

    def retranslate(self):
        self._hint_lbl.setText(tr(self._hint_key))
        self._apply_btn.setText("✔ " + tr("opts.apply"))
        self._cancel_btn.setText("✖ " + tr("opts.cancel"))
        
        if hasattr(self, "_btn_al"):
            self._btn_al.setToolTip(tr("opts.align.left"))
            self._btn_ac.setToolTip(tr("opts.align.center_h"))
            self._btn_ar.setToolTip(tr("opts.align.right"))
            self._btn_at.setToolTip(tr("opts.align.top"))
            self._btn_am.setToolTip(tr("opts.align.center_v"))
            self._btn_ab.setToolTip(tr("opts.align.bottom"))
            self._btn_link.setToolTip(tr("opts.link_aspect"))
        super().retranslate()