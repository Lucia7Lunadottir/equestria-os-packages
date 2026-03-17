import numpy as np
import ctypes
import math
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QDialogButtonBox, QWidget)
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor, QPen

from core.locale import tr, current as locale_current
from ui.adjustments_dialog import _JumpSlider


class LiquifyCanvas(QWidget):
    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.setMouseTracking(True)
        self.zoom = 1.0
        self._pan = QPointF(0, 0)
        self._panning = False
        self._drawing = False
        self._pan_last = None
        self._last_mouse = None
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
        
        if self.dialog.mode == "liquify" and not self._space and self._last_mouse:
            r = (self.dialog.sl1.value() * self.zoom) / 2.0
            p.setPen(QPen(QColor(255, 255, 255, 180), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self._last_mouse, r, r)
            p.setPen(QPen(QColor(0, 0, 0, 150), 1))
            p.drawEllipse(self._last_mouse, r-1, r-1)
            
        p.end()

    def mousePressEvent(self, ev):
        is_pan = ev.button() == Qt.MouseButton.MiddleButton or (self._space and ev.button() == Qt.MouseButton.LeftButton)
        if is_pan:
            self._panning = True
            self._pan_last = ev.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif ev.button() == Qt.MouseButton.LeftButton and self.dialog.mode == "liquify":
            self.dialog.push_undo()
            self._drawing = True
            self._last_mouse = ev.position()

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        if self._panning and self._pan_last is not None:
            self._pan += (pos - self._pan_last)
            self._pan_last = pos
            self.update()
        elif self._drawing and self.dialog.mode == "liquify":
            if self._last_mouse:
                p1_x = (self._last_mouse.x() - self._pan.x()) / self.zoom
                p1_y = (self._last_mouse.y() - self._pan.y()) / self.zoom
                p2_x = (pos.x() - self._pan.x()) / self.zoom
                p2_y = (pos.y() - self._pan.y()) / self.zoom
                self.dialog.apply_warp(p1_x, p1_y, p2_x, p2_y)
            self._last_mouse = pos
            self.update()
        else:
            self._last_mouse = pos
            self.update()

    def mouseReleaseEvent(self, ev):
        self._panning = False
        self._drawing = False
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
        if ev.key() == Qt.Key.Key_Z and (ev.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.dialog.undo()
        elif ev.key() == Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def keyReleaseEvent(self, ev):
        if ev.key() == Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._space = False
            self.setCursor(Qt.CursorShape.ArrowCursor)


class SpecificFiltersDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        title = tr(f"menu.filter.{mode}").replace('…', '')
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.resize(1000, 700)
        
        self.orig_img = layer.image.copy()
        self.preview_img = layer.image.copy()
        
        ptr = self.orig_img.constBits()
        buf = (ctypes.c_uint8 * self.orig_img.sizeInBytes()).from_address(int(ptr))
        self.orig_arr = np.ndarray((self.orig_img.height(), self.orig_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :self.orig_img.width(), :].copy()
        
        h, w = self.orig_arr.shape[:2]
        if self.mode == "liquify":
            Y, X = np.ogrid[:h, :w]
            self.disp_x = np.broadcast_to(X, (h, w)).astype(np.float32).copy()
            self.disp_y = np.broadcast_to(Y, (h, w)).astype(np.float32).copy()
            self._undo_stack = []
            
            from PyQt6.QtGui import QShortcut, QKeySequence
            QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.undo)
            
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._apply_effect)

        self._build_ui()
        self._apply_effect()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        
        self.canvas = LiquifyCanvas(self)
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

        for wg in [self.sl1, self.lbl1, self.sl2, self.lbl2, self.sl3, self.lbl3, 
                   self.sl4, self.lbl4, self.sl5, self.lbl5, self.sl6, self.lbl6]:
            wg.hide()

        if self.mode == "camera_raw":
            self.lbl1.setText(tr("spec.temp"));      self.sl1.setRange(-100, 100); self.sl1.setValue(0)
            self.lbl2.setText(tr("spec.tint"));      self.sl2.setRange(-100, 100); self.sl2.setValue(0)
            self.lbl3.setText(tr("spec.exposure"));  self.sl3.setRange(-100, 100); self.sl3.setValue(0)
            self.lbl4.setText(tr("spec.contrast"));  self.sl4.setRange(-100, 100); self.sl4.setValue(0)
            self.lbl5.setText(tr("spec.highlights"));self.sl5.setRange(-100, 100); self.sl5.setValue(0)
            self.lbl6.setText(tr("spec.shadows"));   self.sl6.setRange(-100, 100); self.sl6.setValue(0)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2, self.sl3, self.lbl3,
                      self.sl4, self.lbl4, self.sl5, self.lbl5, self.sl6, self.lbl6]: w.show()
                      
        elif self.mode == "lens_correction":
            self.lbl1.setText(tr("spec.distortion"));self.sl1.setRange(-100, 100); self.sl1.setValue(0)
            self.lbl2.setText(tr("spec.vignette"));  self.sl2.setRange(-100, 100); self.sl2.setValue(0)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2]: w.show()
            
        elif self.mode == "liquify":
            self.lbl1.setText(tr("spec.liquify.size")); self.sl1.setRange(10, 800); self.sl1.setValue(100)
            self.lbl2.setText(tr("spec.liquify.press"));self.sl2.setRange(1, 100);  self.sl2.setValue(50)
            for w in [self.sl1, self.lbl1, self.sl2, self.lbl2]: w.show()

        pl.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        pl.addWidget(btns)
        root.addWidget(props)

    def _trigger_update(self):
        self._timer.start()
        
    def push_undo(self):
        if self.mode == "liquify":
            self._undo_stack.append((self.disp_x.copy(), self.disp_y.copy()))
            if len(self._undo_stack) > 30:
                self._undo_stack.pop(0)

    def undo(self):
        if self.mode == "liquify" and self._undo_stack:
            self.disp_x, self.disp_y = self._undo_stack.pop()
            self._trigger_update()

    def apply_warp(self, x1, y1, x2, y2):
        """Интерактивный Forward Warp (Деформация) для Пластики."""
        h, w = self.orig_arr.shape[:2]
        r = self.sl1.value() / 2.0
        strength = self.sl2.value() / 100.0
        
        dx, dy = x2 - x1, y2 - y1
        dist_move = math.hypot(dx, dy)
        if dist_move < 1: return
        
        # Ограничиваем ROI для скорости
        min_x = max(0, int(min(x1, x2) - r))
        max_x = min(w, int(max(x1, x2) + r + 1))
        min_y = max(0, int(min(y1, y2) - r))
        max_y = min(h, int(max(y1, y2) + r + 1))
        
        if min_x >= max_x or min_y >= max_y: return
        
        Y, X = np.ogrid[min_y:max_y, min_x:max_x]
        dist_sq = (X - x1)**2 + (Y - y1)**2
        
        # Кисть деформации (плавный спад)
        weight = np.clip(1.0 - (dist_sq / (r**2)), 0.0, 1.0)
        weight = weight * weight * strength
        
        # Смещаем карту координат В ОБРАТНУЮ СТОРОНУ (чтобы тянуть пиксели за мышкой)
        self.disp_x[min_y:max_y, min_x:max_x] -= dx * weight
        self.disp_y[min_y:max_y, min_x:max_x] -= dy * weight
        
        self._trigger_update()

    def _apply_effect(self):
        res_arr = self.orig_arr.copy()
        h, w = res_arr.shape[:2]
        
        if self.mode == "camera_raw":
            temp = self.sl1.value() / 100.0
            tint = self.sl2.value() / 100.0
            exposure = self.sl3.value() / 100.0
            contrast = self.sl4.value() / 100.0
            highlights = self.sl5.value() / 100.0
            shadows = self.sl6.value() / 100.0
            
            arr_f = self.orig_arr[..., :3].astype(np.float32)
            
            # Температура и Оттенок (Баланс белого)
            arr_f[..., 2] += temp * 40.0   # Red
            arr_f[..., 0] -= temp * 40.0   # Blue
            arr_f[..., 1] += tint * 40.0   # Green
            arr_f[..., 2] -= tint * 20.0   # Magenta compensation
            arr_f[..., 0] -= tint * 20.0
            
            # Экспозиция (Умножение)
            arr_f *= (2.0 ** exposure)
            
            # Контраст
            arr_f = (arr_f - 128.0) * math.tan((contrast + 1) * math.pi/4) + 128.0
            
            # Тени / Света
            luma = 0.299 * arr_f[..., 2] + 0.587 * arr_f[..., 1] + 0.114 * arr_f[..., 0]
            
            shadow_mask = np.clip(1.0 - (luma / 128.0), 0.0, 1.0)
            arr_f += shadow_mask[..., np.newaxis] * shadows * 100.0
            
            high_mask = np.clip((luma - 128.0) / 128.0, 0.0, 1.0)
            arr_f += high_mask[..., np.newaxis] * highlights * 100.0
            
            res_arr[..., :3] = np.clip(arr_f, 0, 255).astype(np.uint8)
            
        elif self.mode == "lens_correction":
            k = self.sl1.value() / 100.0 # Оптическое искажение
            vig = self.sl2.value() / 100.0
            
            Y, X = np.ogrid[:h, :w]
            cy, cx = h / 2.0, w / 2.0
            max_r = math.hypot(cx, cy)
            
            yn = (Y - cy) / max_r
            xn = (X - cx) / max_r
            r2 = xn**2 + yn**2
            
            factor = 1.0 + k * r2
            src_X = np.clip(cx + (X - cx) * factor, 0, w - 1).astype(int)
            src_Y = np.clip(cy + (Y - cy) * factor, 0, h - 1).astype(int)
            
            base = self.orig_arr[src_Y, src_X, :3].astype(np.float32)
            
            # Виньетка
            if vig != 0:
                v_mask = 1.0 - np.clip(r2 * abs(vig), 0.0, 1.0)
                if vig < 0: base *= v_mask[..., np.newaxis] # Darken
                else: base = 255 - (255 - base) * v_mask[..., np.newaxis] # Lighten
                
            res_arr[..., :3] = np.clip(base, 0, 255).astype(np.uint8)
            
        elif self.mode == "liquify":
            # Рендеринг по карте смещений
            src_X = np.clip(self.disp_x, 0, w - 1).astype(int)
            src_Y = np.clip(self.disp_y, 0, h - 1).astype(int)
            res_arr[..., :3] = self.orig_arr[src_Y, src_X, :3]
            
        self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()