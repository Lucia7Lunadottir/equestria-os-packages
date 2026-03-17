import numpy as np
import ctypes
import math
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QDialogButtonBox, QWidget, QFileDialog)
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QBrush

from core.locale import tr
from ui.adjustments_dialog import _JumpSlider


class DistortCanvas(QWidget):
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
        
        if self.dialog.mode in ("twirl", "pinch", "spherize", "zigzag"):
            cx, cy = self.dialog.cx, self.dialog.cy
            p.setPen(QPen(QColor(255, 255, 255, 200), max(1.0, 1.5/self.zoom)))
            p.setBrush(QColor(0, 0, 0, 100))
            cr = max(4.0, 6.0/self.zoom)
            p.drawEllipse(QPointF(cx, cy), cr, cr)
            p.drawEllipse(QPointF(cx, cy), cr*3, cr*3)
                
        p.restore()
        p.end()

    def mousePressEvent(self, ev):
        is_pan = ev.button() == Qt.MouseButton.MiddleButton or (self._space and ev.button() == Qt.MouseButton.LeftButton)
        if is_pan:
            self._panning = True
            self._pan_last = ev.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif ev.button() == Qt.MouseButton.LeftButton and self.dialog.mode in ("twirl", "pinch", "spherize", "zigzag"):
            pos = ev.position()
            img_x = (pos.x() - self._pan.x()) / self.zoom
            img_y = (pos.y() - self._pan.y()) / self.zoom
            if math.hypot(img_x - self.dialog.cx, img_y - self.dialog.cy) < (30 / self.zoom):
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


class DistortDialog(QDialog):
    def __init__(self, layer, mode, canvas_refresh, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.mode = mode
        self.canvas_refresh = canvas_refresh
        
        mode_title = tr('menu.distort.' + mode).replace('…', '')
        self.setWindowTitle(f"{tr('menu.distort')} - {mode_title}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.resize(1000, 700)
        
        self.orig_img = layer.image.copy()
        self.preview_img = layer.image.copy()
        self.cx = self.orig_img.width() / 2.0
        self.cy = self.orig_img.height() / 2.0
        
        ptr = self.orig_img.constBits()
        buf = (ctypes.c_uint8 * self.orig_img.sizeInBytes()).from_address(int(ptr))
        self.orig_arr = np.ndarray((self.orig_img.height(), self.orig_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)[:, :self.orig_img.width(), :].copy()
        self.disp_arr = None
        
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._apply_effect)

        self._build_ui()
        self._apply_effect()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        
        self.canvas = DistortCanvas(self)
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
            
        self.amount_sl, self.amt_lbl = add_slider(tr("distort.amount"))
        self.param2_sl, self.p2_lbl = add_slider(tr("distort.param2"))
        
        def hide_p2(): self.param2_sl.hide(); self.p2_lbl.hide()
        def hide_amt(): self.amount_sl.hide(); self.amt_lbl.hide()

        if self.mode == "twirl":
            self.amount_sl.setRange(-720, 720); self.amount_sl.setValue(100); hide_p2()
        elif self.mode in ("pinch", "spherize", "shear"):
            self.amount_sl.setRange(-100, 100); self.amount_sl.setValue(50); hide_p2()
        elif self.mode == "ripple":
            self.amount_sl.setRange(1, 100); self.amount_sl.setValue(10)
            self.param2_sl.setRange(1, 100); self.param2_sl.setValue(30)
        elif self.mode == "wave":
            self.amount_sl.setRange(1, 200); self.amount_sl.setValue(20)
            self.param2_sl.setRange(1, 500); self.param2_sl.setValue(120)
        elif self.mode == "zigzag":
            self.amount_sl.setRange(-100, 100); self.amount_sl.setValue(30)
            self.param2_sl.setRange(1, 50); self.param2_sl.setValue(10)
        elif self.mode == "polar":
            hide_amt(); hide_p2()
            self.mode_combo = QComboBox()
            self.mode_combo.addItem(tr("distort.polar.r2p"), 0)
            self.mode_combo.addItem(tr("distort.polar.p2r"), 1)
            self.mode_combo.currentIndexChanged.connect(self._trigger_update)
            pl.addWidget(self.mode_combo)
        elif self.mode == "displace":
            self.amount_sl.setRange(-200, 200); self.amount_sl.setValue(20)
            self.param2_sl.setRange(-200, 200); self.param2_sl.setValue(20)
            self.load_btn = QPushButton(tr("distort.load_map"))
            self.load_btn.clicked.connect(self._load_map)
            pl.addWidget(self.load_btn)

        pl.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        pl.addWidget(btns)
        root.addWidget(props)

    def _load_map(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("distort.load_map"), "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            img = QImage(path).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            ptr = img.constBits()
            buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
            self.disp_arr = np.ndarray((img.height(), img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf).copy()
            self._trigger_update()

    def _trigger_update(self):
        self._timer.start()

    def _apply_effect(self):
        amount = self.amount_sl.value()
        p2 = self.param2_sl.value()
        
        if amount == 0 and self.mode not in ("polar", "displace"):
            self.preview_img = self.orig_img.copy()
            self.canvas.update()
            return
            
        h, w = self.orig_arr.shape[:2]
        
        Y, X = np.ogrid[:h, :w]
        X_out = np.broadcast_to(X, (h, w)).astype(np.float32).copy()
        Y_out = np.broadcast_to(Y, (h, w)).astype(np.float32).copy()
        
        cx, cy = self.cx, self.cy
        rmax = max(1.0, math.hypot(w, h) / 2.0)
        
        if self.mode in ("twirl", "pinch", "spherize", "zigzag"):
            dx = X_out - cx
            dy = Y_out - cy
            r = np.hypot(dx, dy)
            theta = np.arctan2(dy, dx)
        
        if self.mode == "twirl":
            angle = np.radians(amount)
            mask = r < rmax
            theta_src = theta.copy()
            theta_src[mask] = theta[mask] - angle * ((rmax - r[mask]) / rmax)
            X_out[mask] = cx + r[mask] * np.cos(theta_src[mask])
            Y_out[mask] = cy + r[mask] * np.sin(theta_src[mask])
        elif self.mode in ("pinch", "spherize"):
            a = amount / 100.0
            if self.mode == "spherize": a = -a
            mask = r < rmax
            r_src = r.copy()
            r_src[mask] = rmax * np.power(np.maximum(r[mask], 1e-5) / rmax, 1.0 - a)
            X_out[mask] = cx + r_src[mask] * np.cos(theta[mask])
            Y_out[mask] = cy + r_src[mask] * np.sin(theta[mask])
        elif self.mode == "ripple":
            X_out += amount * np.sin(2 * np.pi * Y_out / max(1, p2))
            Y_out += amount * np.sin(2 * np.pi * X_out / max(1, p2))
        elif self.mode == "wave":
            X_out += amount * np.sin(2 * np.pi * Y_out / max(1, p2))
            Y_out += amount * np.cos(2 * np.pi * X_out / max(1, p2))
        elif self.mode == "zigzag":
            r_src = r - amount * np.sin(max(1, p2) * 2 * np.pi * r / rmax)
            X_out = cx + r_src * np.cos(theta)
            Y_out = cy + r_src * np.sin(theta)
        elif self.mode == "shear":
            X_out -= amount * np.sin(Y_out / h * np.pi)
        elif self.mode == "polar":
            if self.mode_combo.currentIndex() == 0:
                r_src, theta_src = Y_out * (rmax / h), (X_out / w) * 2 * np.pi - np.pi
                X_out, Y_out = cx + r_src * np.cos(theta_src), cy + r_src * np.sin(theta_src)
            else:
                r_dest, theta_dest = Y_out / h * rmax, (X_out / w) * 2 * np.pi - np.pi
                X_out, Y_out = cx + r_dest * np.cos(theta_dest), cy + r_dest * np.sin(theta_dest)
        elif self.mode == "displace" and self.disp_arr is not None:
            dh, dw = self.disp_arr.shape[:2]
            m_Y, m_X = np.clip((Y_out / h * dh).astype(np.int32), 0, dh - 1), np.clip((X_out / w * dw).astype(np.int32), 0, dw - 1)
            d_color = self.disp_arr[m_Y, m_X]
            X_out -= ((d_color[..., 2].astype(np.float32) - 128.0) / 128.0) * amount
            Y_out -= ((d_color[..., 1].astype(np.float32) - 128.0) / 128.0) * p2

        X_idx = np.clip(np.round(X_out).astype(np.int32), 0, w - 1)
        Y_idx = np.clip(np.round(Y_out).astype(np.int32), 0, h - 1)
        res_arr = self.orig_arr[Y_idx, X_idx]
        
        out_of_bounds = (X_out < 0) | (X_out >= w) | (Y_out < 0) | (Y_out >= h)
        if np.any(out_of_bounds): res_arr[out_of_bounds] = 0
            
        self.preview_img = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.canvas.update()

    def accept(self):
        self.layer.image = self.preview_img
        super().accept()