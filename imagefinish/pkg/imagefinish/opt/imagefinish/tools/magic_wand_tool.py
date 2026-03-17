import numpy as np
from PyQt6.QtCore import QPoint, Qt, QRect, QRectF
from PyQt6.QtGui import QImage, QBitmap, QRegion, QPainterPath, QColor
from tools.base_tool import BaseTool
from tools.lasso_tools import LassoMixin


class MagicWandTool(BaseTool, LassoMixin):
    name = "MagicWand"
    icon = "🪄"
    shortcut = "W"

    def __init__(self):
        super().__init__()

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked or layer.image.isNull():
            return

        if getattr(layer, "editing_mask", False) and getattr(layer, "mask", None) is not None:
            img = layer.mask
        else:
            img = layer.image
            
        w, h = img.width(), img.height()
        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()

        if not (0 <= cx < w and 0 <= cy < h):
            return

        target_px = img.pixel(cx, cy)
        if (target_px >> 24) & 0xFF == 0:
            return

        tr = (target_px >> 16) & 0xFF
        tg = (target_px >> 8) & 0xFF
        tb = target_px & 0xFF

        tolerance_pct = opts.get("fill_tolerance", 32)
        max_dist_sq = 255**2 * 3
        tolerance_sq = (tolerance_pct / 100.0)**2 * max_dist_sq
        contiguous = bool(opts.get("fill_contiguous", True))

        # 1. Читаем оригинальное изображение
        import ctypes
        ptr = img.constBits()
        buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
        bpl = img.bytesPerLine()
        arr = np.ndarray((h, bpl // 4, 4), dtype=np.uint8, buffer=buf)[:, :w, :]

        B = arr[..., 0].astype(np.int32)
        G = arr[..., 1].astype(np.int32)
        R = arr[..., 2].astype(np.int32)
        A = arr[..., 3]

        dist_sq = (R - tr)**2 + (G - tg)**2 + (B - tb)**2
        color_mask = (dist_sq <= tolerance_sq) & (A > 0)

        if not color_mask[cy, cx]:
            return

        if contiguous:
            # 2. Создаем чистую логическую маску для Flood Fill
            visited = np.zeros((h, w), dtype=bool)
            # 3. АЛГОРИТМ FLOOD FILL
            stack = [(cy, cx)]
            visited[cy, cx] = True
            color_mask[cy, cx] = False

            while stack:
                y, x = stack.pop()

                if y > 0 and color_mask[y - 1, x]:
                    visited[y - 1, x] = True; color_mask[y - 1, x] = False; stack.append((y - 1, x))
                if y < h - 1 and color_mask[y + 1, x]:
                    visited[y + 1, x] = True; color_mask[y + 1, x] = False; stack.append((y + 1, x))
                if x > 0 and color_mask[y, x - 1]:
                    visited[y, x - 1] = True; color_mask[y, x - 1] = False; stack.append((y, x - 1))
                if x < w - 1 and color_mask[y, x + 1]:
                    visited[y, x + 1] = True; color_mask[y, x + 1] = False; stack.append((y, x + 1))
        else:
            visited = color_mask.copy()
            visited[cy, cx] = True

        # 4. Собираем маску выделения через Альфа-канал
        mask_img = QImage(w, h, QImage.Format.Format_RGBA8888)
        mask_img.fill(0)
        m_ptr = mask_img.bits()
        m_buf = (ctypes.c_uint8 * mask_img.sizeInBytes()).from_address(int(m_ptr))
        np.ndarray((h, w, 4), dtype=np.uint8, buffer=m_buf)[visited, 3] = 255

        # Строим Битмап строго по Альфа-каналу (никакой инверсии цветов!)
        bitmap = QBitmap.fromImage(mask_img.createAlphaMask())

        # 5. Превращаем в регион и ОБЯЗАТЕЛЬНО УПРОЩАЕМ ПУТЬ
        region = QRegion(bitmap)
        path = QPainterPath()
        path.addRegion(region)

        # ГЛАВНАЯ МАГИЯ: Сливаем тысячи прямоугольников в один гладкий контур
        path = path.simplified()
        path.translate(layer.offset.x(), layer.offset.y())

        self._apply_path(doc, path, opts)



    def on_move(self, pos, doc, fg, bg, opts): pass
    def on_release(self, pos, doc, fg, bg, opts): pass

    def needs_history_push(self) -> bool:
        return True

    def cursor(self):
        return Qt.CursorShape.CrossCursor


class QuickSelectionTool(BaseTool, LassoMixin):
    name = "QuickSelection"
    icon = "🖌️✨"
    shortcut = "W"

    def __init__(self):
        super().__init__()
        self._dragging = False
        self._mask = None
        self._target_img = None

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked or layer.image.isNull():
            return
        
        self._dragging = True
        if getattr(layer, "editing_mask", False) and getattr(layer, "mask", None) is not None:
            self._target_img = layer.mask
        else:
            self._target_img = layer.image

        w, h = self._target_img.width(), self._target_img.height()
        self._mask = np.zeros((h, w), dtype=bool)
        self._process_brush(pos, opts)

    def on_move(self, pos: QPoint, doc, fg, bg, opts):
        if self._dragging:
            self._process_brush(pos, opts)

    def on_release(self, pos: QPoint, doc, fg, bg, opts):
        if not self._dragging: return
        self._dragging = False

        if self._mask is not None and np.any(self._mask):
            h, w = self._mask.shape
            mask_img = QImage(w, h, QImage.Format.Format_RGBA8888)
            mask_img.fill(0)
            m_ptr = mask_img.bits()
            m_buf = (ctypes.c_uint8 * mask_img.sizeInBytes()).from_address(int(m_ptr))
            np.ndarray((h, w, 4), dtype=np.uint8, buffer=m_buf)[self._mask, 3] = 255
            path = QPainterPath()
            path.addRegion(QRegion(QBitmap.fromImage(mask_img.createAlphaMask())))
            path.translate(self._target_layer.offset.x(), self._target_layer.offset.y())
            self._apply_path(doc, path.simplified(), opts)

        self._mask = None
        self._target_img = None

    def _process_brush(self, pos, opts):
        if self._target_img is None or self._mask is None: return

        cx, cy = pos.x() - self._target_layer.offset.x(), pos.y() - self._target_layer.offset.y()
        w, h = self._target_img.width(), self._target_img.height()
        if not (0 <= cx < w and 0 <= cy < h): return

        target_px = self._target_img.pixel(cx, cy)
        if (target_px >> 24) & 0xFF == 0: return

        tr, tg, tb = (target_px >> 16) & 0xFF, (target_px >> 8) & 0xFF, target_px & 0xFF

        # Кисть локально расширяется на радиус (brush_size * 1.5)
        brush_size = max(1, opts.get("brush_size", 20))
        radius = int(brush_size * 1.5)
        tolerance = opts.get("fill_tolerance", 32)
        tol_sq = (tolerance / 100.0 * 255)**2 * 3

        min_x, max_x = max(0, cx - radius), min(w, cx + radius + 1)
        min_y, max_y = max(0, cy - radius), min(h, cy + radius + 1)

        ptr = self._target_img.bits()
        ptr.setsize(self._target_img.sizeInBytes())
        arr_full = np.ndarray((h, self._target_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=ptr)
        roi = arr_full[min_y:max_y, min_x:max_x]

        dist_sq = (roi[..., 2].astype(np.int32) - tr)**2 + \
                  (roi[..., 1].astype(np.int32) - tg)**2 + \
                  (roi[..., 0].astype(np.int32) - tb)**2

        local_mask = (dist_sq <= tol_sq) & (roi[..., 3] > 0)
        Y, X = np.ogrid[min_y - cy : max_y - cy, min_x - cx : max_x - cx]
        local_mask &= ((X**2 + Y**2) <= radius**2)

        self._mask[min_y:max_y, min_x:max_x] |= local_mask

    def stroke_preview(self):
        # Отрисовка живого синего превью на холсте
        if self._mask is not None:
            h, w = self._mask.shape
            img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(0)
            m_ptr = img.bits()
            m_buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(m_ptr))
            np.ndarray((h, w, 4), dtype=np.uint8, buffer=m_buf)[self._mask] = [250, 150, 50, 100]
            return (img, self._target_layer.offset, 1.0)
        return None

    def needs_history_push(self): return True
    def cursor(self): return Qt.CursorShape.CrossCursor


class ObjectSelectionTool(BaseTool, LassoMixin):
    name = "ObjectSelection"
    icon = "📦"
    shortcut = "W"

    def __init__(self):
        super().__init__()
        self._start = None
        self._end = None
        self._dragging = False

    def on_press(self, pos, doc, fg, bg, opts):
        self._start = pos
        self._end = pos
        self._dragging = True

    def on_move(self, pos, doc, fg, bg, opts):
        if self._dragging:
            self._end = pos

    def on_release(self, pos, doc, fg, bg, opts):
        if not self._dragging: return
        self._dragging = False
        self._end = pos

        layer = doc.get_active_layer()
        if not layer or layer.locked or layer.image.isNull():
            self._start = None
            return

        target_img = layer.mask if (getattr(layer, "editing_mask", False) and getattr(layer, "mask", None) is not None) else layer.image

        doc_rect = QRect(self._start, self._end).normalized()
        w, h = target_img.width(), target_img.height()
        rect = doc_rect.translated(-layer.offset).intersected(QRect(0, 0, w, h))

        if rect.width() < 10 or rect.height() < 10:
            self._start = None
            return

        min_x, max_x, min_y, max_y = rect.left(), rect.right(), rect.top(), rect.bottom()
        
        import ctypes
        ptr = target_img.constBits()
        buf = (ctypes.c_uint8 * target_img.sizeInBytes()).from_address(int(ptr))
        arr_full = np.ndarray((h, target_img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
        roi = arr_full[min_y:max_y+1, min_x:max_x+1]

        # Эвристика: извлекаем центр 40%
        roi_h, roi_w = roi.shape[:2]
        cw, ch = int(roi_w * 0.4), int(roi_h * 0.4)
        c_x1, c_y1 = (roi_w - cw) // 2, (roi_h - ch) // 2
        center_roi = roi[c_y1:c_y1+ch, c_x1:c_x1+cw]
        
        if center_roi.size > 0:
            avg_b, avg_g, avg_r = np.median(center_roi[..., 0]), np.median(center_roi[..., 1]), np.median(center_roi[..., 2])
        else:
            avg_b, avg_g, avg_r = roi[roi_h//2, roi_w//2, :3]

        dist_sq = (roi[..., 2].astype(np.int32) - avg_r)**2 + \
                  (roi[..., 1].astype(np.int32) - avg_g)**2 + \
                  (roi[..., 0].astype(np.int32) - avg_b)**2

        # Интеллектуальный допуск для отделения объекта от контрастного фона
        tolerance_sq = (50 / 100.0 * 255)**2 * 3
        local_mask = (dist_sq <= tolerance_sq) & (roi[..., 3] > 0)
        
        if np.any(local_mask):
            mask_img = QImage(w, h, QImage.Format.Format_RGBA8888)
            mask_img.fill(0)
            m_ptr = mask_img.bits()
            m_buf = (ctypes.c_uint8 * mask_img.sizeInBytes()).from_address(int(m_ptr))
            np.ndarray((h, w, 4), dtype=np.uint8, buffer=m_buf)[min_y:max_y+1, min_x:max_x+1, 3][local_mask] = 255
            path = QPainterPath()
            path.addRegion(QRegion(QBitmap.fromImage(mask_img.createAlphaMask())))
            path.translate(layer.offset.x(), layer.offset.y())
            self._apply_path(doc, path.simplified(), opts)

        self._start = None

    def sub_drag_path(self):
        if self._dragging and self._start and self._end:
            p = QPainterPath()
            p.addRect(QRectF(QRect(self._start, self._end).normalized()))
            return p
        return None

    def needs_history_push(self): return True
    def cursor(self): return Qt.CursorShape.CrossCursor
