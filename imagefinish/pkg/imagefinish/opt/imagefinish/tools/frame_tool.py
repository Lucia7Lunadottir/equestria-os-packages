from PyQt6.QtCore import QPoint, QPointF, Qt, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor, QImage
from tools.base_tool import BaseTool

class FrameTool(BaseTool):
    name = "Frame"
    icon = "⛶"
    shortcut = "K"

    def __init__(self):
        super().__init__()
        self._start = None
        self._end = None
        self._shape = "rect"

    def on_press(self, pos, doc, fg, bg, opts):
        self._start = pos
        self._end = pos
        self._shape = opts.get("frame_shape", "rect")

    def on_move(self, pos, doc, fg, bg, opts):
        if self._start: self._end = pos

    def on_release(self, pos, doc, fg, bg, opts):
        if self._start and self._end:
            r = QRectF(QPointF(self._start), QPointF(self._end)).normalized()
            if r.width() > 10 and r.height() > 10:
                n = sum(1 for l in doc.layers if getattr(l, "layer_type", "") == "frame") + 1
                layer = doc.add_layer(f"Frame {n}")
                layer.layer_type = "frame"
                layer.frame_data = {"shape": self._shape, "rect": r}
                layer.offset = QPoint(0, 0)
                layer.image = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
                layer.image.fill(Qt.GlobalColor.transparent)
        self._start = self._end = None

    def draw_overlays(self, painter, pw, doc):
        if self._start and self._end:
            r = QRectF(QPointF(self._start), QPointF(self._end)).normalized()
            painter.setPen(QPen(QColor(150, 150, 150), max(1.0, pw * 2)))
            painter.setBrush(QColor(200, 200, 200, 100))
            painter.drawEllipse(r) if self._shape == "ellipse" else painter.drawRect(r)

    def needs_history_push(self): return True
    def cursor(self): return Qt.CursorShape.CrossCursor