import numpy as np
import ctypes
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QDialogButtonBox, QWidget)
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

def apply_kuwahara(arr, r):
    """Мощный математический фильтр Кувахары через интегральные изображения."""
    if r <= 0: return arr.copy()
    h, w = arr.shape[:2]
    pad_arr = np.pad(arr, ((r+1, r+1), (r+1, r+1), (0, 0)), mode='edge').astype(np.float32)
    
    # float64 защищает от переполнения на больших фото
    int_img = np.cumsum(np.cumsum(pad_arr, axis=0, dtype=np.float64), axis=1, dtype=np.float64)
    intensity = 0.299 * pad_arr[..., 2] + 0.587 * pad_arr[..., 1] + 0.114 * pad_arr[..., 0]
    int_i = np.cumsum(np.cumsum(intensity, axis=0, dtype=np.float64), axis=1, dtype=np.float64)
    int_i2 = np.cumsum(np.cumsum(intensity**2, axis=0, dtype=np.float64), axis=1, dtype=np.float64)
    
    def region_stats(dy1, dy2, dx1, dx2):
        y2 = np.arange(r+1, r+1+h) + dy2; y1m1 = np.arange(r+1, r+1+h) + dy1 - 1
        x2 = np.arange(r+1, r+1+w) + dx2; x1m1 = np.arange(r+1, r+1+w) + dx1 - 1
        Y2, X2 = np.ix_(y2, x2); Y1m1, X1m1 = np.ix_(y1m1, x1m1)
        Y2_X1m1 = np.ix_(y2, x1m1); Y1m1_X2 = np.ix_(y1m1, x2)
        area = (dy2 - dy1 + 1) * (dx2 - dx1 + 1)
        S = int_i[Y2, X2] - int_i[Y1m1_X2] - int_i[Y2_X1m1] + int_i[Y1m1, X1m1]
        S2 = int_i2[Y2, X2] - int_i2[Y1m1_X2] - int_i2[Y2_X1m1] + int_i2[Y1m1, X1m1]
        var = np.abs(S2 - (S**2)/area) / area
        C = int_img[Y2, X2] - int_img[Y1m1_X2] - int_img[Y2_X1m1] + int_img[Y1m1, X1m1]
        return var, C / area
        
    v1, m1 = region_stats(-r, 0, -r, 0)
    v2, m2 = region_stats(-r, 0, 0, r)
    v3, m3 = region_stats(0, r, -r, 0)
    v4, m4 = region_stats(0, r, 0, r)
    
    vars_stack = np.stack([v1, v2, v3, v4], axis=-1)
    means_stack = np.stack([m1, m2, m3, m4], axis=3)
    min_idx = np.argmin(vars_stack, axis=-1)
    Y, X = np.ogrid[:h, :w]
    res = np.empty((h, w, 3), dtype=np.float32)
    for c in range(3): res[..., c] = means_stack[Y, X, c, min_idx]
    return res

class StylizeCanvas(QWidget):
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


class StylizeDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        title = tr(f"menu.stylize.{mode}").replace('…', '')
        self.setWindowTitle(f"{tr('menu.stylize')} - {title}")
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
        
        self.canvas = StylizeCanvas(self)
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
            
        self.sl1, self.lbl1 = add_slider("Param1")
        self.sl2, self.lbl2 = add_slider("Param2")
        self.sl3, self.lbl3 = add_slider("Param3")
        self.sl4, self.lbl4 = add_slider("Param4")
        self.sl5, self.lbl5 = add_slider("Param5")
        self.sl6, self.lbl6 = add_slider("Param6")
        
        self.cb1_lbl = QLabel("Combo1")
        self.cb1 = QComboBox(); self.cb1.currentIndexChanged.connect(self._trigger_update)
        pl.addWidget(self.cb1_lbl); pl.addWidget(self.cb1)
        
        self.cb2_lbl = QLabel("Combo2")
        self.cb2 = QComboBox(); self.cb2.currentIndexChanged.connect(self._trigger_update)
        pl.addWidget(self.cb2_lbl); pl.addWidget(self.cb2)

        for wg in [self.sl1, self.lbl1, self.sl2, self.lbl2, self.sl3, self.lbl3, 
                   self.sl4, self.lbl4, self.sl5, self.lbl5, self.sl6, self.lbl6,
                   self.cb1, self.cb1_lbl, self.cb2, self.cb2_lbl]:
            wg.hide()

        if self.mode == "emboss":
            self.lbl1.setText(tr("stylize.angle")); self.sl1.setRange(-180, 180); self.sl1.setValue(135)
            self.lbl2.setText(tr("stylize.height")); self.sl2.setRange(1, 10); self.sl2.setValue(3)
            self.lbl3.setText(tr("stylize.amount")); self.sl3.setRange(1, 500); self.sl3.setValue(100)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2, self.sl3, self.lbl3]: w.show()
        elif self.mode == "extrude":
            self.lbl1.setText(tr("stylize.size")); self.sl1.setRange(2, 255); self.sl1.setValue(30)
            self.lbl2.setText(tr("stylize.depth")); self.sl2.setRange(1, 255); self.sl2.setValue(30)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2]: w.show()
        elif self.mode == "find_edges":
            from core.locale import current as locale_current
            msg = "Этот фильтр не имеет\nнастраиваемых параметров." if locale_current() == "ru" else "This filter has no\nadjustable parameters."
            no_param_lbl = QLabel(msg)
            no_param_lbl.setStyleSheet("color: #a6adc8; font-size: 12px; font-style: italic;")
            pl.addWidget(no_param_lbl)
        elif self.mode == "oil_paint":
            self.lbl1.setText(tr("stylize.stylization")); self.sl1.setRange(1, 10); self.sl1.setValue(5)
            self.lbl2.setText(tr("stylize.cleanliness")); self.sl2.setRange(0, 10); self.sl2.setValue(3)
            self.lbl3.setText(tr("stylize.scale"));       self.sl3.setRange(1, 10); self.sl3.setValue(5)
            self.lbl4.setText(tr("stylize.bristle"));     self.sl4.setRange(0, 10); self.sl4.setValue(5)
            self.lbl5.setText(tr("stylize.angle"));       self.sl5.setRange(-180, 180); self.sl5.setValue(90)
            self.lbl6.setText(tr("stylize.shine"));       self.sl6.setRange(0, 100); self.sl6.setValue(25)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2, self.sl3, self.lbl3,
                      self.sl4, self.lbl4, self.sl5, self.lbl5, self.sl6, self.lbl6]: w.show()
        elif self.mode == "solarize":
            self.lbl1.setText(tr("adj.threshold.threshold")); self.sl1.setRange(0, 255); self.sl1.setValue(128)
            for w in [self.sl1, self.lbl1]: w.show()
        elif self.mode == "tiles":
            self.lbl1.setText(tr("stylize.tiles_num")); self.sl1.setRange(10, 99); self.sl1.setValue(10)
            self.lbl2.setText(tr("stylize.offset")); self.sl2.setRange(1, 90); self.sl2.setValue(10)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2]: w.show()
        elif self.mode == "trace_contour":
            self.lbl1.setText(tr("stylize.level")); self.sl1.setRange(0, 255); self.sl1.setValue(128)
            self.cb1_lbl.setText(tr("stylize.edge")); self.cb1.addItems([tr("stylize.lower"), tr("stylize.upper")])
            for w in [self.sl1, self.lbl1, self.cb1, self.cb1_lbl]: w.show()
        elif self.mode == "wind":
            self.cb1_lbl.setText(tr("stylize.method")); self.cb1.addItems([tr("stylize.wind.wind"), tr("stylize.wind.blast"), tr("stylize.wind.stagger")])
            self.cb2_lbl.setText(tr("stylize.direction")); self.cb2.addItems([tr("stylize.right"), tr("stylize.left")])
            for w in [self.cb1, self.cb1_lbl, self.cb2, self.cb2_lbl]: w.show()

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
        
        if self.mode == "emboss":
            angle, height, amount = self.sl1.value(), self.sl2.value(), self.sl3.value()
            a = np.radians(angle)
            dx, dy = int(np.round(np.cos(a) * height)), int(np.round(np.sin(a) * height))
            
            arr_f = self.orig_arr[..., :3].astype(np.float32)
            gray = 0.299 * arr_f[..., 2] + 0.587 * arr_f[..., 1] + 0.114 * arr_f[..., 0]
            
            shifted = np.roll(np.roll(gray, -dy, axis=0), -dx, axis=1)
            if dy > 0: shifted[-dy:, :] = gray[-dy:, :]
            elif dy < 0: shifted[:-dy, :] = gray[:-dy, :]
            if dx > 0: shifted[:, -dx:] = gray[:, -dx:]
            elif dx < 0: shifted[:, :-dx] = gray[:, :-dx]
            
            grad = shifted - gray
            res = 128 + grad * (amount / 100.0)
            res_arr[..., 0] = res_arr[..., 1] = res_arr[..., 2] = np.clip(res, 0, 255).astype(np.uint8)
            
        elif self.mode == "extrude":
            size, depth = self.sl1.value(), self.sl2.value()
            Y, X = np.ogrid[:h, :w]
            grid_Y, grid_X = Y // size, X // size
            
            np.random.seed(42)
            depths = np.random.randint(1, depth + 1, (h // size + 1, w // size + 1))
            block_depths = depths[grid_Y, grid_X]
            
            cy = np.clip(grid_Y * size + size // 2, 0, h - 1)
            cx = np.clip(grid_X * size + size // 2, 0, w - 1)
            block_colors = self.orig_arr[cy, cx, :3]
            
            inner_y, inner_x = Y % size, X % size
            shade = np.ones((h, w, 3), dtype=np.float32)
            border_size = np.clip(block_depths // 2, 1, size // 2)
            
            shade[inner_y < border_size] = 1.3
            shade[inner_x < border_size] = 1.1
            shade[inner_y > (size - border_size)] = 0.7
            shade[inner_x > (size - border_size)] = 0.5
            
            res_arr[..., :3] = np.clip(block_colors * shade, 0, 255).astype(np.uint8)
            
        elif self.mode == "find_edges":
            arr_f = self.orig_arr[..., :3].astype(np.int16)
            gx = np.abs(np.roll(arr_f, -1, axis=1) - np.roll(arr_f, 1, axis=1))
            gy = np.abs(np.roll(arr_f, -1, axis=0) - np.roll(arr_f, 1, axis=0))
            res_arr[..., :3] = 255 - np.clip(gx + gy, 0, 255).astype(np.uint8)
            
        elif self.mode == "oil_paint":
            stylization = self.sl1.value()
            cleanliness = self.sl2.value()
            scale = self.sl3.value()
            bristle = self.sl4.value()
            angle = self.sl5.value()
            shine = self.sl6.value()
            
            base = self.orig_arr[..., :3].copy()
            if cleanliness > 0: base = fast_box_blur_np(base, cleanliness)
                
            base = base.astype(np.float32)
            if stylization > 0:
                base = apply_kuwahara(base, stylization)
                if cleanliness > 5:
                    base = apply_kuwahara(base, stylization // 2)
                    
            if shine > 0:
                gray = 0.299 * base[..., 2] + 0.587 * base[..., 1] + 0.114 * base[..., 0]
                smooth_radius = 10 - bristle
                if smooth_radius > 0:
                    gray_3d = np.repeat(gray[..., np.newaxis], 3, axis=2).astype(np.uint8)
                    gray = fast_box_blur_np(gray_3d, smooth_radius)[..., 0].astype(np.float32)
                    
                a = np.radians(angle)
                dx, dy = int(np.round(np.cos(a) * scale)), int(np.round(np.sin(a) * scale))
                if dx == 0 and dy == 0: dx = 1
                
                shifted = np.roll(np.roll(gray, -dy, axis=0), -dx, axis=1)
                if dy > 0: shifted[-dy:, :] = gray[-dy:, :]
                elif dy < 0: shifted[:-dy, :] = gray[:-dy, :]
                if dx > 0: shifted[:, -dx:] = gray[:, -dx:]
                elif dx < 0: shifted[:, :-dx] = gray[:, :-dx]
                
                bump = (gray - shifted) * (shine / 100.0) * 1.5
                base = np.clip(base + bump[..., np.newaxis], 0, 255)
                
            res_arr[..., :3] = base.astype(np.uint8)
            
        elif self.mode == "solarize":
            arr_c = self.orig_arr[..., :3]
            res_arr[..., :3] = np.where(arr_c > self.sl1.value(), 255 - arr_c, arr_c)
            
        elif self.mode == "tiles":
            size = max(2, w // self.sl1.value())
            offset_pct = self.sl2.value()
            Y, X = np.ogrid[:h, :w]
            grid_Y, grid_X = Y // size, X // size
            
            np.random.seed(42)
            shift_y = np.random.randint(-size * offset_pct // 100, size * offset_pct // 100 + 1, (h // size + 1, w // size + 1))
            shift_x = np.random.randint(-size * offset_pct // 100, size * offset_pct // 100 + 1, (h // size + 1, w // size + 1))
            
            src_Y = np.clip(Y + shift_y[grid_Y, grid_X], 0, h - 1)
            src_X = np.clip(X + shift_x[grid_Y, grid_X], 0, w - 1)
            
            gap = max(1, size // 10)
            is_gap = ((Y % size) < gap) | ((X % size) < gap)
            
            bg = getattr(self.parent()._canvas, "bg_color", QColor(255, 255, 255)) if hasattr(self.parent(), "_canvas") else QColor(255, 255, 255)
            bg_arr = np.array([bg.blue(), bg.green(), bg.red()], dtype=np.uint8)
            res_arr[..., :3] = np.where(is_gap[..., np.newaxis], bg_arr, self.orig_arr[src_Y, src_X, :3])
            
        elif self.mode == "trace_contour":
            arr_c = self.orig_arr[..., :3]
            mask = arr_c <= self.sl1.value() if self.cb1.currentIndex() == 0 else arr_c >= self.sl1.value()
            edges = (mask ^ np.roll(mask, 1, axis=0)) | (mask ^ np.roll(mask, 1, axis=1))
            res_arr[..., :3] = np.where(edges, arr_c, 255)
            
        elif self.mode == "wind":
            method, direction = self.cb1.currentIndex(), self.cb2.currentIndex()
            f_arr = self.orig_arr[..., :3].copy()
            np.random.seed(42)
            
            prob = 0.05 if method == 0 else 0.15 if method == 1 else 0.1
            length = 20 if method == 0 else 40 if method == 1 else 10
            
            for i in range(1, length):
                mask = (np.random.rand(h, w, 1) < prob)
                if direction == 0:
                    shifted = np.roll(f_arr, i, axis=1); shifted[:, :i] = f_arr[:, :i]
                else:
                    shifted = np.roll(f_arr, -i, axis=1); shifted[:, -i:] = f_arr[:, -i:]
                f_arr = np.where(mask, shifted, f_arr)
                
            res_arr[..., :3] = f_arr
            
        self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()