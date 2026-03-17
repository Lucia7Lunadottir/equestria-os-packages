import math
import numpy as np
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QImage, QPainterPath, QTransform, QPen, QPolygonF
from tools.base_tool import BaseTool
from core.document import Document


class WarpTool(BaseTool):
    name = "Warp"
    icon = "🕸️"
    shortcut = "V"

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
        self._pts = []
        self._drag_idx = None
        self._grid_steps = 10
        self._patches = []
        self._fast_mode = False
        self._linked_children = []
        self._proxy_img = None
        self._proxy_scale = 1.0

    def _get_handle_hit(self, pos: QPointF, zoom: float):
        hit_dist = 8 / max(0.01, zoom)
        best_dist = float('inf')
        best_idx = None
        if not self._pts: return None
        for r in range(4):
            for c in range(4):
                pt = self._pts[r][c]
                d = math.hypot(pos.x() - pt.x(), pos.y() - pt.y())
                if d < best_dist and d <= hit_dist:
                    best_dist = d
                    best_idx = (r, c)
        return best_idx

    def on_press(self, pos, doc, fg, bg, opts):
        if not self.is_transforming and opts.get("move_auto_select", False):
            for i in range(len(doc.layers) - 1, -1, -1):
                l = doc.layers[i]
                if not l.visible or l.locked: continue
                if getattr(l, "layer_type", "raster") == "artboard":
                    if l.artboard_rect and l.artboard_rect.contains(pos):
                        doc.active_layer_index = i
                        break
                elif getattr(l, "layer_type", "raster") == "group": continue
                else:
                    if l.image.isNull(): continue
                    lx, ly = int(pos.x() - l.offset.x()), int(pos.y() - l.offset.y())
                    if 0 <= lx < l.width() and 0 <= ly < l.height():
                        if (l.image.pixel(lx, ly) >> 24) & 0xFF > 0:
                            doc.active_layer_index = i
                            break

        layer = doc.get_active_layer()
        if not layer or layer.locked: return
        if getattr(layer, "layer_type", "raster") in ("artboard", "group"): return

        sel = doc.selection
        has_sel = sel and not sel.isEmpty()
        if getattr(layer, "lock_position", False) and not has_sel: return
        if getattr(layer, "lock_pixels", False) and has_sel: return

        if not self.is_transforming:
            self.is_transforming = True
            self._target_layer = layer
            self._layer_backup = layer.image.copy()
            self._offset_backup = QPoint(layer.offset)

            if has_sel:
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

                mask_img = QImage(local_br.width(), local_br.height(), QImage.Format.Format_Grayscale8)
                mask_img.fill(0)
                p = QPainter(mask_img)
                p.translate(-self._original_offset.x(), -self._original_offset.y())
                p.fillPath(sel, QColor(255, 255, 255))
                p.end()

                m_ptr = mask_img.bits(); m_ptr.setsize(mask_img.sizeInBytes())
                m_arr = np.ndarray((local_br.height(), mask_img.bytesPerLine()), dtype=np.uint8, buffer=m_ptr)
                mask_f = m_arr[:, :local_br.width()].astype(np.float32) / 255.0

                f_ptr = self._original_img.bits(); f_ptr.setsize(self._original_img.sizeInBytes())
                f_arr = np.ndarray((local_br.height(), self._original_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=f_ptr)
                for c in range(4): f_arr[:local_br.height(), :local_br.width(), c] = (f_arr[:local_br.height(), :local_br.width(), c] * mask_f).astype(np.uint8)

                l_ptr = layer.image.bits(); l_ptr.setsize(layer.image.sizeInBytes())
                l_arr = np.ndarray((layer.height(), layer.image.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=l_ptr)

                inv_mask_f = 1.0 - mask_f
                sy, sx = local_br.y(), local_br.x()
                l_roi = l_arr[sy:sy+local_br.height(), sx:sx+local_br.width()]
                for c in range(4): l_roi[..., c] = (l_roi[..., c] * inv_mask_f).astype(np.uint8)
            else:
                self._is_floating = False
                br = Document._nontransparent_bounds(layer.image)
                if br.isEmpty():
                    br = QRect(0, 0, layer.width() or 100, layer.height() or 100)
                self._bounds = QRectF(br).translated(QPointF(layer.offset))
                self._original_img = layer.image.copy(br)
                self._original_offset = layer.offset + br.topLeft()
                self._sel_origin = None
                layer.image = QImage(1, 1, QImage.Format.Format_ARGB32)
                layer.image.fill(Qt.GlobalColor.transparent)

            # Создаем легковесный прокси для мгновенного рендера при перетаскивании
            max_dim = max(self._original_img.width(), self._original_img.height())
            if max_dim > 600:
                self._proxy_scale = 600.0 / max_dim
                self._proxy_img = self._original_img.scaled(
                    int(self._original_img.width() * self._proxy_scale),
                    int(self._original_img.height() * self._proxy_scale),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )
            else:
                self._proxy_scale = 1.0
                self._proxy_img = self._original_img

            self._pts = []
            for r in range(4):
                row_pts = []
                for c in range(4):
                    x = self._bounds.left() + self._bounds.width() * c / 3.0
                    y = self._bounds.top() + self._bounds.height() * r / 3.0
                    row_pts.append(QPointF(x, y))
                self._pts.append(row_pts)

            self._update_preview()

        self._drag_idx = self._get_handle_hit(QPointF(pos), opts.get("_zoom", 1.0))

    def _calc_grid(self, steps_u, steps_v):
        """Векторизованное вычисление всей поверхности Безье через умножение матриц NumPy."""
        u = np.linspace(0, 1, steps_u)
        v = np.linspace(0, 1, steps_v)
        bu = np.array([(1-u)**3, 3*u*(1-u)**2, 3*u**2*(1-u), u**3])
        bv = np.array([(1-v)**3, 3*v*(1-v)**2, 3*v**2*(1-v), v**3])
        pts_x = np.array([[self._pts[r][c].x() for c in range(4)] for r in range(4)])
        pts_y = np.array([[self._pts[r][c].y() for c in range(4)] for r in range(4)])
        return bv.T @ pts_x @ bu, bv.T @ pts_y @ bu

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
        r, c = self._drag_idx
        self._pts[r][c] = QPointF(pos)
        self._update_preview(fast=True)

    def on_release(self, pos, doc, fg, bg, opts): 
        if self._drag_idx is not None:
            self._drag_idx = None
            self._update_preview(fast=False)

    def floating_preview(self):
        if self.is_transforming and hasattr(self, "_patches") and self._patches: return ("warp", self._proxy_img if self._fast_mode else self._original_img, self._patches, self._fast_mode)
        return None

    def draw_overlays(self, painter: QPainter, pw: float, doc):
        if not self.is_transforming or not self._pts: return
        
        xs_h, ys_h = self._calc_grid(21, 4)
        xs_v, ys_v = self._calc_grid(4, 21)
        
        polys_h = [QPolygonF([QPointF(xs_h[i, j], ys_h[i, j]) for j in range(21)]) for i in range(4)]
        polys_v = [QPolygonF([QPointF(xs_v[i, j], ys_v[i, j]) for i in range(21)]) for j in range(4)]
        
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 180), pw * 2)); painter.setBrush(Qt.BrushStyle.NoBrush)
        for poly in polys_h + polys_v: painter.drawPolyline(poly)
            
        painter.setPen(QPen(QColor(0, 0, 0, 150), pw))
        for poly in polys_h + polys_v: painter.drawPolyline(poly)
            
        painter.setPen(QPen(QColor(100, 100, 100, 150), pw))
        for r in range(4):
            for c in range(3): painter.drawLine(self._pts[r][c], self._pts[r][c+1])
        for c in range(4):
            for r in range(3): painter.drawLine(self._pts[r][c], self._pts[r+1][c])
            
        painter.setPen(QPen(QColor(0, 0, 0), pw)); painter.setBrush(QColor(255, 255, 255))
        s = 3 * pw
        for r in range(4):
            for c in range(4): painter.drawEllipse(self._pts[r][c], s, s)
        painter.restore()

    def apply_transform(self, doc):
        if not self.is_transforming: return
        layer = self._target_layer
        
        self._update_preview(fast=False)
        
        if layer and hasattr(self, "_patches") and self._patches:
            xs_b, ys_b = self._calc_grid(11, 11)
            min_x, max_x = np.min(xs_b), np.max(xs_b)
            min_y, max_y = np.min(ys_b), np.max(ys_b)

            out_w = int(math.ceil(max_x - min_x)) + 2
            out_h = int(math.ceil(max_y - min_y)) + 2
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

    @staticmethod
    def draw_warp_patches(painter: QPainter, src_img: QImage, patches: list, fast: bool):
        # Отключаем сглаживание геометрии, чтобы между треугольниками не было прозрачных швов (дырок)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not fast)
            
        for s0, s1, s2, s3, d0, d1, d2, d3 in patches:
            # Разбиваем каждый прямоугольник сетки на 2 треугольника
            for src_tri, dst_tri in [((s0, s1, s2), (d0, d1, d2)), ((s0, s2, s3), (d0, d2, d3))]:
                ts = QTransform(src_tri[1].x() - src_tri[0].x(), src_tri[1].y() - src_tri[0].y(), 0,
                                src_tri[2].x() - src_tri[0].x(), src_tri[2].y() - src_tri[0].y(), 0,
                                src_tri[0].x(),                  src_tri[0].y(),                  1)
                td = QTransform(dst_tri[1].x() - dst_tri[0].x(), dst_tri[1].y() - dst_tri[0].y(), 0,
                                dst_tri[2].x() - dst_tri[0].x(), dst_tri[2].y() - dst_tri[0].y(), 0,
                                dst_tri[0].x(),                  dst_tri[0].y(),                  1)
                inv_ts, ok = ts.inverted()
                if not ok: continue
                
                painter.save()
                painter.setTransform(inv_ts * td, combine=True)
                
                path = QPainterPath()
                path.addPolygon(QPolygonF([src_tri[0], src_tri[1], src_tri[2]]))
                painter.setClipPath(path)
                
                min_x = min(src_tri[0].x(), src_tri[1].x(), src_tri[2].x())
                min_y = min(src_tri[0].y(), src_tri[1].y(), src_tri[2].y())
                max_x = max(src_tri[0].x(), src_tri[1].x(), src_tri[2].x())
                max_y = max(src_tri[0].y(), src_tri[1].y(), src_tri[2].y())
                
                adj = QRectF(min_x, min_y, max_x - min_x, max_y - min_y).adjusted(-1, -1, 1, 1)
                painter.drawImage(adj, src_img, adj)
                painter.restore()

    def cancel_transform(self, doc):
        if not self.is_transforming: return
        layer = self._target_layer
        if layer and self._layer_backup is not None:
            layer.image = self._layer_backup
            layer.offset = self._offset_backup
            if self._sel_origin: doc.selection = self._sel_origin
        self._reset_state()

    def _reset_state(self):
        self.is_transforming = False
        self._target_layer = None
        self._layer_backup = None
        self._offset_backup = None
        self._original_img = None
        self._original_offset = None
        self._sel_origin = None
        self._pts = []
        self._drag_idx = None
        self._patches = []
        self._fast_mode = False
        self._proxy_img = None
        self._proxy_scale = 1.0

    def needs_history_push(self): return False
    def cursor(self): return Qt.CursorShape.CrossCursor if self.is_transforming else Qt.CursorShape.ArrowCursor