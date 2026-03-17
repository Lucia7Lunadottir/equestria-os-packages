import numpy as np
import ctypes
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QDialogButtonBox, QWidget, QSpinBox, QGridLayout)
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor

from core.locale import tr
from ui.adjustments_dialog import _JumpSlider


def fast_box_blur_np(arr, radius):
    r = int(radius)
    if r <= 0: return arr.copy()
    h, w, c = arr.shape
    r = min(r, max(1, min(h, w) // 2))
    pad_h = np.pad(arr, ((0,0), (r, r), (0,0)), mode='edge').astype(np.int32)
    cs_h = np.cumsum(pad_h, axis=1)
    res_h = np.empty_like(arr, dtype=np.int32)
    res_h[:, 0, :] = cs_h[:, 2*r, :]
    if w > 1: res_h[:, 1:, :] = cs_h[:, 2*r+1:, :] - cs_h[:, :-2*r-1, :]
    res_h //= (2*r + 1)
    pad_v = np.pad(res_h, ((r, r), (0,0), (0,0)), mode='edge')
    cs_v = np.cumsum(pad_v, axis=0)
    res_v = np.empty_like(res_h)
    res_v[0, :, :] = cs_v[2*r, :, :]
    if h > 1: res_v[1:, :, :] = cs_v[2*r+1:, :, :] - cs_v[:-2*r-1, :, :]
    res_v //= (2*r + 1)
    return res_v.astype(np.uint8)


class OtherFiltersCanvas(QWidget):
    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.setMouseTracking(True)
        self.zoom = 1.0
        self._pan = QPointF(0, 0)
        self._panning = False
        self._pan_last = None
        self._space = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 30, 40))
        if not self.dialog.preview_img: return
            
        w, h = self.dialog.preview_img.width(), self.dialog.preview_img.height()
        p.save()
        p.translate(self._pan)
        p.scale(self.zoom, self.zoom)
        
        tile = 16
        for y in range(0, h, tile):
            for x in range(0, w, tile):
                c = QColor(180,180,180) if (x//tile + y//tile) % 2 == 0 else QColor(220,220,220)
                p.fillRect(x, y, min(tile, w-x), min(tile, h-y), c)
                
        p.drawImage(0, 0, self.dialog.preview_img)
        p.restore()
        p.end()

    def mousePressEvent(self, ev):
        is_pan = ev.button() == Qt.MouseButton.MiddleButton or (self._space and ev.button() == Qt.MouseButton.LeftButton)
        if is_pan:
            self._panning = True
            self._pan_last = ev.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, ev):
        if self._panning and self._pan_last is not None:
            self._pan += (ev.position() - self._pan_last)
            self._pan_last = ev.position()
            self.update()

    def mouseReleaseEvent(self, ev):
        self._panning = False
        self.setCursor(Qt.CursorShape.OpenHandCursor if self._space else Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, ev):
        factor = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        new_zoom = max(0.05, min(32.0, self.zoom * factor))
        scale = new_zoom / self.zoom
        pivot = ev.position()
        self._pan = QPointF(pivot.x() - (pivot.x() - self._pan.x()) * scale, pivot.y() - (pivot.y() - self._pan.y()) * scale)
        self.zoom = new_zoom
        self.update()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def keyReleaseEvent(self, ev):
        if ev.key() == Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._space = False
            self.setCursor(Qt.CursorShape.ArrowCursor)


class OtherFiltersDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        title = tr(f"menu.other.{mode}").replace('…', '')
        self.setWindowTitle(f"{tr('menu.other')} - {title}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.resize(1000, 700)
        
        self.orig_img = layer.image.copy()
        self.preview_img = layer.image.copy()
        
        ptr = self.orig_img.constBits()
        buf = (ctypes.c_uint8 * self.orig_img.sizeInBytes()).from_address(int(ptr))
        self.orig_arr = np.ndarray((self.orig_img.height(), self.orig_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :self.orig_img.width(), :].copy()
        
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._apply_effect)

        self._build_ui()
        self._apply_effect()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        
        self.canvas = OtherFiltersCanvas(self)
        w, h = self.orig_img.width(), self.orig_img.height()
        scale = min(700 / max(1, w), 600 / max(1, h))
        self.canvas.zoom = scale
        self.canvas._pan = QPointF(50, 50)
        root.addWidget(self.canvas, 1)
        
        props = QWidget()
        props.setFixedWidth(280)
        props.setStyleSheet("background: #1e1e2e; border-left: 1px solid #313244;")
        pl = QVBoxLayout(props)
        pl.setContentsMargins(15, 15, 15, 15); pl.setSpacing(15)
        
        def add_slider(name):
            lbl = QLabel(name)
            pl.addWidget(lbl)
            sl = _JumpSlider(Qt.Orientation.Horizontal)
            sl.valueChanged.connect(self._trigger_update)
            pl.addWidget(sl)
            return sl, lbl
            
        self.radius_sl, self.rad_lbl = add_slider(tr("other.radius"))
        
        self.dx_lbl = QLabel(tr("other.horiz"))
        self.dx_sp = QSpinBox(); self.dx_sp.setRange(-9999, 9999); self.dx_sp.valueChanged.connect(self._trigger_update)
        self.dy_lbl = QLabel(tr("other.vert"))
        self.dy_sp = QSpinBox(); self.dy_sp.setRange(-9999, 9999); self.dy_sp.valueChanged.connect(self._trigger_update)
        self.edge_lbl = QLabel(tr("other.edge"))
        self.edge_combo = QComboBox()
        self.edge_combo.addItem(tr("other.wrap"), 0)
        self.edge_combo.addItem(tr("other.repeat"), 1)
        self.edge_combo.addItem(tr("other.bg"), 2)
        self.edge_combo.currentIndexChanged.connect(self._trigger_update)
        
        for w in [self.dx_lbl, self.dx_sp, self.dy_lbl, self.dy_sp, self.edge_lbl, self.edge_combo]: pl.addWidget(w)

        # Пользовательская матрица 3x3
        self.matrix_w = QWidget()
        grid = QGridLayout(self.matrix_w)
        grid.setContentsMargins(0,0,0,0); grid.setSpacing(4)
        self.k_spins = []
        for i in range(3):
            row = []
            for j in range(3):
                sp = QSpinBox(); sp.setRange(-999, 999); sp.setValue(1 if i==1 and j==1 else 0)
                sp.valueChanged.connect(self._trigger_update)
                grid.addWidget(sp, i, j)
                row.append(sp)
            self.k_spins.append(row)
            
        self.scale_lbl = QLabel(tr("other.scale"))
        self.scale_sp = QSpinBox(); self.scale_sp.setRange(1, 9999); self.scale_sp.setValue(1)
        self.scale_sp.valueChanged.connect(self._trigger_update)
        self.offset_lbl = QLabel(tr("other.offset_val"))
        self.offset_sp = QSpinBox(); self.offset_sp.setRange(-9999, 9999); self.offset_sp.setValue(0)
        self.offset_sp.valueChanged.connect(self._trigger_update)
        
        for w in [self.matrix_w, self.scale_lbl, self.scale_sp, self.offset_lbl, self.offset_sp]: pl.addWidget(w)

        for wg in [self.radius_sl, self.rad_lbl, self.dx_lbl, self.dx_sp, self.dy_lbl, self.dy_sp, 
                   self.edge_lbl, self.edge_combo, self.matrix_w, self.scale_lbl, self.scale_sp, self.offset_lbl, self.offset_sp]:
            wg.hide()

        if self.mode == "high_pass":
            self.radius_sl.setRange(1, 250); self.radius_sl.setValue(10)
            self.radius_sl.show(); self.rad_lbl.show()
        elif self.mode in ("minimum", "maximum"):
            self.radius_sl.setRange(1, 100); self.radius_sl.setValue(1)
            self.radius_sl.show(); self.rad_lbl.show()
        elif self.mode == "offset":
            for wg in [self.dx_lbl, self.dx_sp, self.dy_lbl, self.dy_sp, self.edge_lbl, self.edge_combo]: wg.show()
        elif self.mode == "custom":
            for wg in [self.matrix_w, self.scale_lbl, self.scale_sp, self.offset_lbl, self.offset_sp]: wg.show()

        pl.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        pl.addWidget(btns)
        root.addWidget(props)

    def _trigger_update(self):
        self._timer.start()

    def _apply_effect(self):
        res_arr = self.orig_arr.copy()
        h, w = res_arr.shape[:2]
        
        if self.mode == "high_pass":
            r = self.radius_sl.value()
            blurred = fast_box_blur_np(self.orig_arr, r)
            res = self.orig_arr[..., :3].astype(np.float32) - blurred[..., :3].astype(np.float32) + 128.0
            res_arr[..., :3] = np.clip(res, 0, 255).astype(np.uint8)
            
        elif self.mode in ("minimum", "maximum"):
            r = self.radius_sl.value()
            op = np.minimum if self.mode == "minimum" else np.maximum
            
            padded_x = np.pad(self.orig_arr[..., :3], ((0,0), (r,r), (0,0)), mode='edge')
            tmp = padded_x[:, r:w+r, :]
            for i in range(-r, r+1): tmp = op(tmp, padded_x[:, r+i : w+r+i, :]) if i != -r else padded_x[:, r+i : w+r+i, :]
                
            padded_y = np.pad(tmp, ((r,r), (0,0), (0,0)), mode='edge')
            res = padded_y[r:h+r, :, :]
            for i in range(-r, r+1): res = op(res, padded_y[r+i : h+r+i, :, :]) if i != -r else padded_y[r+i : h+r+i, :, :]
                
            res_arr[..., :3] = res
            
        elif self.mode == "offset":
            dx, dy = self.dx_sp.value(), self.dy_sp.value()
            edge_mode = self.edge_combo.currentIndex()
            if edge_mode == 0:
                res_arr = np.roll(np.roll(self.orig_arr, dy, axis=0), dx, axis=1)
            elif edge_mode == 1:
                Y, X = np.ogrid[:h, :w]
                Y = np.clip(Y - dy, 0, h - 1); X = np.clip(X - dx, 0, w - 1)
                res_arr = self.orig_arr[Y, X]
            elif edge_mode == 2:
                res_arr.fill(0)
                y1_src, y2_src = max(0, -dy), min(h, h - dy); x1_src, x2_src = max(0, -dx), min(w, w - dx)
                y1_dst, y2_dst = max(0, dy), min(h, h + dy); x1_dst, x2_dst = max(0, dx), min(w, w + dx)
                if y1_src < y2_src and x1_src < x2_src: res_arr[y1_dst:y2_dst, x1_dst:x2_dst] = self.orig_arr[y1_src:y2_src, x1_src:x2_src]
                
        elif self.mode == "custom":
            kernel = np.array([[self.k_spins[i][j].value() for j in range(3)] for i in range(3)], dtype=np.float32)
            scale, offset = self.scale_sp.value(), self.offset_sp.value()
            padded = np.pad(self.orig_arr[..., :3].astype(np.float32), ((1,1),(1,1),(0,0)), mode='edge')
            res = np.zeros((h, w, 3), dtype=np.float32)
            for dy in range(3):
                for dx in range(3):
                    if kernel[dy, dx] != 0: res += padded[dy:h+dy, dx:w+dx] * kernel[dy, dx]
            res_arr[..., :3] = np.clip(res / scale + offset, 0, 255).astype(np.uint8)
            
        self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()