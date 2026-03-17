import numpy as np
import ctypes
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QDialogButtonBox, QWidget)
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor

from core.locale import tr
from ui.adjustments_dialog import _JumpSlider


class PixelateCanvas(QWidget):
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


class PixelateDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        title = tr(f"menu.pixelate.{mode}").replace('…', '')
        self.setWindowTitle(f"{tr('menu.pixelate')} - {title}")
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
        
        self.canvas = PixelateCanvas(self)
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
        
        self.amount_lbl = QLabel(tr("pixelate.radius"))
        self.amount_sl = _JumpSlider(Qt.Orientation.Horizontal)
        self.amount_sl.valueChanged.connect(self._trigger_update)
        
        self.type_lbl = QLabel(tr("pixelate.type"))
        self.type_combo = QComboBox()
        self.type_combo.currentIndexChanged.connect(self._trigger_update)
        
        pl.addWidget(self.amount_lbl)
        pl.addWidget(self.amount_sl)
        pl.addWidget(self.type_lbl)
        pl.addWidget(self.type_combo)
        
        self.amount_lbl.hide(); self.amount_sl.hide()
        self.type_lbl.hide(); self.type_combo.hide()

        if self.mode in ("mosaic", "crystallize", "pointillize", "color_halftone"):
            self.amount_lbl.show(); self.amount_sl.show()
            if self.mode == "mosaic":
                self.amount_sl.setRange(2, 200); self.amount_sl.setValue(10)
            elif self.mode == "color_halftone":
                self.amount_sl.setRange(4, 127); self.amount_sl.setValue(8)
            else:
                self.amount_sl.setRange(3, 300); self.amount_sl.setValue(10)
                
        elif self.mode == "mezzotint":
            self.type_lbl.show(); self.type_combo.show()
            for t in ["fine_dots", "medium_dots", "grainy_dots", "short_lines", "medium_lines", "long_lines", "short_strokes", "medium_strokes", "long_strokes"]:
                self.type_combo.addItem(tr(f"pixelate.mezzotint.{t}"), t)
        elif self.mode in ("facet", "fragment"):
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
        
        if self.mode == "mosaic":
            s = max(2, self.amount_sl.value())
            Y, X = np.ogrid[:h, :w]
            Y_idx = np.clip((Y // s) * s + s // 2, 0, h - 1)
            X_idx = np.clip((X // s) * s + s // 2, 0, w - 1)
            res_arr[..., :3] = self.orig_arr[Y_idx, X_idx, :3]
            
        elif self.mode in ("crystallize", "pointillize"):
            s = max(3, self.amount_sl.value())
            small_h, small_w = (h + s - 1) // s, (w + s - 1) // s
            
            grid_y, grid_x = np.mgrid[:small_h, :small_w]
            cy = grid_y * s + s // 2
            cx = grid_x * s + s // 2
            
            np.random.seed(42)
            cy = np.clip(cy + np.random.randint(-s//2, s//2, (small_h, small_w)), 0, h - 1)
            cx = np.clip(cx + np.random.randint(-s//2, s//2, (small_h, small_w)), 0, w - 1)
            
            Y, X = np.ogrid[:h, :w]
            grid_Y, grid_X = Y // s, X // s
            
            min_dist = np.full((h, w), 1e9, dtype=np.float32)
            owner_y, owner_x = np.zeros((h, w), dtype=np.int32), np.zeros((h, w), dtype=np.int32)
            
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    gy = np.clip(grid_Y + dy, 0, small_h - 1)
                    gx = np.clip(grid_X + dx, 0, small_w - 1)
                    py, px = cy[gy, gx], cx[gy, gx]
                    dist = (Y - py)**2 + (X - px)**2
                    mask = dist < min_dist
                    min_dist[mask] = dist[mask]
                    owner_y[mask] = py[mask]
                    owner_x[mask] = px[mask]
                    
            if self.mode == "crystallize":
                res_arr[..., :3] = self.orig_arr[owner_y, owner_x, :3]
            else:
                bg = getattr(self.parent()._canvas, "bg_color", QColor(255, 255, 255)) if hasattr(self.parent(), "_canvas") else QColor(255, 255, 255)
                bg_arr = np.array([bg.blue(), bg.green(), bg.red()], dtype=np.uint8)
                mask = np.expand_dims(min_dist < (s * 0.6)**2, -1)
                res_arr[..., :3] = np.where(mask, self.orig_arr[owner_y, owner_x, :3], bg_arr)
                
        elif self.mode == "fragment":
            Y, X = np.ogrid[:h, :w]
            y1, y2 = np.clip(Y - 4, 0, h - 1), np.clip(Y + 4, 0, h - 1)
            x1, x2 = np.clip(X - 4, 0, w - 1), np.clip(X + 4, 0, w - 1)
            res = self.orig_arr[y1, x1, :3].astype(np.uint16) + self.orig_arr[y1, x2, :3] + self.orig_arr[y2, x1, :3] + self.orig_arr[y2, x2, :3]
            res_arr[..., :3] = (res // 4).astype(np.uint8)
            
        elif self.mode == "facet":
            current = self.orig_arr[..., :3].copy()
            for _ in range(2):
                padded = np.pad(current, ((1,1),(1,1),(0,0)), mode='edge')
                stack = np.stack([padded[dy:h+dy, dx:w+dx] for dy in range(3) for dx in range(3)], axis=-1)
                current = np.median(stack, axis=-1).astype(np.uint8)
            res_arr[..., :3] = current
            
        elif self.mode == "color_halftone":
            s = max(4, self.amount_sl.value())
            R, G, B = self.orig_arr[..., 2].astype(np.float32)/255.0, self.orig_arr[..., 1].astype(np.float32)/255.0, self.orig_arr[..., 0].astype(np.float32)/255.0
            K = 1.0 - np.maximum(np.maximum(R, G), B)
            safe_K = np.where(K == 1.0, 1e-5, 1.0 - K)
            C, M, Y_c = (1.0 - R - K) / safe_K, (1.0 - G - K) / safe_K, (1.0 - B - K) / safe_K
            
            def hc(val, angle):
                a = np.radians(angle)
                Y, X = np.ogrid[:h, :w]
                Xr, Yr = X * np.cos(a) - Y * np.sin(a), X * np.sin(a) + Y * np.cos(a)
                return ((Xr - ((Xr // s) * s + s / 2.0))**2 + (Yr - ((Yr // s) * s + s / 2.0))**2 <= val * (s * 0.707)**2).astype(np.float32)
                
            d_C, d_M, d_Y, d_K = hc(C, 15), hc(M, 75), hc(Y_c, 0), hc(K, 45)
            res_arr[..., 2] = ((1.0 - np.clip(d_C + d_K, 0.0, 1.0)) * 255).astype(np.uint8)
            res_arr[..., 1] = ((1.0 - np.clip(d_M + d_K, 0.0, 1.0)) * 255).astype(np.uint8)
            res_arr[..., 0] = ((1.0 - np.clip(d_Y + d_K, 0.0, 1.0)) * 255).astype(np.uint8)
            
        elif self.mode == "mezzotint":
            mt = self.type_combo.currentData()
            np.random.seed(42)
            if "dots" in mt:
                if "fine" in mt: n = np.random.uniform(-0.5, 0.5, (h, w, 3))
                elif "medium" in mt: n = np.random.uniform(-0.5, 0.5, (h//2+1, w//2+1, 3)).repeat(2, axis=0).repeat(2, axis=1)[:h, :w]
                else: n = np.random.uniform(-0.5, 0.5, (h//3+1, w//3+1, 3)).repeat(3, axis=0).repeat(3, axis=1)[:h, :w]
            elif "lines" in mt:
                if "short" in mt: n = np.random.uniform(-0.5, 0.5, (h, w//3+1, 3)).repeat(3, axis=1)[:h, :w]
                elif "medium" in mt: n = np.random.uniform(-0.5, 0.5, (h, w//8+1, 3)).repeat(8, axis=1)[:h, :w]
                else: n = np.random.uniform(-0.5, 0.5, (h, w//16+1, 3)).repeat(16, axis=1)[:h, :w]
            elif "strokes" in mt:
                n0 = np.random.uniform(-0.5, 0.5, (h, w, 3))
                shift = 3 if "short" in mt else 8 if "medium" in mt else 15
                n = np.zeros_like(n0)
                for i in range(shift): n += np.roll(np.roll(n0, i, axis=0), i, axis=1)
                n /= shift
                
            res = (self.orig_arr[..., :3].astype(np.float32) / 255.0 + n * 1.5) > 0.5
            res_arr[..., :3] = (res * 255).astype(np.uint8)
            
        self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()