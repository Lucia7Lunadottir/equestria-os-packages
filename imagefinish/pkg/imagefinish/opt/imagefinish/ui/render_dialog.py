import numpy as np
import ctypes
import math
import random
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QDialogButtonBox, QWidget)
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QRadialGradient, QBrush, QPainterPath

from core.locale import tr, current as locale_current
from ui.adjustments_dialog import _JumpSlider
from core.adjustments._widgets import _ColorButton

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


def _generate_noise_image(w, h, octaves=6, seed=None, scale_x=None, scale_y=None):
    """Настоящий градиентный шум (Perlin Noise) через NumPy для идеальных облаков."""
    if seed is not None: np.random.seed(seed)
    res = np.zeros((h, w), dtype=np.float32)
    base_sx = scale_x if scale_x else max(w, h) / 3.0
    base_sy = scale_y if scale_y else max(w, h) / 3.0
    amp = 1.0
    
    y_coords, x_coords = np.mgrid[0:h:1, 0:w:1]
    
    for i in range(octaves):
        sx = max(1.0, base_sx)
        sy = max(1.0, base_sy)
        
        x = x_coords / sx
        y = y_coords / sy
        
        x0 = x.astype(int)
        y0 = y.astype(int)
        x1 = x0 + 1
        y1 = y0 + 1
        
        angles = np.random.rand(y1.max()+1, x1.max()+1) * 2 * np.pi
        gx = np.cos(angles)
        gy = np.sin(angles)
        
        g00 = gx[y0, x0] * (x - x0) + gy[y0, x0] * (y - y0)
        g10 = gx[y0, x1] * (x - x1) + gy[y0, x1] * (y - y0)
        g01 = gx[y1, x0] * (x - x0) + gy[y1, x0] * (y - y1)
        g11 = gx[y1, x1] * (x - x1) + gy[y1, x1] * (y - y1)
        
        dx = x - x0
        dy = y - y0
        u = dx * dx * (3.0 - 2.0 * dx)
        v = dy * dy * (3.0 - 2.0 * dy)
        
        nx0 = g00 * (1 - u) + g10 * u
        nx1 = g01 * (1 - u) + g11 * u
        n = nx0 * (1 - v) + nx1 * v
        
        res += n * amp
        amp *= 0.5
        base_sx *= 0.5
        base_sy *= 0.5
        
    return (res - res.min()) / (res.max() - res.min() + 1e-5)


class RenderCanvas(QWidget):
    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.setMouseTracking(True)
        self.zoom = 1.0
        self._pan = QPointF(0, 0)
        self._panning = False
        self._dragging_center = False
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
        
        if self.dialog.mode in ("lens_flare", "lighting"):
            cx, cy = self.dialog.cx, self.dialog.cy
            p.setPen(QPen(QColor(255, 255, 255, 200), max(1.0, 1.5/self.zoom)))
            p.setBrush(QColor(0, 0, 0, 100))
            cr = max(4.0, 6.0/self.zoom)
            p.drawEllipse(QPointF(cx, cy), cr, cr)
            p.drawLine(QPointF(cx - cr*2, cy), QPointF(cx + cr*2, cy))
            p.drawLine(QPointF(cx, cy - cr*2), QPointF(cx, cy + cr*2))
            
        p.restore()
        p.end()

    def mousePressEvent(self, ev):
        is_pan = ev.button() == Qt.MouseButton.MiddleButton or (self._space and ev.button() == Qt.MouseButton.LeftButton)
        if is_pan:
            self._panning = True
            self._pan_last = ev.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif ev.button() == Qt.MouseButton.LeftButton and self.dialog.mode in ("lens_flare", "lighting"):
            pos = ev.position()
            img_x = (pos.x() - self._pan.x()) / self.zoom
            img_y = (pos.y() - self._pan.y()) / self.zoom
            if math.hypot(img_x - self.dialog.cx, img_y - self.dialog.cy) < (40 / self.zoom):
                self._dragging_center = True

    def mouseMoveEvent(self, ev):
        if self._panning and self._pan_last is not None:
            self._pan += (ev.position() - self._pan_last)
            self._pan_last = ev.position()
            self.update()
        elif self._dragging_center:
            pos = ev.position()
            self.dialog.cx = (pos.x() - self._pan.x()) / self.zoom
            self.dialog.cy = (pos.y() - self._pan.y()) / self.zoom
            self.update()
            self.dialog._trigger_update()

    def mouseReleaseEvent(self, ev):
        self._panning = False
        self._dragging_center = False
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


class RenderDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        title = tr(f"menu.render.{mode}").replace('…', '')
        self.setWindowTitle(f"{tr('menu.render_gallery')} - {title}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.resize(1000, 700)
        
        self.orig_img = layer.image.copy()
        self.preview_img = layer.image.copy()
        self.cx = self.orig_img.width() / 2.0
        self.cy = self.orig_img.height() / 2.0
        
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
        
        self.canvas = RenderCanvas(self)
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
        
        self.color_lbl = QLabel(tr("render.color"))
        self.color_btn = _ColorButton(QColor(255, 255, 255))
        self.color_btn.colorChanged.connect(self._trigger_update)
        pl.addWidget(self.color_lbl)
        pl.addWidget(self.color_btn)
        
        self.cb1_lbl = QLabel("Combo1")
        self.cb1 = QComboBox(); self.cb1.currentIndexChanged.connect(self._trigger_update)
        pl.addWidget(self.cb1_lbl); pl.addWidget(self.cb1)
        
        for wg in [self.sl1, self.lbl1, self.sl2, self.lbl2, self.sl3, self.lbl3, 
                   self.sl4, self.lbl4, self.sl5, self.lbl5, 
                   self.cb1, self.cb1_lbl, self.color_lbl, self.color_btn]: wg.hide()

        if self.mode == "fibers":
            self.lbl1.setText(tr("render.variance")); self.sl1.setRange(1, 64); self.sl1.setValue(16)
            self.lbl2.setText(tr("render.strength")); self.sl2.setRange(1, 64); self.sl2.setValue(4)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2]: w.show()
        elif self.mode == "lens_flare":
            self.lbl1.setText(tr("render.brightness")); self.sl1.setRange(10, 300); self.sl1.setValue(100)
            self.cb1_lbl.setText(tr("render.lens_type"))
            self.cb1.addItems([tr("render.lens.50_300"), tr("render.lens.35"), tr("render.lens.105")])
            for w in [self.sl1, self.lbl1, self.cb1, self.cb1_lbl, self.color_lbl, self.color_btn]: w.show()
        elif self.mode == "lighting":
            self.lbl1.setText(tr("render.intensity")); self.sl1.setRange(0, 100); self.sl1.setValue(50)
            self.lbl2.setText(tr("render.focus")); self.sl2.setRange(0, 100); self.sl2.setValue(50)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2]: w.show()
        elif self.mode == "wood":
            self.lbl1.setText(tr("render.rings")); self.sl1.setRange(1, 100); self.sl1.setValue(15)
            self.lbl2.setText(tr("render.turbulence")); self.sl2.setRange(0, 100); self.sl2.setValue(30)
            self.cb1_lbl.setText(tr("render.wood_type")); self.cb1.clear()
            self.cb1.addItems([tr("render.wood.rings"), tr("render.wood.bark")])
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2, self.cb1, self.cb1_lbl]: w.show()
        elif self.mode == "flame":
            self.lbl1.setText(tr("render.width")); self.sl1.setRange(1, 200); self.sl1.setValue(50)
            self.lbl2.setText(tr("render.length")); self.sl2.setRange(10, 500); self.sl2.setValue(100)
            self.lbl3.setText(tr("render.turbulence")); self.sl3.setRange(0, 100); self.sl3.setValue(30)
            self.lbl4.setText(tr("render.complexity")); self.sl4.setRange(1, 20); self.sl4.setValue(5)
            self.lbl5.setText(tr("render.core")); self.sl5.setRange(1, 100); self.sl5.setValue(80)
            
            self.cb1_lbl.setText(tr("render.flame_type")); self.cb1.clear()
            self.cb1.addItems([tr("render.flame.single"), tr("render.flame.multiple"), tr("render.flame.candle")])
            
            self.color_btn.set_color(QColor(255, 100, 0))
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2, self.sl3, self.lbl3, self.sl4, self.lbl4, self.sl5, self.lbl5, self.cb1, self.cb1_lbl, self.color_lbl, self.color_btn]: w.show()
        elif self.mode == "frame":
            self.lbl1.setText(tr("render.margin")); self.sl1.setRange(1, 100); self.sl1.setValue(20)
            self.lbl2.setText(tr("render.size")); self.sl2.setRange(1, 50); self.sl2.setValue(10)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2]: w.show()
        elif self.mode in ("clouds", "diff_clouds"):
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
        h, w = res_arr.shape[:2]
        fg = getattr(self.parent()._canvas, "fg_color", QColor(0, 0, 0)) if hasattr(self.parent(), "_canvas") else QColor(0, 0, 0)
        bg = getattr(self.parent()._canvas, "bg_color", QColor(255, 255, 255)) if hasattr(self.parent(), "_canvas") else QColor(255, 255, 255)
        
        if self.mode in ("clouds", "diff_clouds"):
            noise = _generate_noise_image(w, h, octaves=7)
            noise_f = noise.astype(np.float32)
            
            fc = np.array([fg.blue(), fg.green(), fg.red()], dtype=np.float32)
            bc = np.array([bg.blue(), bg.green(), bg.red()], dtype=np.float32)
            
            color_noise = bc + (fc - bc) * noise_f[..., np.newaxis]
            
            if self.mode == "diff_clouds":
                res_arr[..., :3] = np.abs(self.orig_arr[..., :3].astype(np.float32) - color_noise).astype(np.uint8)
            else:
                res_arr[..., :3] = color_noise.astype(np.uint8)
            res_arr[..., 3] = 255 # Делаем слой непрозрачным, если он был пустым
                
        elif self.mode == "fibers":
            var, strength = self.sl1.value(), self.sl2.value()
            noise_f = _generate_noise_image(w, h, octaves=5, scale_x=w/10.0, scale_y=h/(strength*5.0))
            noise_f = np.clip((noise_f - 0.5) * (var / 16.0) + 0.5, 0, 1)
            
            fc = np.array([fg.blue(), fg.green(), fg.red()], dtype=np.float32)
            bc = np.array([bg.blue(), bg.green(), bg.red()], dtype=np.float32)
            color_fibers = bc + (fc - bc) * noise_f[..., np.newaxis]
            res_arr[..., :3] = color_fibers.astype(np.uint8)
            res_arr[..., 3] = 255
            
        elif self.mode == "wood":
            rings = self.sl1.value()
            turb = self.sl2.value() / 100.0
            wood_type = self.cb1.currentIndex()
            
            Y, X = np.ogrid[:h, :w]
            
            if wood_type == 0: # Rings
                noise_f = _generate_noise_image(w, h, octaves=5).astype(np.float32)
                dx = X - w/2 + (noise_f - 0.5) * turb * w
                dy = Y - h/2 + (noise_f - 0.5) * turb * h
                r = np.hypot(dx, dy)
                
                ring_val = (np.sin(r * rings / max(w, h) * 2 * np.pi) + 1) / 2.0
                grain = (np.sin((r + (noise_f - 0.5) * turb * w * 0.5) * rings * 10 / max(w, h) * 2 * np.pi) + 1) / 2.0
                val = ring_val * 0.6 + grain * 0.2 + noise_f * 0.2
                
                c1 = np.array([30, 60, 100]) # Dark
                c2 = np.array([80, 140, 200]) # Light
                res_arr[..., :3] = (c1 + (c2 - c1) * val[..., np.newaxis]).astype(np.uint8)
            else: # Bark (Кора)
                n_base = _generate_noise_image(w, h, octaves=6, scale_x=max(10, w/rings), scale_y=max(50, h/2.0)).astype(np.float32)
                distort = _generate_noise_image(w, h, octaves=4, scale_x=50, scale_y=50).astype(np.float32)
                X_dist = np.clip(X + (distort - 0.5) * turb * 100, 0, w - 1).astype(int)
                
                ridges = np.abs(n_base[Y, X_dist] - 0.5) * 2.0
                val = np.power(ridges, 0.5 + turb) # Глубокие трещины
                
                c1 = np.array([15, 25, 40]) # Deep cracks
                c2 = np.array([50, 80, 110]) # Surface
                res_arr[..., :3] = (c1 + (c2 - c1) * val[..., np.newaxis]).astype(np.uint8)
                
            res_arr[..., 3] = 255
            
        elif self.mode in ("lens_flare", "lighting", "frame", "flame"):
            # Эффекты на базе QPainter
            img = QImage(self.orig_img)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            if self.mode == "lens_flare":
                b = self.sl1.value() / 100.0
                color = self.color_btn.color()
                l_type = self.cb1.currentIndex()
                
                # Main glow
                r1 = w * 0.4 * b
                grad = QRadialGradient(self.cx, self.cy, r1)
                grad.setColorAt(0, QColor(color.red(), color.green(), color.blue(), int(255 * min(1, b))))
                grad.setColorAt(0.1, QColor(color.red(), color.green(), color.blue(), int(150 * min(1, b))))
                grad.setColorAt(1, QColor(0, 0, 0, 0))
                
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
                p.fillRect(0, 0, w, h, QBrush(grad))
                
                # Artifacts
                dx, dy = self.cx - w/2, self.cy - h/2
                colors = [QColor(color.red(), 100, 100, 100), QColor(100, color.green(), 100, 80), QColor(100, 100, color.blue(), 120)]
                for i, mult in enumerate([-0.2, -0.5, -1.2, -1.5, 0.8]):
                    ax, ay = w/2 + dx*mult, h/2 + dy*mult
                    ar = r1 * 0.1 * abs(mult)
                    p.setBrush(QBrush(colors[i % len(colors)]))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawEllipse(QPointF(ax, ay), ar, ar)
                    
            elif self.mode == "lighting":
                intensity = self.sl1.value() / 50.0
                focus = self.sl2.value() / 100.0
                r = max(w, h) * (0.2 + focus * 0.8)
                grad = QRadialGradient(self.cx, self.cy, r)
                grad.setColorAt(0, QColor(255, 255, 255, int(255 * min(1, intensity))))
                grad.setColorAt(1, QColor(0, 0, 0, 0))
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
                p.fillRect(0, 0, w, h, QBrush(grad))
                
            elif self.mode == "frame":
                m = self.sl1.value()
                s = self.sl2.value()
                p.setPen(QPen(fg, s))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(m, m, w - m*2, h - m*2)
                
            elif self.mode == "flame":
                width = self.sl1.value()
                lines_count = self.sl2.value()
                turb = self.sl3.value() / 100.0
                complexity = self.sl4.value()
                core = self.sl5.value() / 100.0
                color = self.color_btn.color()
                f_type = self.cb1.currentIndex()
                
                # Достаём контур, который ты могла нарисовать Пером (Pen Tool)
                doc = self.parent()._document if hasattr(self.parent(), "_document") else None
                wp = getattr(doc, "work_path", {}) if doc else {}
                nodes = wp.get("nodes", [])
                
                base_path = QPainterPath()
                is_closed = wp.get("closed", False)
                try:
                    if nodes:
                        if isinstance(nodes[0], dict) and 'p' in nodes[0]:
                            base_path.moveTo(nodes[0]['p'])
                            for i in range(1, len(nodes)):
                                n0, n1 = nodes[i-1], nodes[i]
                                base_path.cubicTo(n0['c2'], n1['c1'], n1['p'])
                            if is_closed and len(nodes) > 1:
                                base_path.cubicTo(nodes[-1]['c2'], nodes[0]['c1'], nodes[0]['p'])
                        elif hasattr(nodes[0], 'x'):
                            base_path.moveTo(nodes[0])
                            for i in range(1, len(nodes)):
                                base_path.lineTo(nodes[i])
                    else:
                        base_path.moveTo(w/2, h * 0.9)
                        base_path.lineTo(w/2, h * 0.1)
                except Exception as e:
                    print("Flame path parsing error:", e)
                    base_path = QPainterPath()
                    base_path.moveTo(w/2, h * 0.9)
                    base_path.lineTo(w/2, h * 0.1)
                    
                # Огонь рисуется на отдельном прозрачном слое для правильного наложения альфы
                fire_img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                fire_img.fill(0)
                fp = QPainter(fire_img)
                fp.setRenderHint(QPainter.RenderHint.Antialiasing)
                fp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

                c = QColor(color)
                
                random.seed(42)
                
                path_len = base_path.length()
                if path_len < 10: path_len = max(100.0, h * 0.8)
                
                base_opacity = min(1.0, 10.0 / max(1, lines_count))
                c_pen = QColor(c.red(), c.green(), c.blue(), int(255 * base_opacity))
                c_core_pen = QColor(255, 255, 255, int(255 * base_opacity * core))
                
                for i in range(lines_count):
                    flame_path = QPainterPath()
                    phase = random.uniform(0, 100)
                    freq = random.uniform(2.0, 5.0) * complexity
                    
                    if f_type == 0:
                        t_start = 0.0
                        t_end = random.uniform(0.3, 1.0)
                        x_offset = random.uniform(-width, width)
                    elif f_type == 1:
                        t_start = random.uniform(0.0, 0.8)
                        t_end = t_start + random.uniform(0.1, 0.5)
                        x_offset = random.uniform(-width, width)
                    else:
                        t_start = 0.0
                        t_end = random.uniform(0.5, 1.0)
                        x_offset = random.uniform(-width*0.2, width*0.2)
                        
                    if t_end > 1.0: t_end = 1.0
                    
                    steps = max(10, int(path_len * (t_end - t_start) / 5))
                    
                    for s in range(steps + 1):
                        norm_s = s / steps if steps > 0 else 0
                        t = t_start + norm_s * (t_end - t_start)
                        
                        pt = base_path.pointAtPercent(t)
                        angle = base_path.angleAtPercent(t)
                        rad = math.radians(angle)
                        nx = -math.sin(rad)
                        ny = math.cos(rad)
                        
                        envelope = 1.0 - norm_s**2
                        if f_type == 2:
                            envelope = math.sin(norm_s * math.pi) * (1.0 - norm_s) + 0.1
                            
                        wiggle = math.sin(norm_s * freq + phase) * turb * width * norm_s
                        
                        offset_pt = QPointF(
                            pt.x() + nx * (x_offset * envelope + wiggle),
                            pt.y() + ny * (x_offset * envelope + wiggle)
                        )
                        
                        if s == 0: flame_path.moveTo(offset_pt)
                        else: flame_path.lineTo(offset_pt)
                        
                    pen_width = max(1.0, random.uniform(width * 0.1, width * 0.4))
                    fp.setPen(QPen(c_pen, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                    fp.drawPath(flame_path)
                    fp.setPen(QPen(c_core_pen, pen_width * 0.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                    fp.drawPath(flame_path)
                    
                fp.end()
                
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                p.drawImage(0, 0, fire_img)
                
            p.end()
            ptr = img.constBits()
            buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
            res_arr = np.ndarray((h, img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :w, :].copy()
            
        self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()