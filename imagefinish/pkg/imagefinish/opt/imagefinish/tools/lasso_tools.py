import math
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QPainterPath, QPolygonF, QColor
from tools.base_tool import BaseTool

class LassoMixin:
    """Общая логика режимов выделения (Add, Subtract, Intersect)"""
    def _apply_path(self, doc, path: QPainterPath, opts: dict):
        sel = doc.selection
        ctrl = bool(opts.get("_ctrl", False))
        alt = bool(opts.get("_alt", False))

        if not sel or sel.isEmpty():
            doc.selection = path
            return

        base_path = QPainterPath(sel)
        if ctrl and alt:
            doc.selection = base_path.intersected(path)
        elif ctrl:
            doc.selection = base_path.united(path)
        elif alt:
            doc.selection = base_path.subtracted(path)
        else:
            doc.selection = path


class LassoTool(BaseTool, LassoMixin):
    name = "Lasso"
    icon = "➰"
    shortcut = "L"

    def __init__(self):
        self.points: list[QPointF] = []

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        self.points = [QPointF(pos)]

    def on_move(self, pos: QPoint, doc, fg, bg, opts):
        if self.points:
            self.points.append(QPointF(pos))

    def on_release(self, pos: QPoint, doc, fg, bg, opts):
        if len(self.points) > 2:
            path = QPainterPath()
            path.addPolygon(QPolygonF(self.points))
            path.closeSubpath()
            self._apply_path(doc, path, opts)
        self.points = []

    def needs_history_push(self) -> bool: return True
    def cursor(self): return Qt.CursorShape.CrossCursor
    def lasso_preview(self): return self.points


class PolygonalLassoTool(BaseTool, LassoMixin):
    name = "PolygonalLasso"
    icon = "⬡"
    shortcut = "L"

    def __init__(self):
        self.points: list[QPointF] = []
        self.current_pos: QPointF | None = None

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        # Завершение выделения по двойному клику (или если клик близко к началу)
        if self.points:
            start = self.points[0]
            dist = math.hypot(pos.x() - start.x(), pos.y() - start.y())
            if dist < 10:  # Замыкаем, если кликнули рядом с первой точкой
                self._commit(doc, opts)
                return

        self.points.append(QPointF(pos))
        self.current_pos = QPointF(pos)

    def on_move(self, pos: QPoint, doc, fg, bg, opts):
        if self.points:
            self.current_pos = QPointF(pos)

    def on_release(self, pos, doc, fg, bg, opts):
        pass # Полигональное лассо работает по кликам, а не по drag & drop

    def _commit(self, doc, opts):
        if len(self.points) > 2:
            path = QPainterPath()
            path.addPolygon(QPolygonF(self.points))
            path.closeSubpath()
            self._apply_path(doc, path, opts)
        self.points = []
        self.current_pos = None

    def needs_history_push(self) -> bool: return True
    def cursor(self): return Qt.CursorShape.CrossCursor
    def lasso_preview(self): return self.points, self.current_pos


class MagneticLassoTool(PolygonalLassoTool):
    name = "MagneticLasso"
    icon = "🧲"
    shortcut = "L"

    def __init__(self):
        super().__init__()
        self._last_width = 10

    def on_move(self, pos: QPoint, doc, fg, bg, opts):
        width = opts.get("mag_width", 10)
        self._last_width = width
        contrast = opts.get("mag_contrast", 10)
        freq = opts.get("mag_freq", 57)

        layer = doc.get_active_layer()
        if not layer or layer.image.isNull():
            self.current_pos = QPointF(pos)
            return

        snap_pos = pos

        img = layer.image
        w, h = img.width(), img.height()
        r = width
        min_x, max_x = max(0, pos.x() - r), min(w, pos.x() + r + 1)
        min_y, max_y = max(0, pos.y() - r), min(h, pos.y() + r + 1)

        if min_x < max_x and min_y < max_y:
            import ctypes
            import numpy as np
            ptr = img.constBits()
            buf = (ctypes.c_uint8 * img.sizeInBytes()).from_address(int(ptr))
            arr = np.ndarray((h, img.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
            roi = arr[min_y:max_y, min_x:max_x]

            gray = 0.299 * roi[..., 2] + 0.587 * roi[..., 1] + 0.114 * roi[..., 0]
            alpha_mask = (roi[..., 3] > 0).astype(np.float32)

            if gray.shape[0] >= 3 and gray.shape[1] >= 3:
                dy, dx = np.gradient(gray)
                grad_mag = np.hypot(dx, dy) * alpha_mask

                max_idx = np.unravel_index(np.argmax(grad_mag), grad_mag.shape)
                max_val = grad_mag[max_idx]

                threshold = (contrast / 100.0) * 128.0
                if max_val >= threshold and roi[max_idx[0], max_idx[1], 3] > 0:
                    snap_pos = QPoint(min_x + max_idx[1], min_y + max_idx[0])

        self.current_pos = QPointF(snap_pos)
        if not self.points: return

        last = self.points[-1]
        dist = math.hypot(snap_pos.x() - last.x(), snap_pos.y() - last.y())
        drop_dist = 100 - (freq / 100.0) * 95
        if dist > drop_dist:
            self.points.append(QPointF(snap_pos))

    def draw_overlays(self, painter, pw, doc):
        if self.current_pos:
            from PyQt6.QtGui import QPen
            r = self._last_width
            painter.setPen(QPen(QColor(0, 0, 0, 150), pw))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.current_pos, r, r)
