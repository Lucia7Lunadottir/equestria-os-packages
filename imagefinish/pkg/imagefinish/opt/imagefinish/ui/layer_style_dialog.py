from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QStackedWidget,
                             QCheckBox, QPushButton, QSpinBox, QComboBox, QWidget, QDialogButtonBox, QListWidgetItem, QFormLayout, QDial)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QIcon
from ui.gradient_editor import GradientPreviewWidget, GradientEditorDialog
from core.locale import tr
from core.adjustments._widgets import _ColorButton
from ui.adjustments_dialog import _JumpSlider

def _slider_spin(lo: int, hi: int, val: int):
    sl = _JumpSlider(Qt.Orientation.Horizontal)
    sl.setRange(lo, hi)
    sl.setValue(val)
    sp = QSpinBox()
    sp.setRange(lo, hi)
    sp.setValue(val)
    sp.setFixedWidth(68)
    sl.valueChanged.connect(sp.setValue)
    sp.valueChanged.connect(sl.setValue)
    return sl, sp

class LayerStyleDialog(QDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ls.title"))
        self.setMinimumSize(600, 450)
        self.layer = layer
        self.canvas_refresh = canvas_refresh
        
        import copy
        self.original_styles = copy.deepcopy(getattr(layer, "layer_styles", None)) or {}
        self.current_styles = copy.deepcopy(self.original_styles)
        
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._apply_preview)
        
        self.effects_names = {}
        self._build_ui()
        self._load_data()
        
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        
        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(160)
        self.list_widget.currentRowChanged.connect(self.stack.setCurrentIndex if hasattr(self, 'stack') else lambda x: x)
        self.list_widget.itemChanged.connect(self._trigger)
        
        self.stack = QStackedWidget()
        self.list_widget.currentRowChanged.connect(self.stack.setCurrentIndex)
        
        self.pages = {}
        effects = [
            ("bevel", tr("ls.bevel")), ("stroke", tr("ls.stroke")),
            ("inner_shadow", tr("ls.inner_shadow")), ("inner_glow", tr("ls.inner_glow")),
            ("satin", tr("ls.satin")), ("color_overlay", tr("ls.color_overlay")),
            ("gradient_overlay", tr("ls.gradient_overlay")), ("pattern_overlay", tr("ls.pattern_overlay")),
            ("outer_glow", tr("ls.outer_glow")), ("drop_shadow", tr("ls.drop_shadow")),
            ("offset", tr("ls.offset")),
        ]
        
        for key, name in effects:
            self.effects_names[key] = name
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list_widget.addItem(item)
            
            page = QWidget()
            lo = QVBoxLayout(page)
            lo.setContentsMargins(10, 0, 0, 0)
            title = QLabel(name)
            title.setStyleSheet("font-weight: bold; font-size: 14px; border-bottom: 1px solid #45475a; padding-bottom: 4px;")
            lo.addWidget(title)
            
            form = QFormLayout()
            lo.addLayout(form)
            lo.addStretch()
            
            self.pages[key] = {"widget": page, "form": form, "inputs": {}}
            self.stack.addWidget(page)
            self._build_page(key, form)
            
        root.addWidget(self.list_widget)
        root.addWidget(self.stack, 1)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.setOrientation(Qt.Orientation.Vertical)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _build_page(self, key, form):
        inputs = self.pages[key]["inputs"]
        def add_slider(name, prop, lo, hi, val, suffix=""):
            sl, sp = _slider_spin(lo, hi, val)
            sp.setSuffix(suffix)
            w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0,0,0,0)
            h.addWidget(sl); h.addWidget(sp)
            form.addRow(name, w)
            sl.valueChanged.connect(self._trigger)
            inputs[prop] = sp
        def add_color(name, prop, val):
            btn = _ColorButton(val)
            btn.colorChanged.connect(self._trigger)
            form.addRow(name, btn)
            inputs[prop] = btn
        def add_combo(name, prop, items):
            cb = QComboBox()
            for k, v in items: cb.addItem(k, v)
            cb.currentIndexChanged.connect(self._trigger)
            form.addRow(name, cb)
            inputs[prop] = cb
        def add_angle(name, prop, val):
            dial = QDial()
            dial.setRange(-180, 180)
            dial.setWrapping(True)
            dial.setNotchesVisible(True)
            dial.setFixedSize(40, 40)
            dial.setValue(val)
            sp = QSpinBox()
            sp.setRange(-180, 180)
            sp.setValue(val)
            sp.setSuffix("°")
            sp.setFixedWidth(68)
            dial.valueChanged.connect(sp.setValue)
            sp.valueChanged.connect(dial.setValue)
            w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0,0,0,0)
            h.addWidget(dial); h.addWidget(sp)
            form.addRow(name, w)
            dial.valueChanged.connect(self._trigger)
            inputs[prop] = sp
        def add_pattern(name, prop, val):
            cb = QComboBox()
            import os, glob
            pat_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patterns")
            if os.path.exists(pat_dir):
                for f in glob.glob(os.path.join(pat_dir, '*.[pP][nN][gG]')) + glob.glob(os.path.join(pat_dir, '*.[jJ][pP][gG]')):
                    cb.addItem(QIcon(f), os.path.splitext(os.path.basename(f))[0], f)
            cb.currentIndexChanged.connect(self._trigger)
            form.addRow(name, cb)
            inputs[prop] = cb
        def add_gradient(name, prop, val):
            preview = GradientPreviewWidget()
            preview.set_stops(val)
            def _open_editor():
                mw = self.window()
                fg = getattr(mw._canvas, 'fg_color', QColor(0,0,0)) if hasattr(mw, '_canvas') else QColor(0,0,0)
                bg = getattr(mw._canvas, 'bg_color', QColor(255,255,255)) if hasattr(mw, '_canvas') else QColor(255,255,255)
                dlg = GradientEditorDialog(preview._stops, fg, bg, self)
                if dlg.exec():
                    preview.set_stops(dlg.result_stops())
                    self._trigger()
            preview.clicked.connect(_open_editor)
            form.addRow(name, preview)
            inputs[prop] = preview

        blend_modes = [
            (tr("blend.normal"),      "SourceOver"),
            (tr("blend.multiply"),    "Multiply"),
            (tr("blend.screen"),      "Screen"),
            (tr("blend.overlay"),     "Overlay"),
            (tr("blend.darken"),      "Darken"),
            (tr("blend.lighten"),     "Lighten"),
            (tr("blend.color_dodge"), "ColorDodge"),
            (tr("blend.color_burn"),  "ColorBurn"),
            (tr("blend.hard_light"),  "HardLight"),
            (tr("blend.soft_light"),  "SoftLight"),
            (tr("blend.difference"),  "Difference"),
            (tr("blend.exclusion"),   "Exclusion"),
        ]

        if key in ("drop_shadow", "inner_shadow"):
            add_combo(tr("ls.blend_mode"), "blend_mode", blend_modes)
            add_color(tr("ls.color"), "color", QColor(0,0,0))
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 75, "%")
            add_angle(tr("ls.angle"), "angle", 90)
            add_slider(tr("ls.distance"), "distance", 0, 100, 5, "px")
            if key == "drop_shadow": add_slider(tr("ls.spread"), "spread", 0, 100, 0, "%")
            add_slider(tr("ls.size"), "size", 0, 100, 5, "px")
        elif key == "bevel":
            add_slider(tr("ls.size"), "size", 0, 100, 5, "px")
            add_slider(tr("ls.distance"), "distance", 0, 100, 5, "px")
            add_angle(tr("ls.angle"), "angle", 90)
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 75, "%")
            add_color(tr("ls.highlight_color"), "color", QColor(255, 255, 255))
            add_color(tr("ls.shadow_color"), "shadow_color", QColor(0, 0, 0))
        elif key == "inner_glow":
            add_combo(tr("ls.blend_mode"), "blend_mode", blend_modes)
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 75, "%")
            add_color(tr("ls.color"), "color", QColor(255, 255, 150))
            add_slider(tr("ls.size"), "size", 0, 100, 5, "px")
        elif key == "satin":
            add_combo(tr("ls.blend_mode"), "blend_mode", blend_modes)
            add_color(tr("ls.color"), "color", QColor(0, 0, 0))
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 50, "%")
            add_angle(tr("ls.angle"), "angle", 90)
            add_slider(tr("ls.distance"), "distance", 0, 100, 11, "px")
            add_slider(tr("ls.size"), "size", 0, 100, 14, "px")
        elif key == "outer_glow":
            add_combo(tr("ls.blend_mode"), "blend_mode", blend_modes)
            add_color(tr("ls.color"), "color", QColor(255,255,150))
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 75, "%")
            add_slider(tr("ls.size"), "size", 0, 100, 5, "px")
        elif key == "stroke":
            add_slider(tr("ls.size"), "size", 1, 100, 3, "px")
            add_combo(tr("ls.blend_mode"), "blend_mode", blend_modes)
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 100, "%")
            add_color(tr("ls.color"), "color", QColor(0,0,0))
        elif key == "color_overlay":
            add_combo(tr("ls.blend_mode"), "blend_mode", blend_modes)
            add_color(tr("ls.color"), "color", QColor(255,0,0))
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 100, "%")
        elif key == "gradient_overlay":
            add_combo(tr("ls.blend_mode"), "blend_mode", blend_modes)
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 100, "%")
            
            add_gradient(tr("fill_layer.gradient"), "stops", [(0.0, QColor(0,0,0)), (1.0, QColor(255,255,255))])
            gtypes = [(tr("opts.gradient.linear"), "linear"), (tr("opts.gradient.radial"), "radial")]
            add_combo(tr("opts.gradient.type"), "type", gtypes)
            add_angle(tr("ls.angle"), "angle", 90)
        elif key == "pattern_overlay":
            add_combo(tr("ls.blend_mode"), "blend_mode", blend_modes)
            add_slider(tr("ls.opacity"), "opacity", 0, 100, 100, "%")
            add_pattern(tr("ls.pattern"), "pattern", "")
            add_slider(tr("ls.scale"), "scale", 1, 1000, 100, "%")
        elif key == "offset":
            add_slider(tr("ls.offset_x"), "dx_pct", -100, 100, 0, "%")
            add_slider(tr("ls.offset_y"), "dy_pct", -100, 100, 0, "%")
            edge_modes = [
                (tr("other.wrap"), "wrap"),
                (tr("other.repeat"), "repeat"),
                (tr("other.bg"), "transparent")
            ]
            add_combo(tr("other.edge"), "edge_mode", edge_modes)
            
            reset_btn = QPushButton(tr("adj.reset"))
            reset_btn.clicked.connect(lambda: (inputs["dx_pct"].setValue(0), inputs["dy_pct"].setValue(0), inputs["edge_mode"].setCurrentIndex(0)))
            form.addRow("", reset_btn)

    def _read_data(self):
        for key, p in self.pages.items():
            inputs = p["inputs"]
            item = self.list_widget.findItems(self.effects_names[key], Qt.MatchFlag.MatchExactly)[0]
            state = {"enabled": item.checkState() == Qt.CheckState.Checked}
            for prop, widget in inputs.items():
                if isinstance(widget, QSpinBox): state[prop] = widget.value()
                elif hasattr(widget, "color"): state[prop] = widget.color()
                elif isinstance(widget, QComboBox): state[prop] = widget.currentData()
                elif isinstance(widget, GradientPreviewWidget): state[prop] = widget._stops
            self.current_styles[key] = state

    def _load_data(self):
        self.list_widget.blockSignals(True)
        for key, p in self.pages.items():
            inputs = p["inputs"]
            state = self.current_styles.get(key, {})
            item = self.list_widget.findItems(self.effects_names[key], Qt.MatchFlag.MatchExactly)[0]
            item.setCheckState(Qt.CheckState.Checked if state.get("enabled") else Qt.CheckState.Unchecked)
            for prop, widget in inputs.items():
                if prop in state:
                    widget.blockSignals(True)
                    if isinstance(widget, QSpinBox): widget.setValue(state[prop])
                    elif hasattr(widget, "set_color"): widget.set_color(state[prop])
                    elif isinstance(widget, QComboBox):
                        idx = widget.findData(state[prop])
                        if idx >= 0: widget.setCurrentIndex(idx)
                    elif isinstance(widget, GradientPreviewWidget):
                        widget.set_stops(state[prop])
                    widget.blockSignals(False)
        self.list_widget.blockSignals(False)

    def _trigger(self, *args):
        self._read_data()
        self._timer.start()

    def _apply_preview(self):
        self.layer.layer_styles = self.current_styles
        self.canvas_refresh()

    def accept(self):
        self._read_data()
        self.layer.layer_styles = self.current_styles
        super().accept()

    def reject(self):
        self._timer.stop()
        self.layer.layer_styles = self.original_styles
        self.canvas_refresh()
        super().reject()