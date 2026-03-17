import numpy as np
import ctypes
import math
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QDialogButtonBox, QWidget)
from PyQt6.QtCore import Qt, QPointF, QRect, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QPixmap

from core.locale import tr
from ui.adjustments_dialog import _JumpSlider


def fast_box_blur_np(arr, radius):
    """Сверхбыстрый сепарабельный Box Blur на NumPy для предпросмотра."""
    r = int(radius)
    if r <= 0: return arr.copy()
    h, w, c = arr.shape
    
    # Ограничиваем радиус, чтобы не сломать память
    r = min(r, max(1, min(h, w) // 2))
    
    # Горизонтальный проход
    pad_h = np.pad(arr, ((0,0), (r, r), (0,0)), mode='edge').astype(np.int32)
    cs_h = np.cumsum(pad_h, axis=1)
    res_h = np.empty_like(arr, dtype=np.int32)
    res_h[:, 0, :] = cs_h[:, 2*r, :]
    if w > 1:
        res_h[:, 1:, :] = cs_h[:, 2*r+1:, :] - cs_h[:, :-2*r-1, :]
    res_h //= (2*r + 1)
    
    # Вертикальный проход
    pad_v = np.pad(res_h, ((r, r), (0,0), (0,0)), mode='edge')
    cs_v = np.cumsum(pad_v, axis=0)
    res_v = np.empty_like(res_h)
    res_v[0, :, :] = cs_v[2*r, :, :]
    if h > 1:
        res_v[1:, :, :] = cs_v[2*r+1:, :, :] - cs_v[:-2*r-1, :, :]
    res_v //= (2*r + 1)
    
    return res_v.astype(np.uint8)


class BlurGalleryCanvas(QWidget):
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
        if not self.dialog.preview_img:
            return
            
        w, h = self.dialog.preview_img.width(), self.dialog.preview_img.height()
        
        p.save()
        p.translate(self._pan)
        p.scale(self.zoom, self.zoom)
        
        # Шахматка
        tile = 16
        for y in range(0, h, tile):
            for x in range(0, w, tile):
                c = QColor(180,180,180) if (x//tile + y//tile) % 2 == 0 else QColor(220,220,220)
                p.fillRect(x, y, min(tile, w-x), min(tile, h-y), c)
                
        p.drawImage(0, 0, self.dialog.preview_img)
        
        # Отрисовка UI элементов (центр фокуса)
        cx, cy = self.dialog.cx, self.dialog.cy
        p.setPen(QPen(QColor(255, 255, 255, 200), max(1.0, 1.5/self.zoom)))
        p.setBrush(QColor(0, 0, 0, 100))
        cr = max(4.0, 6.0/self.zoom)
        p.drawEllipse(QPointF(cx, cy), cr, cr)
        p.drawEllipse(QPointF(cx, cy), cr*3, cr*3)
        
        mode = self.dialog.mode
        focus = self.dialog.focus_sl.value() / 100.0 * max(w, h) / 2.0
        trans = self.dialog.trans_sl.value() / 100.0 * max(w, h) / 2.0
        
        p.setPen(QPen(QColor(255, 255, 255, 100), max(1.0, 1.0/self.zoom), Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if mode == "iris":
            p.drawEllipse(QPointF(cx, cy), focus, focus)
            p.drawEllipse(QPointF(cx, cy), focus + trans, focus + trans)
        elif mode in ("tilt_shift", "path"):
            p.translate(cx, cy)
            p.rotate(-self.dialog.angle_sl.value())
            
            if mode == "tilt_shift":
                p.drawLine(QPointF(-w*2, -focus), QPointF(w*2, -focus))
                p.drawLine(QPointF(-w*2, focus), QPointF(w*2, focus))
                p.setPen(QPen(QColor(255, 255, 255, 50), max(1.0, 1.0/self.zoom), Qt.PenStyle.DotLine))
                p.drawLine(QPointF(-w*2, -(focus + trans)), QPointF(w*2, -(focus + trans)))
                p.drawLine(QPointF(-w*2, focus + trans), QPointF(w*2, focus + trans))
            else: # path
                p.drawLine(QPointF(-w*2, 0), QPointF(w*2, 0))
                
        p.restore()
        p.end()

    def mousePressEvent(self, ev):
        is_pan = ev.button() == Qt.MouseButton.MiddleButton or (self._space and ev.button() == Qt.MouseButton.LeftButton)
        if is_pan:
            self._panning = True
            self._pan_last = ev.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif ev.button() == Qt.MouseButton.LeftButton:
            # Проверка попадания в центр
            pos = ev.position()
            img_x = (pos.x() - self._pan.x()) / self.zoom
            img_y = (pos.y() - self._pan.y()) / self.zoom
            if math.hypot(img_x - self.dialog.cx, img_y - self.dialog.cy) < (20 / self.zoom):
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
        if self._space:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

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
        self.update()


class BlurGalleryDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("menu.blur_gallery") + f" - {mode.replace('_', ' ').title()}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.resize(1000, 700)
        
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        self.orig_img = layer.image.copy()
        self.preview_img = layer.image.copy()
        self.cx = self.orig_img.width() / 2.0
        self.cy = self.orig_img.height() / 2.0
        
        ptr = self.orig_img.constBits()
        buf = (ctypes.c_uint8 * self.orig_img.sizeInBytes()).from_address(int(ptr))
        self.orig_arr = np.ndarray((self.orig_img.height(), self.orig_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :self.orig_img.width(), :].copy()
        
        self.blurred_cache = None
        self.last_blur_radius = -1
        
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._apply_effect)

        self._build_ui()
        self._apply_effect()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)
        
        # Canvas
        self.canvas = BlurGalleryCanvas(self)
        
        # Initial Zoom fit
        w, h = self.orig_img.width(), self.orig_img.height()
        scale = min(700 / max(1, w), 600 / max(1, h))
        self.canvas.zoom = scale
        self.canvas._pan = QPointF(50, 50)
        
        root.addWidget(self.canvas, 1)
        
        # Controls Right Panel
        props = QWidget()
        props.setFixedWidth(280)
        props.setStyleSheet("background: #1e1e2e; border-left: 1px solid #313244;")
        pl = QVBoxLayout(props)
        pl.setContentsMargins(15, 15, 15, 15)
        pl.setSpacing(15)
        
        def add_slider(name, lo, hi, val):
            pl.addWidget(QLabel(name))
            sl = _JumpSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(val)
            sl.valueChanged.connect(self._trigger_update)
            pl.addWidget(sl)
            return sl
            
        self.blur_sl = add_slider("Размытие (Amount):", 0, 150, 15)
        
        self.focus_sl = add_slider("Зона резкости:", 0, 100, 20)
        self.trans_sl = add_slider("Плавность перехода:", 0, 100, 30)
        self.angle_sl = add_slider("Угол наклона:", -180, 180, 0)
        
        # Скрываем ненужные ползунки в зависимости от режима
        if self.mode == "field":
            for sl in (self.focus_sl, self.trans_sl, self.angle_sl):
                pl.itemAt(pl.indexOf(sl)).widget().hide()
                pl.itemAt(pl.indexOf(sl)-1).widget().hide()
        elif self.mode == "iris":
            self.angle_sl.hide()
            pl.itemAt(pl.indexOf(self.angle_sl)-1).widget().hide()
        elif self.mode in ("spin", "path"):
            self.focus_sl.hide(); self.trans_sl.hide()
            pl.itemAt(pl.indexOf(self.focus_sl)-1).widget().hide()
            pl.itemAt(pl.indexOf(self.trans_sl)-1).widget().hide()
            if self.mode == "spin":
                self.angle_sl.hide()
                pl.itemAt(pl.indexOf(self.angle_sl)-1).widget().hide()

        pl.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        pl.addWidget(btns)
        root.addWidget(props)

    def _trigger_update(self):
        self._timer.start()
        self.canvas.update()

    def _apply_effect(self):
        r = self.blur_sl.value()
        if r == 0:
            self.preview_img = self.orig_img.copy()
            self.canvas.update()
            return
            
        h, w = self.orig_arr.shape[:2]
        
        if self.mode in ("field", "iris", "tilt_shift"):
            # Кэшируем блюр для скорости
            if self.last_blur_radius != r or self.blurred_cache is None:
                # Двойной проход для мягкости (псевдо-гаусс)
                self.blurred_cache = fast_box_blur_np(fast_box_blur_np(self.orig_arr, r//2), r//2)
                self.last_blur_radius = r
                
            Y, X = np.ogrid[:h, :w]
            
            if self.mode == "field":
                mask = np.ones((h, w, 1), dtype=np.float32)
            else:
                max_dim = max(h, w)
                focus = (self.focus_sl.value() / 100.0) * (max_dim / 2.0)
                trans = max(1.0, (self.trans_sl.value() / 100.0) * (max_dim / 2.0))
                
                if self.mode == "iris":
                    dist = np.sqrt((X - self.cx)**2 + (Y - self.cy)**2)
                else: # tilt_shift
                    theta = np.radians(self.angle_sl.value())
                    dist = np.abs((X - self.cx) * np.sin(theta) + (Y - self.cy) * np.cos(theta))
                    
                m = (dist - focus) / trans
                mask = np.clip(m, 0.0, 1.0)[..., np.newaxis]
                mask = mask * mask * (3.0 - 2.0 * mask) # Smoothstep
                
            res_arr = (self.orig_arr.astype(np.float32) * (1.0 - mask) + self.blurred_cache.astype(np.float32) * mask).astype(np.uint8)
            
            # Обновляем картинку
            self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
            
        elif self.mode in ("path", "spin"):
            # Для motion/spin blur проще и быстрее использовать QPainter
            res_img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            res_img.fill(0)
            p = QPainter(res_img)
            steps = min(40, max(5, r)) # Адаптивное число шагов
            p.setOpacity(1.0 / steps)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.translate(self.cx, self.cy)
            
            theta = np.radians(self.angle_sl.value())
            
            for i in range(steps):
                p.save()
                if self.mode == "path":
                    offset = (i - steps/2) * (r / steps)
                    p.translate(np.cos(theta) * offset, np.sin(theta) * offset)
                elif self.mode == "spin":
                    a = (i - steps/2) * (r / steps) * 2.0 # Градусы
                    p.rotate(a)
                p.drawImage(QPointF(-self.cx, -self.cy), self.orig_img)
                p.restore()
            p.end()
            
            # Компенсация потери яркости и альфы из-за погрешностей 8-битного сложения QPainter
            step_alpha = int(round(255.0 / steps))
            if step_alpha > 0:
                max_possible = step_alpha * steps
                if max_possible < 255:
                    ptr = res_img.bits()
                    buf = (ctypes.c_uint8 * res_img.sizeInBytes()).from_address(int(ptr))
                    arr = np.ndarray((h, w, 4), dtype=np.uint8, buffer=buf)
                    ratio = 255.0 / max_possible
                    arr[...] = np.clip(arr.astype(np.float32) * ratio, 0, 255).astype(np.uint8)
                    
            self.preview_img = res_img
            
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()