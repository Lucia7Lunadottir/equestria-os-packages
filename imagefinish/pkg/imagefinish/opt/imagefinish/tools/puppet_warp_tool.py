import math
import numpy as np
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QImage, QPainterPath, QTransform, QPen, QPolygonF
from tools.base_tool import BaseTool
from core.document import Document
from tools.warp_tool import WarpTool

class PuppetWarpTool(BaseTool):
    name = "PuppetWarp"
    icon = "📌"
    shortcut = "W"

    def __init__(self):
        super().__init__()
        self.is_transforming = False
        self._target_layer = None
        self._layer_backup = None
        self._offset_backup = None
        self._original_img = None
        self._original_offset = None
        self._sel_origin = None
        self._bounds = QRectF()
        self._is_floating = False
        self._patches = []
        self._fast_mode = False
        self._linked_children = []
        self._proxy_img = None
        self._proxy_scale = 1.0

        self._pins = [] # [{'orig': QPointF, 'curr': QPointF}]
        self._drag_idx = None

    def on_press(self, pos, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked: return
        if getattr(layer, "layer_type", "raster") in ("artboard", "group"): return

        if not self.is_transforming:
            self.is_transforming = True
            self._target_layer = layer
            self._layer_backup = layer.image.copy()
            self._offset_backup = QPoint(layer.offset)

            sel = doc.selection
            if sel and not sel.isEmpty():
                self._is_floating = True
                self._bounds = sel.boundingRect()
                br = self._bounds.toRect()
                local_br = br.translated(-layer.offset).intersected(layer.image.rect())
                if local_br.isEmpty():
                    self.is_transforming = False
                    return
                self._original_img = layer.image.copy(local_br)
                self._original_offset = layer.offset + local_br.topLeft()
                self._sel_origin = QPainterPath(sel)

                import ctypes
                mask_img = QImage(local_br.width(), local_br.height(), QImage.Format.Format_Grayscale8)
                mask_img.fill(0)
                p = QPainter(mask_img)
                p.translate(-self._original_offset.x(), -self._original_offset.y())
                p.fillPath(sel, QColor(255, 255, 255))
                p.end()

                m_arr = np.empty((local_br.height(), mask_img.bytesPerLine()), dtype=np.uint8)
                ctypes.memmove(m_arr.ctypes.data, int(mask_img.constBits()), mask_img.sizeInBytes())
                mask_f = m_arr[:, :local_br.width()].astype(np.float32) / 255.0
                
                f_arr = np.empty((local_br.height(), self._original_img.bytesPerLine() // 4, 4), dtype=np.uint8)
                ctypes.memmove(f_arr.ctypes.data, int(self._original_img.constBits()), self._original_img.sizeInBytes())
                for c in range(4): f_arr[:local_br.height(), :local_br.width(), c] = (f_arr[:local_br.height(), :local_br.width(), c] * mask_f).astype(np.uint8)
                ctypes.memmove(int(self._original_img.bits()), f_arr.ctypes.data, self._original_img.sizeInBytes())
                
                l_arr = np.empty((layer.height(), layer.image.bytesPerLine() // 4, 4), dtype=np.uint8)
                ctypes.memmove(l_arr.ctypes.data, int(layer.image.constBits()), layer.image.sizeInBytes())
                
                inv_mask_f = 1.0 - mask_f
                sy, sx = local_br.y(), local_br.x()
                l_roi = l_arr[sy:sy+local_br.height(), sx:sx+local_br.width()]
                for c in range(4): l_roi[..., c] = (l_roi[..., c] * inv_mask_f).astype(np.uint8)
                ctypes.memmove(int(layer.image.bits()), l_arr.ctypes.data, layer.image.sizeInBytes())
            else:
                self._is_floating = False
                br = Document._nontransparent_bounds(layer.image)
                if br.isEmpty(): br = QRect(0, 0, layer.width() or 100, layer.height() or 100)
                self._bounds = QRectF(br).translated(QPointF(layer.offset))
                self._original_img = layer.image.copy(br)
                self._original_offset = layer.offset + br.topLeft()
                self._sel_origin = None
                layer.image = QImage(1, 1, QImage.Format.Format_ARGB32)
                layer.image.fill(Qt.GlobalColor.transparent)

            max_dim = max(self._original_img.width(), self._original_img.height())
            if max_dim > 600:
                self._proxy_scale = 600.0 / max_dim
                self._proxy_img = self._original_img.scaled(int(self._original_img.width() * self._proxy_scale),
                                                            int(self._original_img.height() * self._proxy_scale),
                                                            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
            else:
                self._proxy_img = self._original_img
                
            self._update_preview()

        # Hit test existing pins
        hit_dist = 10 / max(0.01, opts.get("_zoom", 1.0))
        self._drag_idx = None
        for i, pin in enumerate(self._pins):
            if math.hypot(pos.x() - pin['curr'].x(), pos.y() - pin['curr'].y()) < hit_dist:
                self._drag_idx = i
                break

        if self._drag_idx is not None:
            if opts.get("_alt", False):
                self._pins.pop(self._drag_idx)
                self._drag_idx = None
                self._update_preview()
        else:
            self._pins.append({'orig': QPointF(pos), 'curr': QPointF(pos)})
            self._drag_idx = len(self._pins) - 1
            self._update_preview()

    def _calc_grid(self, steps_u, steps_v):
        x0, y0 = self._bounds.left(), self._bounds.top()
        w, h = self._bounds.width(), self._bounds.height()
        uu, vv = np.meshgrid(np.linspace(0, 1, steps_u), np.linspace(0, 1, steps_v))
        grid_x = x0 + uu * w
        grid_y = y0 + vv * h

        if not self._pins: return grid_x, grid_y
        if len(self._pins) == 1:
            dx = self._pins[0]['curr'].x() - self._pins[0]['orig'].x()
            dy = self._pins[0]['curr'].y() - self._pins[0]['orig'].y()
            return grid_x + dx, grid_y + dy

        P = np.array([[p['orig'].x(), p['orig'].y()] for p in self._pins])
        Q = np.array([[p['curr'].x(), p['curr'].y()] for p in self._pins])
        D = Q - P

        dx = grid_x[..., None] - P[:, 0]
        dy = grid_y[..., None] - P[:, 1]
        dist_sq = np.maximum(dx**2 + dy**2, 1e-5)
        w_dist = 1.0 / (dist_sq ** 2) # Inverse distance power 4
        w_norm = w_dist / np.sum(w_dist, axis=-1, keepdims=True)

        disp_x = np.sum(w_norm * D[:, 0], axis=-1)
        disp_y = np.sum(w_norm * D[:, 1], axis=-1)

        return grid_x + disp_x, grid_y + disp_y

    def _update_preview(self, fast=False):
        if not self._original_img: return
        self._fast_mode = fast
        steps = 8 if fast else 16
        xs, ys = self._calc_grid(steps + 1, steps + 1)
        
        src_img = self._proxy_img if fast else self._original_img
        w, h = src_img.width(), src_img.height()

        patches = []
        for i in range(steps):
            for j in range(steps):
                u0, v0 = j/steps, i/steps
                u1, v1 = (j+1)/steps, (i+1)/steps
                s0, s1 = QPointF(u0*w, v0*h), QPointF(u1*w, v0*h)
                s2, s3 = QPointF(u1*w, v1*h), QPointF(u0*w, v1*h)
                d0, d1 = QPointF(xs[i, j], ys[i, j]), QPointF(xs[i, j+1], ys[i, j+1])
                d2, d3 = QPointF(xs[i+1, j+1], ys[i+1, j+1]), QPointF(xs[i+1, j], ys[i+1, j])
                patches.append((s0, s1, s2, s3, d0, d1, d2, d3))
        self._patches = patches

    def on_move(self, pos, doc, fg, bg, opts):
        if not self.is_transforming or self._drag_idx is None: return
        self._pins[self._drag_idx]['curr'] = QPointF(pos)
        self._update_preview(fast=True)

    def on_release(self, pos, doc, fg, bg, opts): 
        if self._drag_idx is not None:
            self._drag_idx = None
            self._update_preview(fast=False)

    def floating_preview(self):
        if self.is_transforming and hasattr(self, "_patches") and self._patches: 
            return ("warp", self._proxy_img if self._fast_mode else self._original_img, self._patches, self._fast_mode)
        return None

    def draw_overlays(self, painter: QPainter, pw: float, doc):
        if not self.is_transforming: return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, pin in enumerate(self._pins):
            painter.setPen(QPen(QColor(0, 0, 0, 180), pw * 2))
            painter.setBrush(QColor(255, 255, 255) if i != self._drag_idx else QColor(200, 200, 255))
            painter.drawEllipse(pin['curr'], 5*pw, 5*pw)
        painter.restore()

    def apply_transform(self, doc):
        if not self.is_transforming: return
        layer = self._target_layer
        self._update_preview(fast=False)
        
        if layer and hasattr(self, "_patches") and self._patches:
            xs_b, ys_b = self._calc_grid(11, 11)
            min_x, max_x, min_y, max_y = np.min(xs_b), np.max(xs_b), np.min(ys_b), np.max(ys_b)
            out_w, out_h = int(math.ceil(max_x - min_x)) + 2, int(math.ceil(max_y - min_y)) + 2
            if out_w > 0 and out_h > 0:
                out_img = QImage(out_w, out_h, QImage.Format.Format_ARGB32_Premultiplied)
                out_img.fill(Qt.GlobalColor.transparent)
                p = QPainter(out_img)
                p.translate(-min_x, -min_y)
                WarpTool.draw_warp_patches(p, self._original_img, self._patches, fast=False)
                p.end()

                if self._is_floating:
                    p = QPainter(layer.image)
                    p.drawImage(QPoint(int(min_x - layer.offset.x()), int(min_y - layer.offset.y())), out_img)
                    p.end()
                else:
                    layer.image = out_img
                    layer.offset = QPoint(int(min_x), int(min_y))
        if self._is_floating: doc.selection = None
        self._reset_state()

    def cancel_transform(self, doc):
        if self._layer_backup is not None and getattr(self, "_target_layer", None):
            self._target_layer.image = self._layer_backup
            self._target_layer.offset = self._offset_backup
            if self._sel_origin: doc.selection = self._sel_origin
        self._reset_state()

    def _reset_state(self):
        self.is_transforming = False
        self._target_layer = self._layer_backup = self._original_img = self._patches = None
        self._pins = []

    def needs_history_push(self): return False
    def cursor(self): return Qt.CursorShape.CrossCursor if self.is_transforming else Qt.CursorShape.ArrowCursor