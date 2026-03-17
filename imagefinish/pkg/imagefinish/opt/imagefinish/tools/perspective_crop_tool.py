from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QPolygon, QPainter, QPen

from tools.base_tool import BaseTool
import math


class PerspectiveCropTool(BaseTool):
    name = "Perspective Crop"
    icon = "📐"
    shortcut = "P"

    def __init__(self):
        self.points = []
        self.pending_quad = None
        self._dragged_point_index = -1
        self._threshold = 40


    def draw(self, painter: QPainter, doc, fg, bg, opts):
        if not self.points:
            return

        # Настройка пера для рисования рамки
        pen = QPen(QColor(255, 255, 255), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)

        # Рисуем линии между поставленными точками
        for i in range(len(self.points)):
            painter.drawEllipse(self.points[i], 4, 4) # Узлы
            if i > 0:
                painter.drawLine(self.points[i-1], self.points[i])

        # Замыкаем четырехугольник
        if len(self.points) == 4:
            painter.drawLine(self.points[3], self.points[0])
            # Можно закрасить область полупрозрачным цветом
            painter.setBrush(QColor(255, 255, 255, 30))
            painter.drawPolygon(QPolygon(self.points))


    def on_press(self, pos: QPoint, doc, fg: QColor, bg: QColor, opts: dict):
        if len(self.points) == 4:
            for i, p in enumerate(self.points):
                if self._dist_to_point(pos, p) < self._threshold:
                    self._dragged_point_index = i
                    return

        if len(self.points) < 4:
            self.points.append(pos)
            if len(self.points) == 4:
                self.pending_quad = QPolygon(self.points)

    def on_move(self, pos: QPoint, doc, fg: QColor, bg: QColor, opts: dict):
        if self._dragged_point_index != -1:
            self.points[self._dragged_point_index] = pos
            if len(self.points) == 4:
                self.pending_quad = QPolygon(self.points)

    def on_release(self, pos: QPoint, doc, fg: QColor, bg: QColor, opts: dict):
        self._dragged_point_index = -1

    def on_key_press(self, key, doc, fg, bg, opts):
        if key == Qt.Key.Key_Escape:
            self.points = []
            self.pending_quad = None

    def needs_history_push(self) -> bool:
        return False

    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    def _dist_to_point(self, p1: QPoint, p2: QPoint) -> float:
        return math.sqrt((p1.x() - p2.x())**2 + (p1.y() - p2.y())**2)
