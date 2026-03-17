import numpy as np
import ctypes
import math
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QDialogButtonBox, QWidget, QCheckBox)
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor, QPen

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
    if w > 1:
        res_h[:, 1:, :] = cs_h[:, 2*r+1:, :] - cs_h[:, :-2*r-1, :]
    res_h //= (2*r + 1)
    
    pad_v = np.pad(res_h, ((r, r), (0,0), (0,0)), mode='edge')
    cs_v = np.cumsum(pad_v, axis=0)
    res_v = np.empty_like(res_h)
    res_v[0, :, :] = cs_v[2*r, :, :]
    if h > 1:
        res_v[1:, :, :] = cs_v[2*r+1:, :, :] - cs_v[:-2*r-1, :, :]
    res_v //= (2*r + 1)
    return res_v.astype(np.uint8)


class NoiseCanvas(QWidget):
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


class NoiseDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        mode_keys = {
            "add_noise": "menu.noise.add",
            "despeckle": "menu.noise.despeckle",
            "dust_scratches": "menu.noise.dust",
            "median": "menu.noise.median",
            "reduce_noise": "menu.noise.reduce"
        }
        title = tr(mode_keys.get(mode, "menu.noise")).replace('…', '')
        self.setWindowTitle(f"{tr('menu.noise')} - {title}")
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
        
        self.canvas = NoiseCanvas(self)
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
            
        self.amount_sl, self.amt_lbl = add_slider(tr("noise.amount"))
        self.radius_sl, self.rad_lbl = add_slider(tr("noise.radius"))
        self.threshold_sl, self.thr_lbl = add_slider(tr("noise.threshold"))
        self.strength_sl, self.str_lbl = add_slider(tr("noise.strength"))
        self.preserve_sl, self.prs_lbl = add_slider(tr("noise.preserve"))
        self.color_sl, self.col_lbl = add_slider(tr("noise.color"))
        
        self.dist_lbl = QLabel(tr("noise.distribution"))
        self.dist_combo = QComboBox()
        self.dist_combo.addItem(tr("noise.uniform"), 0)
        self.dist_combo.addItem(tr("noise.gaussian"), 1)
        self.dist_combo.currentIndexChanged.connect(self._trigger_update)
        pl.addWidget(self.dist_lbl)
        pl.addWidget(self.dist_combo)
        
        self.mono_cb = QCheckBox(tr("noise.monochromatic"))
        self.mono_cb.toggled.connect(self._trigger_update)
        pl.addWidget(self.mono_cb)

        for wg in [self.amount_sl, self.amt_lbl, self.radius_sl, self.rad_lbl, 
                   self.threshold_sl, self.thr_lbl, self.strength_sl, self.str_lbl,
                   self.preserve_sl, self.prs_lbl, self.color_sl, self.col_lbl,
                   self.dist_lbl, self.dist_combo, self.mono_cb]:
            wg.hide()

        if self.mode == "add_noise":
            self.amount_sl.setRange(1, 400); self.amount_sl.setValue(12)
            self.amount_sl.show(); self.amt_lbl.show()
            self.dist_lbl.show(); self.dist_combo.show(); self.mono_cb.show()
        elif self.mode == "dust_scratches":
            self.radius_sl.setRange(1, 50); self.radius_sl.setValue(1)
            self.radius_sl.show(); self.rad_lbl.show()
            self.threshold_sl.setRange(0, 255); self.threshold_sl.setValue(0)
            self.threshold_sl.show(); self.thr_lbl.show()
        elif self.mode == "median":
            self.radius_sl.setRange(1, 50); self.radius_sl.setValue(1)
            self.radius_sl.show(); self.rad_lbl.show()
        elif self.mode == "reduce_noise":
            self.strength_sl.setRange(1, 10); self.strength_sl.setValue(5)
            self.strength_sl.show(); self.str_lbl.show()
            self.preserve_sl.setRange(0, 100); self.preserve_sl.setValue(50)
            self.preserve_sl.show(); self.prs_lbl.show()
            self.color_sl.setRange(0, 100); self.color_sl.setValue(50)
            self.color_sl.show(); self.col_lbl.show()
        elif self.mode == "despeckle":
            from core.locale import current as locale_current
            msg = "Этот фильтр не имеет\nнастраиваемых параметров." if locale_current() == "ru" else "This filter has no\nadjustable parameters."
            no_param_lbl = QLabel(msg)
            no_param_lbl.setStyleSheet("color: #a6adc8; font-size: 12px; font-style: italic;")
            pl.addWidget(no_param_lbl)

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
        
        if self.mode == "add_noise":
            amt = self.amount_sl.value() / 100.0
            is_gauss = self.dist_combo.currentIndex() == 1
            is_mono = self.mono_cb.isChecked()
            
            shape = (h, w, 1) if is_mono else (h, w, 3)
            if is_gauss: noise = np.random.normal(0, amt * 127, shape)
            else: noise = np.random.uniform(-amt * 255, amt * 255, shape)
                
            res_arr[..., :3] = np.clip(self.orig_arr[..., :3].astype(np.float32) + noise, 0, 255).astype(np.uint8)
            
        elif self.mode == "despeckle":
            padded = np.pad(self.orig_arr[..., :3], ((1,1),(1,1),(0,0)), mode='edge')
            stack = np.stack([padded[dy:h+dy, dx:w+dx] for dy in range(3) for dx in range(3)], axis=-1)
            res_arr[..., :3] = np.median(stack, axis=-1).astype(np.uint8)
            
        elif self.mode in ("dust_scratches", "median"):
            r = self.radius_sl.value()
            thresh = self.threshold_sl.value() if self.mode == "dust_scratches" else 0
            
            current = self.orig_arr[..., :3].copy()
            iters = min(r, 10) # Ограничиваем количество проходов (эмуляция широкой медианы без падения FPS)
            for _ in range(iters):
                padded = np.pad(current, ((1,1),(1,1),(0,0)), mode='edge')
                stack = np.stack([padded[dy:h+dy, dx:w+dx] for dy in range(3) for dx in range(3)], axis=-1)
                current = np.median(stack, axis=-1).astype(np.uint8)
                
            if thresh > 0:
                diff = np.abs(self.orig_arr[..., :3].astype(np.int16) - current.astype(np.int16))
                mask = np.max(diff, axis=-1, keepdims=True) > thresh
                res_arr[..., :3] = np.where(mask, current, self.orig_arr[..., :3])
            else:
                res_arr[..., :3] = current
                
        elif self.mode == "reduce_noise":
            st = self.strength_sl.value()
            pr = self.preserve_sl.value() / 100.0
            cn = self.color_sl.value() / 100.0
            
            blurred = fast_box_blur_np(self.orig_arr, st * 2)
            
            if cn > 0:
                luma = self.orig_arr[..., :3].mean(axis=-1, keepdims=True)
                chroma = self.orig_arr[..., :3].astype(np.float32) - luma
                chroma_blur_arr = np.clip(chroma + 128, 0, 255).astype(np.uint8)
                chroma_blur_arr = np.concatenate([chroma_blur_arr, np.zeros((h,w,1), dtype=np.uint8)], axis=-1)
                chroma_blurred = fast_box_blur_np(chroma_blur_arr, st * 3)[..., :3].astype(np.float32) - 128
                chroma = chroma * (1 - cn) + chroma_blurred * cn
                base = np.clip(luma + chroma, 0, 255).astype(np.uint8)
            else:
                base = self.orig_arr[..., :3].copy()
                
            diff = np.abs(base.astype(np.float32) - blurred[..., :3].astype(np.float32)).mean(axis=-1, keepdims=True)
            edge_thresh = 5 + pr * 45
            weight = np.clip(1.0 - (diff / edge_thresh), 0.0, 1.0)
            
            final = base.astype(np.float32) * (1 - weight) + blurred[..., :3].astype(np.float32) * weight
            res_arr[..., :3] = final.astype(np.uint8)
            
        self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()