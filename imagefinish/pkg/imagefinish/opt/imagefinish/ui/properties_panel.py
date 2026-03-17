from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QScrollArea, QFrame, QGridLayout, QSpinBox,
                             QPushButton, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QPainter, QColor, QPixmap, QIcon
from core.locale import tr

_TYPE_LABELS = {
    "raster":       "Raster",
    "text":         "Text Layer",
    "vector":       "Vector",
    "adjustment":   "Adjustment",
    "fill":         "Fill",
    "smart_object": "Smart Object",
    "group":        "Group",
    "artboard":     "Artboard",
}

LABEL_STYLE  = "color:#a6adc8;font-size:11px;background:transparent;"
VALUE_STYLE  = "color:#cdd6f4;font-size:11px;background:transparent;"
HEADER_STYLE = ("color:#7f849c;font-size:10px;font-weight:bold;"
                "letter-spacing:1px;background:transparent;padding:6px 0 3px 0;")
SPIN_STYLE   = ("QSpinBox{background:#313244;color:#cdd6f4;border:none;"
                "padding:2px 4px;border-radius:3px;font-size:11px;}"
                "QSpinBox::up-button,QSpinBox::down-button{width:14px;}"
                "QSpinBox:focus{border:1px solid #cba6f7;}")
ALIGN_BTN    = ("QPushButton{background:#313244;color:#cdd6f4;border:none;"
                "border-radius:3px;font-size:11px;padding:3px;}"
                "QPushButton:hover{background:#45475a;}"
                "QPushButton:pressed{background:#cba6f7;color:#1e1e2e;}")
SEP_STYLE    = "background:#313244;max-height:1px;"


def _sep():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(SEP_STYLE)
    return f


def _header(text):
    l = QLabel(text)
    l.setStyleSheet(HEADER_STYLE)
    return l


class PropertiesPanel(QWidget):
    # Emitted when position/size changed so main_window can refresh canvas + push history
    transform_changed = pyqtSignal(int, int)   # new offset x, y
    align_requested   = pyqtSignal(str)        # "left","center_h","right","top","center_v","bottom"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas = None
        self._blocking = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:#1e1e2e;border:none;")

        body = QWidget()
        body.setStyleSheet("background:#1e1e2e;")
        v = QVBoxLayout(body)
        v.setContentsMargins(8, 4, 8, 8)
        v.setSpacing(4)

        # ── Transform ─────────────────────────────────────────────────────
        self._hdr_transform = _header("TRANSFORM")
        v.addWidget(self._hdr_transform)
        v.addWidget(_sep())

        grid = QGridLayout()
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        def lbl(t): l = QLabel(t); l.setStyleSheet(LABEL_STYLE); return l
        def spin(lo=-99999, hi=99999):
            s = QSpinBox(); s.setRange(lo, hi); s.setStyleSheet(SPIN_STYLE)
            s.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows); return s

        self._x_spin = spin(); self._y_spin = spin()
        self._w_spin = spin(1, 99999); self._w_spin.setEnabled(False)
        self._h_spin = spin(1, 99999); self._h_spin.setEnabled(False)

        grid.addWidget(lbl("X:"), 0, 0); grid.addWidget(self._x_spin, 0, 1)
        grid.addWidget(lbl("Y:"), 0, 2); grid.addWidget(self._y_spin, 0, 3)
        grid.addWidget(lbl("W:"), 1, 0); grid.addWidget(self._w_spin, 1, 1)
        grid.addWidget(lbl("H:"), 1, 2); grid.addWidget(self._h_spin, 1, 3)
        v.addLayout(grid)

        self._x_spin.valueChanged.connect(self._on_pos_changed)
        self._y_spin.valueChanged.connect(self._on_pos_changed)

        # ── Alignment ─────────────────────────────────────────────────────
        self._hdr_align = _header("ALIGN TO CANVAS")
        v.addWidget(self._hdr_align)
        v.addWidget(_sep())

        align_row1 = QHBoxLayout()
        align_row2 = QHBoxLayout()
        align_row1.setSpacing(3); align_row2.setSpacing(3)

        def abtn(icon_char, tip, slot):
            b = QPushButton(icon_char); b.setStyleSheet(ALIGN_BTN)
            b.setFixedSize(32, 26); b.setToolTip(tip)
            b.clicked.connect(slot); return b

        self._btn_al  = abtn("⇤", "Align Left",             lambda: self.align_requested.emit("left"))
        self._btn_ac  = abtn("↔", "Align Center H",          lambda: self.align_requested.emit("center_h"))
        self._btn_ar  = abtn("⇥", "Align Right",             lambda: self.align_requested.emit("right"))
        self._btn_at  = abtn("⇡", "Align Top",               lambda: self.align_requested.emit("top"))
        self._btn_avc = abtn("↕", "Align Center V",           lambda: self.align_requested.emit("center_v"))
        self._btn_ab  = abtn("⇣", "Align Bottom",             lambda: self.align_requested.emit("bottom"))

        for b in (self._btn_al, self._btn_ac, self._btn_ar): align_row1.addWidget(b)
        align_row1.addStretch()
        for b in (self._btn_at, self._btn_avc, self._btn_ab): align_row2.addWidget(b)
        align_row2.addStretch()
        v.addLayout(align_row1)
        v.addLayout(align_row2)

        # ── Layer info ────────────────────────────────────────────────────
        self._hdr_info = _header("LAYER INFO")
        v.addWidget(self._hdr_info)
        v.addWidget(_sep())

        info_grid = QGridLayout()
        info_grid.setContentsMargins(0, 4, 0, 4)
        info_grid.setHorizontalSpacing(8)
        info_grid.setVerticalSpacing(5)
        info_grid.setColumnStretch(1, 1)

        self._lbl_name  = lbl(tr("props.name"));    self._val_name  = QLabel("—"); self._val_name.setStyleSheet(VALUE_STYLE)
        self._lbl_type  = lbl(tr("props.type"));    self._val_type  = QLabel("—"); self._val_type.setStyleSheet(VALUE_STYLE)
        self._lbl_blend = lbl(tr("props.blend"));   self._val_blend = QLabel("—"); self._val_blend.setStyleSheet(VALUE_STYLE)
        self._lbl_op    = lbl(tr("props.opacity")); self._val_op    = QLabel("—"); self._val_op.setStyleSheet(VALUE_STYLE)
        self._lbl_vis   = lbl(tr("props.visible")); self._val_vis   = QLabel("—"); self._val_vis.setStyleSheet(VALUE_STYLE)

        for row_i, (lw, vw) in enumerate([
            (self._lbl_name,  self._val_name),
            (self._lbl_type,  self._val_type),
            (self._lbl_blend, self._val_blend),
            (self._lbl_op,    self._val_op),
            (self._lbl_vis,   self._val_vis),
        ]):
            info_grid.addWidget(lw, row_i, 0, Qt.AlignmentFlag.AlignTop)
            info_grid.addWidget(vw, row_i, 1, Qt.AlignmentFlag.AlignTop)
        v.addLayout(info_grid)

        v.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    # ── Internal slot ──────────────────────────────────────────────────────
    def _on_pos_changed(self):
        if self._blocking:
            return
        layer = self._active_layer()
        if layer is None:
            return
        x, y = self._x_spin.value(), self._y_spin.value()
        layer.offset = QPoint(x, y)
        self.transform_changed.emit(x, y)

    def _active_layer(self):
        if self._canvas and self._canvas.document:
            return self._canvas.document.get_active_layer()
        return None

    # ── Public API ─────────────────────────────────────────────────────────
    def refresh(self, canvas):
        self._canvas = canvas
        layer = None
        if canvas and canvas.document:
            layer = canvas.document.get_active_layer()

        self._blocking = True
        if layer is None:
            self._x_spin.setValue(0); self._y_spin.setValue(0)
            self._w_spin.setValue(0); self._h_spin.setValue(0)
            self._val_name.setText("—"); self._val_type.setText("—")
            self._val_blend.setText("—"); self._val_op.setText("—")
            self._val_vis.setText("—")
            for b in (self._btn_al, self._btn_ac, self._btn_ar,
                      self._btn_at, self._btn_avc, self._btn_ab):
                b.setEnabled(False)
        else:
            off = getattr(layer, "offset", QPoint(0, 0))
            self._x_spin.setValue(off.x())
            self._y_spin.setValue(off.y())
            img = layer.image
            if img and not img.isNull():
                self._w_spin.setValue(img.width())
                self._h_spin.setValue(img.height())
            ltype = getattr(layer, "layer_type", "raster")
            self._val_name.setText(layer.name)
            self._val_type.setText(_TYPE_LABELS.get(ltype, ltype.capitalize()))
            self._val_blend.setText(getattr(layer, "blend_mode", "Normal"))
            self._val_op.setText(f"{int(layer.opacity * 100)}%")
            self._val_vis.setText("Yes" if layer.visible else "No")
            for b in (self._btn_al, self._btn_ac, self._btn_ar,
                      self._btn_at, self._btn_avc, self._btn_ab):
                b.setEnabled(True)
        self._blocking = False

    def retranslate(self):
        self._hdr_transform.setText(tr("props.transform") if tr("props.transform") != "props.transform" else "TRANSFORM")
        self._hdr_align.setText(tr("props.align")     if tr("props.align")     != "props.align"     else "ALIGN TO CANVAS")
        self._hdr_info.setText(tr("props.info")       if tr("props.info")      != "props.info"      else "LAYER INFO")
        self._lbl_name.setText(tr("props.name")       if tr("props.name")      != "props.name"      else "Name:")
        self._lbl_type.setText(tr("props.type")       if tr("props.type")      != "props.type"      else "Type:")
        self._lbl_blend.setText(tr("props.blend")     if tr("props.blend")     != "props.blend"     else "Blend Mode:")
        self._lbl_op.setText(tr("props.opacity")      if tr("props.opacity")   != "props.opacity"   else "Opacity:")
        self._lbl_vis.setText(tr("props.visible")     if tr("props.visible")   != "props.visible"   else "Visible:")
