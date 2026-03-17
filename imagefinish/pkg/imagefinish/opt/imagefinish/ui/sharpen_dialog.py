import numpy as np
import ctypes
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QDialogButtonBox, QWidget)
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor

from core.locale import tr, current as locale_current
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

def apply_conv3x3(arr, kernel):
    h, w = arr.shape[:2]
    padded = np.pad(arr[..., :3].astype(np.float32), ((1,1),(1,1),(0,0)), mode='edge')
    res = np.zeros((h, w, 3), dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            if kernel[dy, dx] != 0:
                res += padded[dy:h+dy, dx:w+dx] * kernel[dy, dx]
    return np.clip(res, 0, 255).astype(np.uint8)


class SharpenCanvas(QWidget):
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


class SharpenDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        title = tr(f"menu.sharpen.{mode}").replace('…', '')
        self.setWindowTitle(f"{tr('menu.sharpen_gallery')} - {title}")
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
        
        self.canvas = SharpenCanvas(self)
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
            
        self.amount_sl, self.amt_lbl = add_slider(tr("sharpen.amount"))
        self.radius_sl, self.rad_lbl = add_slider(tr("sharpen.radius"))
        self.noise_sl, self.noise_lbl = add_slider(tr("sharpen.reduce_noise"))
        self.thresh_sl, self.thr_lbl = add_slider(tr("sharpen.threshold"))

        for wg in [self.amount_sl, self.amt_lbl, self.radius_sl, self.rad_lbl, 
                   self.noise_sl, self.noise_lbl, self.thresh_sl, self.thr_lbl]: wg.hide()

        if self.mode == "unsharp":
            self.amount_sl.setRange(1, 500); self.amount_sl.setValue(50)
            self.radius_sl.setRange(1, 250); self.radius_sl.setValue(10) # Делим на 10 для float (1.0)
            self.thresh_sl.setRange(0, 255); self.thresh_sl.setValue(0)
            for w in [self.amount_sl, self.amt_lbl, self.radius_sl, self.rad_lbl, self.thresh_sl, self.thr_lbl]: w.show()
        elif self.mode == "smart":
            self.amount_sl.setRange(1, 500); self.amount_sl.setValue(100)
            self.radius_sl.setRange(1, 250); self.radius_sl.setValue(10)
            self.noise_sl.setRange(0, 100); self.noise_sl.setValue(10)
            for w in [self.amount_sl, self.amt_lbl, self.radius_sl, self.rad_lbl, self.noise_sl, self.noise_lbl]: w.show()
        elif self.mode in ("sharpen", "edges", "more"):
            msg = "Этот фильтр не имеет\nнастраиваемых параметров." if locale_current() == "ru" else "This filter has no\nadjustable parameters."
            lbl = QLabel(msg)
            lbl.setStyleSheet("color: #a6adc8; font-size: 12px; font-style: italic;")
            pl.addWidget(lbl)

        pl.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        pl.addWidget(btns)
        root.addWidget(props)

    def _trigger_update(self):
        self._timer.start()

    def _apply_effect(self):
        res_arr = self.orig_arr.copy()
        
        if self.mode == "sharpen":
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            res_arr[..., :3] = apply_conv3x3(self.orig_arr, kernel)
            
        elif self.mode == "more":
            kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]], dtype=np.float32)
            res_arr[..., :3] = apply_conv3x3(self.orig_arr, kernel)
            
        elif self.mode == "edges":
            gray = 0.299 * self.orig_arr[..., 2] + 0.587 * self.orig_arr[..., 1] + 0.114 * self.orig_arr[..., 0]
            gy = np.abs(np.roll(gray, -1, axis=0) - gray)
            gx = np.abs(np.roll(gray, -1, axis=1) - gray)
            edges = (gx + gy) > 15
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            sharp = apply_conv3x3(self.orig_arr, kernel)
            res_arr[edges, :3] = sharp[edges]
            
        elif self.mode in ("unsharp", "smart"):
            amt = self.amount_sl.value() / 100.0
            rad = max(1, self.radius_sl.value() // 10)
            
            base = self.orig_arr[..., :3].copy()
            if self.mode == "smart" and self.noise_sl.value() > 0:
                base = fast_box_blur_np(base, max(1, self.noise_sl.value() // 10))
                
            blurred = fast_box_blur_np(base, rad)
            diff = self.orig_arr[..., :3].astype(np.int16) - blurred.astype(np.int16)
            
            if self.mode == "unsharp":
                thresh = self.thresh_sl.value()
                mask = np.max(np.abs(diff), axis=-1, keepdims=True) > thresh
            else:
                mask = True # Smart Sharpen применяет разницу везде
                
            res_arr[..., :3] = np.where(mask, np.clip(self.orig_arr[..., :3].astype(np.float32) + diff * amt, 0, 255).astype(np.uint8), self.orig_arr[..., :3])
            
        h, w = res_arr.shape[:2]
        self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()