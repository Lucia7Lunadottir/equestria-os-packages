from PyQt6.QtCore import QPoint, Qt, QRect
from PyQt6.QtGui import QPainter, QPen, QColor
from tools.base_tool import BaseTool

class SliceTool(BaseTool):
    name = "Slice"
    icon = "🔪"
    shortcut = "C"

    def __init__(self):
        super().__init__()
        self._start = None
        self._end = None

    def on_press(self, pos, doc, fg, bg, opts):
        self._start = pos
        self._end = pos

    def on_move(self, pos, doc, fg, bg, opts):
        if self._start:
            self._end = pos

    def on_release(self, pos, doc, fg, bg, opts):
        if self._start and self._end:
            r = QRect(self._start, self._end).normalized()
            if r.width() > 5 and r.height() > 5:
                if not hasattr(doc, "slices"): doc.slices = []
                doc.slices.append(r)
        self._start = None
        self._end = None

    def draw_overlays(self, painter, pw, doc):
        if self._start and self._end:
            r = QRect(self._start, self._end).normalized()
            painter.setPen(QPen(QColor(0, 150, 255), max(1.0, pw)))
            painter.setBrush(QColor(0, 150, 255, 40))
            painter.drawRect(r)

    def needs_history_push(self): return False
    def cursor(self): return Qt.CursorShape.CrossCursor