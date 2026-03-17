import math
import numpy as np

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import (QPainter, QColor, QLinearGradient,
                         QRadialGradient, QBrush, QGradient)
from tools.base_tool import BaseTool


class GradientTool(BaseTool):
    name     = "Gradient"
    icon     = "🌈"
    shortcut = "G"

    def __init__(self):
        self._start:    QPoint | None = None
        self._end:      QPoint | None = None
        self._dragging: bool          = False

    def on_press(self, pos, doc, fg, bg, opts):
        self._start    = pos
        self._end      = pos
        self._dragging = True

    def on_move(self, pos, doc, fg, bg, opts):
        self._end = pos

    def preview_gradient(self):
        if self._dragging and self._start is not None:
            return self._start, self._end
        return None

    def on_release(self, pos, doc, fg, bg, opts):
        self._dragging = False
        if self._start is None:
            return
        layer = doc.get_active_layer()
        if not layer or layer.locked:
            self._start = None
            return

        sx, sy = self._start.x() - layer.offset.x(), self._start.y() - layer.offset.y()
        ex, ey = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()
        if sx == ex and sy == ey:
            self._start = None
            return

        gtype   = opts.get("gradient_type",    "linear")
        opacity = float(opts.get("gradient_opacity", 100)) / 100
        reverse = bool(opts.get("gradient_reverse",  False))

        # Получаем список точек градиента. Если мы еще ни разу не открывали
        # редактор, берем дефолтные текущие цвета (от fg до bg)
        stops = opts.get("gradient_stops", [(0.0, fg), (1.0, bg)])

        if reverse:
            # Инвертируем позиции и порядок: точка на 0.1 станет 0.9 и т.д.
            stops = [(1.0 - pos, color) for pos, color in reversed(stops)]
            
        if getattr(layer, "editing_mask", False) and getattr(layer, "mask", None) is not None:
            target_img = layer.mask
            lock_a = False
        else:
            target_img = layer.image
            lock_a = getattr(layer, "lock_alpha", False)
            
        if lock_a:
            w, h = target_img.width(), target_img.height()
            ptr = target_img.bits()
            ptr.setsize(target_img.sizeInBytes())
            arr = np.ndarray((h, w, 4), dtype=np.uint8, buffer=ptr)
            orig_alpha = arr[..., 3].copy()

        painter = QPainter(target_img)
        painter.setOpacity(opacity)
        if doc.selection and not doc.selection.isEmpty():
            painter.setClipPath(doc.selection.translated(-layer.offset.x(), -layer.offset.y()))

        self._apply_gradient(painter, gtype,
                             target_img.width(), target_img.height(),
                             sx, sy, ex, ey, stops)
        painter.end()
        
        if lock_a:
            new_alpha = arr[..., 3].astype(np.float32)
            new_alpha[new_alpha == 0] = 1.0 
            ratio = orig_alpha.astype(np.float32) / new_alpha
            arr[..., 0] = np.clip(arr[..., 0] * ratio, 0, 255).astype(np.uint8)
            arr[..., 1] = np.clip(arr[..., 1] * ratio, 0, 255).astype(np.uint8)
            arr[..., 2] = np.clip(arr[..., 2] * ratio, 0, 255).astype(np.uint8)
            arr[..., 3] = orig_alpha
            
        self._start = None

    @staticmethod
    def _apply_gradient(painter: QPainter, gtype: str,
                        w: int, h: int,
                        sx: int, sy: int, ex: int, ey: int,
                        stops: list):
        rect = QRectF(0, 0, w, h)

        if gtype == "radial":
            r    = math.hypot(ex - sx, ey - sy)
            grad = QRadialGradient(QPointF(sx, sy), max(r, 1))
        else:  # linear
            grad = QLinearGradient(QPointF(sx, sy), QPointF(ex, ey))

        # Применяем все цветовые точки из списка
        for pos, color in stops:
            grad.setColorAt(pos, color)

        grad.setSpread(QGradient.Spread.PadSpread)

        painter.fillRect(rect, QBrush(grad))

    def cursor(self):
        return Qt.CursorShape.CrossCursor
