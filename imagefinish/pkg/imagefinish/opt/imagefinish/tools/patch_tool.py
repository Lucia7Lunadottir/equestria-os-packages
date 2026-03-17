import numpy as np
from PyQt6.QtCore import QPoint, QPointF, Qt, QRect
from PyQt6.QtGui import QPainterPath, QImage, QPainter, QColor, QPolygonF, QPen
from tools.base_tool import BaseTool
from tools.lasso_tools import LassoMixin
from tools.effect_tools import _box_blur_np

class PatchTool(BaseTool, LassoMixin):
    name = "Patch"
    icon = "🩹"
    shortcut = "J"

    def __init__(self):
        self.points = []
        self._mode = "new"  # 'new' (рисование лассо) или 'drag' (перетаскивание заплатки)
        self._drag_start = None
        self._drag_offset = QPoint(0, 0)
        self._sel_path = None
        self._layer_backup = None
        self._current_opacity = 1.0

    def on_press(self, pos, doc, fg, bg, opts):
        self._current_opacity = float(opts.get("patch_opacity", 1.0))
        sel = doc.selection
        has_sel = sel and not sel.isEmpty()

        if has_sel and sel.contains(QPointF(pos)):
            self._mode = "drag"
            self._drag_start = pos
            self._drag_offset = QPoint(0, 0)
            self._sel_path = QPainterPath(sel)
            layer = doc.get_active_layer()
            if layer and not layer.locked and not layer.image.isNull():
                self._layer_backup = layer.image.copy()
        else:
            self._mode = "new"
            self.points = [QPointF(pos)]
            doc.selection = None

    def on_move(self, pos, doc, fg, bg, opts):
        if self._mode == "new":
            if self.points:
                self.points.append(QPointF(pos))
        elif self._mode == "drag":
            if self._drag_start:
                self._drag_offset = pos - self._drag_start

    def on_release(self, pos, doc, fg, bg, opts):
        if self._mode == "new":
            if len(self.points) > 2:
                path = QPainterPath()
                path.addPolygon(QPolygonF(self.points))
                path.closeSubpath()
                self._apply_path(doc, path, opts)
            self.points = []
        elif self._mode == "drag":
            self._apply_patch(doc, opts)
            self._drag_start = None
            self._drag_offset = QPoint(0, 0)
            self._sel_path = None
            self._layer_backup = None
            self._mode = "new"

    def _apply_patch(self, doc, opts):
        if self._drag_offset.isNull(): return
        layer = doc.get_active_layer()
        if not layer or layer.locked or not self._layer_backup or not self._sel_path: return

        w, h = layer.width(), layer.height()
        br = self._sel_path.boundingRect().toRect().intersected(QRect(0, 0, w, h))
        if br.isEmpty(): return

        dx, dy = self._drag_offset.x(), self._drag_offset.y()
        
        mask_img = QImage(w, h, QImage.Format.Format_Grayscale8)
        mask_img.fill(0)
        mp = QPainter(mask_img)
        mp.fillPath(self._sel_path, QColor(255))
        mp.end()

        import ctypes
        arr = np.empty((h, layer.image.bytesPerLine() // 4, 4), dtype=np.uint8)
        ctypes.memmove(arr.ctypes.data, int(self._layer_backup.constBits()), self._layer_backup.sizeInBytes())
        arr = arr[:, :w, :].copy()

        m_arr = np.empty((h, mask_img.bytesPerLine()), dtype=np.uint8)
        ctypes.memmove(m_arr.ctypes.data, int(mask_img.constBits()), mask_img.sizeInBytes())
        m_arr = m_arr[:, :w].copy()

        y_idx, x_idx = np.where(m_arr > 0)
        if len(y_idx) == 0: return
        y1, y2 = y_idx.min(), y_idx.max() + 1
        x1, x2 = x_idx.min(), x_idx.max() + 1

        mask_roi = m_arr[y1:y2, x1:x2].astype(np.float32) / 255.0
        target_roi = arr[y1:y2, x1:x2].astype(np.float32)

        sy1, sy2 = y1 + dy, y2 + dy
        sx1, sx2 = x1 + dx, x2 + dx
        
        source_roi = np.zeros_like(target_roi)
        sy_start, sy_end = max(0, sy1), min(h, sy2)
        sx_start, sx_end = max(0, sx1), min(w, sx2)
        ry_start, ry_end = sy_start - sy1, (sy_start - sy1) + (sy_end - sy_start)
        rx_start, rx_end = sx_start - sx1, (sx_start - sx1) + (sx_end - sx_start)
        if sy_start < sy_end and sx_start < sx_end:
            source_roi[ry_start:ry_end, rx_start:rx_end] = arr[sy_start:sy_end, sx_start:sx_end]

        # Находим границы выделения (для выравнивания яркости Mean Value)
        mask_bin = mask_roi > 0.5
        up = np.roll(mask_bin, 1, axis=0); up[0, :] = False
        down = np.roll(mask_bin, -1, axis=0); down[-1, :] = False
        left = np.roll(mask_bin, 1, axis=1); left[:, 0] = False
        right = np.roll(mask_bin, -1, axis=1); right[:, -1] = False
        eroded = mask_bin & up & down & left & right
        boundary = mask_bin & ~eroded

        if np.any(boundary):
            t_mean = np.mean(target_roi[boundary], axis=0)
            s_mean = np.mean(source_roi[boundary], axis=0)
            diff = t_mean - s_mean
            diff[3] = 0 # Альфа-канал не сдвигаем
            cloned = np.clip(source_roi + diff, 0, 255)
        else:
            cloned = source_roi

        # Динамическое многопроходное Гауссово сглаживание маски (Feathering)
        diffusion = int(opts.get("patch_diffusion", 5))
        base_r = max(2, min(w, h) // 40)
        blur_r = max(1, int(base_r * (diffusion / 5.0)))
        
        mask_rgb = np.repeat(mask_roi[:, :, np.newaxis] * 255, 3, axis=2).astype(np.uint8)
        smooth_mask_rgb = mask_rgb
        for _ in range(3):
            smooth_mask_rgb = _box_blur_np(smooth_mask_rgb, blur_r)
            
        smooth_mask = smooth_mask_rgb[..., 0:1].astype(np.float32) / 255.0

        final_roi = target_roi.copy()
        op = self._current_opacity
        final_roi[..., :3] = target_roi[..., :3] * (1 - smooth_mask * op) + cloned[..., :3] * (smooth_mask * op)
        arr[y1:y2, x1:x2] = final_roi.astype(np.uint8)

        new_img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        out_ptr = new_img.bits()
        out_ptr.setsize(new_img.sizeInBytes())
        out_arr = np.frombuffer(out_ptr, dtype=np.uint8).reshape((h, new_img.bytesPerLine() // 4, 4))
        out_arr[:, :w, :] = arr
        del out_arr
        del out_ptr
        layer.image = new_img

    def draw_overlays(self, painter, pw, doc):
        if self._mode == "new" and len(self.points) > 1:
            painter.setPen(QPen(QColor(0, 0, 0), pw))
            painter.drawPolyline(QPolygonF(self.points))
            pen = QPen(QColor(255, 255, 255), pw)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF(self.points))
        elif self._mode == "drag" and self._sel_path and not self._drag_offset.isNull():
            painter.setPen(QPen(QColor(0, 0, 0, 180), pw))
            translated = self._sel_path.translated(self._drag_offset.x(), self._drag_offset.y())
            painter.drawPath(translated)
            pen = QPen(QColor(255, 255, 255, 200), pw)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawPath(translated)

    def floating_preview(self):
        if self._mode == "drag" and self._layer_backup and self._sel_path and not self._drag_offset.isNull():
            br = self._sel_path.boundingRect().toRect()
            patch_img = QImage(br.width(), br.height(), QImage.Format.Format_ARGB32_Premultiplied)
            patch_img.fill(0)
            
            p = QPainter(patch_img)
            p.setOpacity(self._current_opacity)
            local_path = self._sel_path.translated(-br.x(), -br.y())
            p.setClipPath(local_path)
            # Отрисовываем исходник со смещением, чтобы показать превью "Заплатки" внутри выделения
            source_rect = br.translated(self._drag_offset)
            p.drawImage(0, 0, self._layer_backup, source_rect.x(), source_rect.y(), source_rect.width(), source_rect.height())
            p.end()
            
            return (patch_img, br.topLeft())
        return None

    def needs_history_push(self) -> bool: return True

    def cursor(self):
        return Qt.CursorShape.CrossCursor


class SpotHealingTool(BaseTool):
    name = "SpotHealing"
    icon = "🩹✨"
    shortcut = "J"

    def __init__(self):
        super().__init__()
        self._pts = []
        self._target_layer = None
        self._current_size = 20
        self._current_opacity = 1.0

    def on_press(self, pos, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked or layer.image.isNull() or getattr(layer, "lock_pixels", False): 
            return
        self._pts = [pos]
        self._target_layer = layer
        self._current_size = int(opts.get("brush_size", 20))
        self._current_opacity = float(opts.get("brush_opacity", 1.0))

    def on_move(self, pos, doc, fg, bg, opts):
        if self._pts:
            self._pts.append(pos)

    def on_release(self, pos, doc, fg, bg, opts):
        if not self._pts: return
        
        layer = self._target_layer
        w, h = layer.width(), layer.height()
        
        mask_img = QImage(w, h, QImage.Format.Format_Grayscale8)
        mask_img.fill(0)
        p = QPainter(mask_img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255), self._current_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        poly = QPolygonF([QPointF(pt - layer.offset) for pt in self._pts])
        p.drawPolyline(poly)
        p.end()

        import ctypes
        m_arr = np.empty((h, mask_img.bytesPerLine()), dtype=np.uint8)
        ctypes.memmove(m_arr.ctypes.data, int(mask_img.constBits()), mask_img.sizeInBytes())
        m_arr = m_arr[:, :w].copy()
        y_idx, x_idx = np.where(m_arr > 0)
        if len(y_idx) == 0: 
            self._pts = []
            return
            
        y1, y2 = max(0, y_idx.min() - self._current_size), min(h, y_idx.max() + self._current_size + 1)
        x1, x2 = max(0, x_idx.min() - self._current_size), min(w, x_idx.max() + self._current_size + 1)
        rw, rh = x2 - x1, y2 - y1

        # Автоматический поиск чистой текстуры рядом со штрихом
        dx, dy = 0, 0
        offsets = [(rw, 0), (-rw, 0), (0, rh), (0, -rh), (rw, rh), (-rw, -rh), (rw, -rh), (-rw, rh)]
        for ox, oy in offsets:
            if 0 <= x1 + ox and x2 + ox < w and 0 <= y1 + oy and y2 + oy < h:
                dx, dy = ox, oy
                break
                
        if dx == 0 and dy == 0:
            dx, dy = min(rw, 10), min(rh, 10) # Fallback чтобы края тоже работали

        arr = np.empty((h, layer.image.bytesPerLine() // 4, 4), dtype=np.uint8)
        ctypes.memmove(arr.ctypes.data, int(layer.image.constBits()), layer.image.sizeInBytes())
        arr = arr[:, :w, :].copy()
        
        mask_roi = m_arr[y1:y2, x1:x2].astype(np.float32) / 255.0
        target_roi = arr[y1:y2, x1:x2].astype(np.float32)

        sy1, sy2 = y1 + dy, y2 + dy
        sx1, sx2 = x1 + dx, x2 + dx
        
        source_roi = np.zeros_like(target_roi)
        sy_start, sy_end = max(0, sy1), min(h, sy2)
        sx_start, sx_end = max(0, sx1), min(w, sx2)
        ry_start, ry_end = sy_start - sy1, (sy_start - sy1) + (sy_end - sy_start)
        rx_start, rx_end = sx_start - sx1, (sx_start - sx1) + (sx_end - sx_start)
        if sy_start < sy_end and sx_start < sx_end:
            source_roi[ry_start:ry_end, rx_start:rx_end] = arr[sy_start:sy_end, sx_start:sx_end].astype(np.float32)

        mask_bin = mask_roi > 0.5
        up = np.roll(mask_bin, 1, axis=0); up[0, :] = False
        down = np.roll(mask_bin, -1, axis=0); down[-1, :] = False
        left = np.roll(mask_bin, 1, axis=1); left[:, 0] = False
        right = np.roll(mask_bin, -1, axis=1); right[:, -1] = False
        boundary = mask_bin & ~(mask_bin & up & down & left & right)

        if np.any(boundary):
            t_mean = np.mean(target_roi[boundary], axis=0)
            s_mean = np.mean(source_roi[boundary], axis=0)
            diff = t_mean - s_mean
            diff[3] = 0
            cloned = np.clip(source_roi + diff, 0, 255)
        else:
            cloned = source_roi

        smooth_mask_rgb = np.repeat(mask_roi[:, :, np.newaxis] * 255, 3, axis=2).astype(np.uint8)
        blur_r = max(1, min(rw, rh) // 5)
        for _ in range(3): smooth_mask_rgb = _box_blur_np(smooth_mask_rgb, blur_r)
        smooth_mask = smooth_mask_rgb[..., 0:1].astype(np.float32) / 255.0

        final_roi = target_roi.copy()
        op = self._current_opacity
        final_roi[..., :3] = target_roi[..., :3] * (1 - smooth_mask * op) + cloned[..., :3] * (smooth_mask * op)
        arr[y1:y2, x1:x2] = final_roi.astype(np.uint8)

        new_img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        out_arr = np.empty((h, new_img.bytesPerLine() // 4, 4), dtype=np.uint8)
        ctypes.memmove(out_arr.ctypes.data, int(layer.image.constBits()), layer.image.sizeInBytes())
        out_arr[:, :w, :] = arr
        ctypes.memmove(int(new_img.bits()), out_arr.ctypes.data, new_img.sizeInBytes())
        layer.image = new_img
        self._pts = []

    def draw_overlays(self, painter, pw, doc):
        if len(self._pts) > 1:
            painter.setPen(QPen(QColor(0, 0, 0, 150), self._current_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            poly = QPolygonF([QPointF(pt) for pt in self._pts])
            painter.drawPolyline(poly)

    def needs_history_push(self): return True
    def cursor(self): return Qt.CursorShape.CrossCursor


class RedEyeTool(BaseTool):
    name = "RedEye"
    icon = "👁️"
    shortcut = "J"

    def __init__(self):
        super().__init__()
        self._start = None
        self._end = None

    def on_press(self, pos, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked or layer.image.isNull() or getattr(layer, "lock_pixels", False): 
            return
        self._start = pos
        self._end = pos

    def on_move(self, pos, doc, fg, bg, opts):
        if self._start:
            self._end = pos

    def on_release(self, pos, doc, fg, bg, opts):
        if not self._start: return
        self._end = pos
        
        rect = QRect(self._start, self._end).normalized()
        if rect.width() < 5 or rect.height() < 5:
            # Если просто кликнули, создаем рамку на основе ползунка размера
            r = int(opts.get("red_eye_size", 50))
            rect = QRect(pos.x() - r, pos.y() - r, r*2, r*2)

        layer = doc.get_active_layer()
        w, h = layer.width(), layer.height()
        rect = rect.translated(-layer.offset).intersected(QRect(0, 0, w, h))
        if rect.isEmpty():
            self._start = None
            return

        import ctypes
        arr = np.empty((h, layer.image.bytesPerLine() // 4, 4), dtype=np.uint8)
        ctypes.memmove(arr.ctypes.data, int(layer.image.constBits()), layer.image.sizeInBytes())
        roi = arr[rect.top():rect.bottom()+1, rect.left():rect.right()+1]

        if roi.size > 0:
            B = roi[..., 0].astype(np.float32)
            G = roi[..., 1].astype(np.float32)
            R = roi[..., 2].astype(np.float32)

            # Формула обнаружения покраснения (Redness)
            redness = R - (G + B) / 2.0
            mask = np.clip((redness - 15) / 30.0, 0.0, 1.0)
            
            darken = float(opts.get("red_eye_darken", 50)) / 100.0
            target_lum = ((G + B) / 2.0) * (1.0 - darken)

            # Заменяем красные пиксели на серые/темные
            roi[..., 0] = np.clip(B * (1 - mask) + target_lum * mask, 0, 255).astype(np.uint8)
            roi[..., 1] = np.clip(G * (1 - mask) + target_lum * mask, 0, 255).astype(np.uint8)
            roi[..., 2] = np.clip(R * (1 - mask) + target_lum * mask, 0, 255).astype(np.uint8)
            
            new_img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            out_arr = np.ascontiguousarray(arr)
            ctypes.memmove(int(new_img.bits()), out_arr.ctypes.data, new_img.sizeInBytes())
            layer.image = new_img

        self._start = None

    def draw_overlays(self, painter, pw, doc):
        if self._start and self._end and self._start != self._end:
            r = QRect(self._start, self._end).normalized()
            painter.setPen(QPen(QColor(0, 0, 0, 150), pw, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)
            painter.setPen(QPen(QColor(255, 255, 255, 200), pw, Qt.PenStyle.DotLine))
            painter.drawRect(r)

    def needs_history_push(self): return True
    def cursor(self): return Qt.CursorShape.CrossCursor


class HealingBrushTool(BaseTool):
    name = "HealingBrush"
    icon = "🩹🖌️"
    shortcut = "J"

    def __init__(self):
        super().__init__()
        self._source_pos = None
        self._paint_offset = None
        self._source_img = None
        self._crosshair_pos = None
        self._pts = []
        self._target_layer = None
        self._current_size = 20
        self._current_opacity = 1.0

    def on_press(self, pos, doc, fg, bg, opts):
        if opts.get("_alt", False):
            self._source_pos = pos
            return

        if self._source_pos is None:
            return

        self._paint_offset = pos - self._source_pos
        layer = doc.get_active_layer()
        if not layer or layer.locked or layer.image.isNull() or getattr(layer, "lock_pixels", False): 
            return

        self._source_img = layer.image.copy()
        self._source_offset = layer.offset
        self._target_layer = layer
        self._pts = [pos]
        self._current_size = int(opts.get("brush_size", 20))
        self._current_opacity = float(opts.get("brush_opacity", 1.0))
        self._crosshair_pos = pos - self._paint_offset

    def on_move(self, pos, doc, fg, bg, opts):
        if opts.get("_alt", False):
            self._source_pos = pos
            return
        if self._source_pos is None or self._source_img is None or not self._pts:
            return
        self._pts.append(pos)
        self._crosshair_pos = pos - self._paint_offset

    def on_release(self, pos, doc, fg, bg, opts):
        if opts.get("_alt", False) or not self._pts or self._source_img is None:
            return
        
        layer = self._target_layer
        w, h = layer.width(), layer.height()
        
        mask_img = QImage(w, h, QImage.Format.Format_Grayscale8)
        mask_img.fill(0)
        p = QPainter(mask_img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255), self._current_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        poly = QPolygonF([QPointF(pt - layer.offset) for pt in self._pts])
        p.drawPolyline(poly)
        p.end()

        import ctypes
        m_arr = np.empty((h, mask_img.bytesPerLine()), dtype=np.uint8)
        ctypes.memmove(m_arr.ctypes.data, int(mask_img.constBits()), mask_img.sizeInBytes())
        m_arr = m_arr[:, :w].copy()
        y_idx, x_idx = np.where(m_arr > 0)
        if len(y_idx) == 0: 
            self._reset_stroke()
            return
            
        y1, y2 = max(0, y_idx.min() - self._current_size), min(h, y_idx.max() + self._current_size + 1)
        x1, x2 = max(0, x_idx.min() - self._current_size), min(w, x_idx.max() + self._current_size + 1)

        dx = int(self._paint_offset.x() - layer.offset.x() + self._source_offset.x())
        dy = int(self._paint_offset.y() - layer.offset.y() + self._source_offset.y())

        arr = np.empty((h, layer.image.bytesPerLine() // 4, 4), dtype=np.uint8)
        ctypes.memmove(arr.ctypes.data, int(layer.image.constBits()), layer.image.sizeInBytes())
        arr = arr[:, :w, :].copy()
        
        mask_roi = m_arr[y1:y2, x1:x2].astype(np.float32) / 255.0
        target_roi = arr[y1:y2, x1:x2].astype(np.float32)

        sy1, sy2 = y1 - dy, y2 - dy
        sx1, sx2 = x1 - dx, x2 - dx
        
        source_roi = np.zeros_like(target_roi)
        s_arr = np.empty((h, self._source_img.bytesPerLine() // 4, 4), dtype=np.uint8)
        ctypes.memmove(s_arr.ctypes.data, int(self._source_img.constBits()), self._source_img.sizeInBytes())
        s_arr = s_arr[:, :w, :].copy()
        
        sy_start, sy_end = max(0, sy1), min(h, sy2)
        sx_start, sx_end = max(0, sx1), min(w, sx2)
        ry_start, ry_end = sy_start - sy1, (sy_start - sy1) + (sy_end - sy_start)
        rx_start, rx_end = sx_start - sx1, (sx_start - sx1) + (sx_end - sx_start)
        if sy_start < sy_end and sx_start < sx_end:
            source_roi[ry_start:ry_end, rx_start:rx_end] = s_arr[sy_start:sy_end, sx_start:sx_end].astype(np.float32)

        mask_bin = mask_roi > 0.5
        up = np.roll(mask_bin, 1, axis=0); up[0, :] = False
        down = np.roll(mask_bin, -1, axis=0); down[-1, :] = False
        left = np.roll(mask_bin, 1, axis=1); left[:, 0] = False
        right = np.roll(mask_bin, -1, axis=1); right[:, -1] = False
        boundary = mask_bin & ~(mask_bin & up & down & left & right)

        if np.any(boundary):
            t_mean = np.mean(target_roi[boundary], axis=0)
            s_mean = np.mean(source_roi[boundary], axis=0)
            diff = t_mean - s_mean
            diff[3] = 0
            cloned = np.clip(source_roi + diff, 0, 255)
        else:
            cloned = source_roi

        smooth_mask_rgb = np.repeat(mask_roi[:, :, np.newaxis] * 255, 3, axis=2).astype(np.uint8)
        blur_r = max(1, min(x2-x1, y2-y1) // 5)
        for _ in range(3): smooth_mask_rgb = _box_blur_np(smooth_mask_rgb, blur_r)
        smooth_mask = smooth_mask_rgb[..., 0:1].astype(np.float32) / 255.0

        final_roi = target_roi.copy()
        op = self._current_opacity
        final_roi[..., :3] = target_roi[..., :3] * (1 - smooth_mask * op) + cloned[..., :3] * (smooth_mask * op)
        arr[y1:y2, x1:x2] = final_roi.astype(np.uint8)

        new_img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        out_arr = np.empty((h, new_img.bytesPerLine() // 4, 4), dtype=np.uint8)
        ctypes.memmove(out_arr.ctypes.data, int(layer.image.constBits()), layer.image.sizeInBytes())
        out_arr[:, :w, :] = arr
        ctypes.memmove(int(new_img.bits()), out_arr.ctypes.data, new_img.sizeInBytes())
        layer.image = new_img
        self._reset_stroke()

    def _reset_stroke(self):
        self._pts = []
        self._paint_offset = None
        self._source_img = None
        self._crosshair_pos = None

    def stroke_preview(self):
        if not self._pts or self._source_img is None: return None
        from PyQt6.QtGui import QRegion, QBitmap
        layer = self._target_layer
        w, h = layer.width(), layer.height()
        mask_img = QImage(w, h, QImage.Format.Format_Grayscale8)
        mask_img.fill(0)
        p = QPainter(mask_img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255), self._current_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        poly = QPolygonF([QPointF(pt - layer.offset) for pt in self._pts])
        p.drawPolyline(poly)
        p.end()

        preview = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        preview.fill(0)
        p2 = QPainter(preview)
        p2.setClipRegion(QRegion(QBitmap.fromImage(mask_img.createAlphaMask())))
        dx = int(self._paint_offset.x() - layer.offset.x() + self._source_offset.x())
        dy = int(self._paint_offset.y() - layer.offset.y() + self._source_offset.y())
        p2.drawImage(QPoint(-dx, -dy), self._source_img)
        p2.end()
        return (preview, layer.offset, self._current_opacity)

    def draw_overlays(self, painter, pw, doc):
        if self._crosshair_pos:
            cpos = self._crosshair_pos
            painter.setPen(QPen(QColor(0, 0, 0, 180), pw * 3))
            r = 6 * pw
            painter.drawLine(QPointF(cpos.x() - r, cpos.y()), QPointF(cpos.x() + r, cpos.y()))
            painter.drawLine(QPointF(cpos.x(), cpos.y() - r), QPointF(cpos.x(), cpos.y() + r))
            painter.setPen(QPen(QColor(255, 255, 255, 220), pw))
            painter.drawLine(QPointF(cpos.x() - r, cpos.y()), QPointF(cpos.x() + r, cpos.y()))
            painter.drawLine(QPointF(cpos.x(), cpos.y() - r), QPointF(cpos.x(), cpos.y() + r))

    def needs_history_push(self): return True
    def cursor(self): return Qt.CursorShape.CrossCursor