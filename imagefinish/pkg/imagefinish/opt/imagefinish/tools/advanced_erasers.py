import math
import numpy as np
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, qRed, qGreen, qBlue, qAlpha, QImage
from tools.base_tool import BaseTool



class MagicEraserTool(BaseTool):
    name = "MagicEraser"
    icon = "🎇"
    shortcut = "E"

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked or layer.image.isNull() or getattr(layer, "lock_pixels", False):
            return
            
        if getattr(layer, "lock_alpha", False):
            return
            
        if getattr(layer, "editing_mask", False):
            return

        img = layer.image
        w, h = img.width(), img.height()
        sx, sy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()

        if not (0 <= sx < w and 0 <= sy < h):
            return

        target_pixel = img.pixel(sx, sy)
        if qAlpha(target_pixel) == 0:
            return  # Кликнули по пустой области

        # Подготавливаем цвета для быстрого сравнения
        tr, tg, tb = qRed(target_pixel), qGreen(target_pixel), qBlue(target_pixel)

        tolerance_pct = opts.get("fill_tolerance", 32)
        max_dist_sq = 255**2 * 3
        tolerance_sq = (tolerance_pct / 100.0)**2 * max_dist_sq
        contiguous = bool(opts.get("fill_contiguous", True))

        # --- NUMPY ОПТИМИЗАЦИЯ ---
        import ctypes
        bpl = img.bytesPerLine()
        arr_full = np.empty((h, bpl // 4, 4), dtype=np.uint8)
        ctypes.memmove(arr_full.ctypes.data, int(img.constBits()), img.sizeInBytes())
        arr = arr_full[:, :w, :]

        # Векторно считаем маску совпадения цвета
        B = arr[..., 0].astype(np.int32)
        G = arr[..., 1].astype(np.int32)
        R = arr[..., 2].astype(np.int32)
        A = arr[..., 3]

        dist_sq = (R - tr)**2 + (G - tg)**2 + (B - tb)**2
        color_mask = (dist_sq <= tolerance_sq) & (A > 0)

        if not color_mask[sy, sx]:
            return

        if contiguous:
            # Быстрый Flood Fill по логической маске вместо медленного img.pixel()
            visited = np.zeros((h, w), dtype=bool)
            stack = [(sy, sx)]
            visited[sy, sx] = True
            color_mask[sy, sx] = False

            while stack:
                y, x = stack.pop()

                if y > 0 and color_mask[y - 1, x]: visited[y - 1, x] = True; color_mask[y - 1, x] = False; stack.append((y - 1, x))
                if y < h - 1 and color_mask[y + 1, x]: visited[y + 1, x] = True; color_mask[y + 1, x] = False; stack.append((y + 1, x))
                if x > 0 and color_mask[y, x - 1]: visited[y, x - 1] = True; color_mask[y, x - 1] = False; stack.append((y, x - 1))
                if x < w - 1 and color_mask[y, x + 1]: visited[y, x + 1] = True; color_mask[y, x + 1] = False; stack.append((y, x + 1))
        else:
            visited = color_mask.copy()
            visited[sy, sx] = True

        # Мгновенно очищаем все найденные пиксели махом
        arr[visited] = 0
        ctypes.memmove(int(img.bits()), arr_full.ctypes.data, img.sizeInBytes())

    def on_move(self, pos, doc, fg, bg, opts): pass
    def on_release(self, pos, doc, fg, bg, opts): pass
    def needs_history_push(self) -> bool: return True
    def cursor(self): return Qt.CursorShape.CrossCursor




class BackgroundEraserTool(BaseTool):
    name = "BackgroundEraser"
    icon = "✂️"
    shortcut = "E"
    modifies_canvas_on_move = True

    def __init__(self):
        super().__init__()
        self.sample_color = None
        self.last_paint_pos = None

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked or layer.image.isNull() or getattr(layer, "lock_pixels", False):
            self.sample_color = None
            return
            
        if getattr(layer, "lock_alpha", False):
            return
            
        if getattr(layer, "editing_mask", False):
            return

        img = layer.image
        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()

        if 0 <= cx < img.width() and 0 <= cy < img.height():
            px = img.pixel(cx, cy)
            if (px >> 24) & 0xFF > 0:
                self.sample_color = px
            else:
                self.sample_color = None

        if self.sample_color is not None:
            self.last_paint_pos = pos
            self._erase_background(pos, doc, opts)

    def on_move(self, pos: QPoint, doc, fg, bg, opts):
        if self.sample_color is None or not self.last_paint_pos:
            return

        radius = max(1, opts.get("brush_size", 20) / 2)
        spacing = max(1.0, radius * 0.15)

        dx = pos.x() - self.last_paint_pos.x()
        dy = pos.y() - self.last_paint_pos.y()
        dist = (dx**2 + dy**2)**0.5

        if dist < spacing:
            return

        # Интерполяция для резких рывков мыши
        steps = int(dist / spacing)
        if steps > 1:
            step_dx = dx / steps
            step_dy = dy / steps
            for i in range(1, steps):
                inter_pos = QPoint(int(self.last_paint_pos.x() + step_dx * i),
                                   int(self.last_paint_pos.y() + step_dy * i))
                self._erase_background(inter_pos, doc, opts)

        self._erase_background(pos, doc, opts)
        self.last_paint_pos = pos

    def on_release(self, pos, doc, fg, bg, opts):
        self.sample_color = None
        self.last_paint_pos = None

    def _erase_background(self, pos: QPoint, doc, opts):
        layer = doc.get_active_layer()
        img = layer.image
        w, h = img.width(), img.height()
        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()

        radius = int(opts.get("brush_size", 20) / 2)
        tolerance_pct = opts.get("fill_tolerance", 32)

        min_x, max_x = max(0, cx - radius), min(w, cx + radius + 1)
        min_y, max_y = max(0, cy - radius), min(h, cy + radius + 1)

        if min_x >= max_x or min_y >= max_y:
            return

        sc = self.sample_color
        sr = (sc >> 16) & 0xFF
        sg = (sc >> 8) & 0xFF
        sb = sc & 0xFF

        # --- NUMPY МАГИЯ НАЧИНАЕТСЯ ЗДЕСЬ ---
        import ctypes
        bpl = img.bytesPerLine()
        arr_full = np.empty((h, bpl // 4, 4), dtype=np.uint8)
        ctypes.memmove(arr_full.ctypes.data, int(img.constBits()), img.sizeInBytes())
        arr = arr_full[:, :w, :]
        
        roi = arr[min_y:max_y, min_x:max_x]
        Y, X = np.ogrid[min_y - cy : max_y - cy, min_x - cx : max_x - cx]
        circle_mask = (X**2 + Y**2) <= radius**2
        
        roi_B = roi[..., 0].astype(np.int32)
        roi_G = roi[..., 1].astype(np.int32)
        roi_R = roi[..., 2].astype(np.int32)
        roi_A = roi[..., 3]
        
        color_dist_sq = (roi_R - sr)**2 + (roi_G - sg)**2 + (roi_B - sb)**2
        tolerance_sq = (tolerance_pct / 100.0)**2 * (255**2 * 3)
        
        final_mask = circle_mask & (roi_A > 0) & (color_dist_sq <= tolerance_sq)
        roi[final_mask] = 0
        
        ctypes.memmove(int(img.bits()), arr_full.ctypes.data, img.sizeInBytes())

    def needs_history_push(self) -> bool: return True
    def cursor(self): return Qt.CursorShape.CrossCursor
