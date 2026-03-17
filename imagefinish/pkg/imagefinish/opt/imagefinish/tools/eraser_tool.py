from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtCore import QPoint, Qt
from tools.base_tool import BaseTool


class EraserTool(BaseTool):
    name = "Eraser"
    icon = "🧹"
    shortcut = "E"

    def __init__(self):
        self._last_pos: QPoint | None = None

    def on_press(self, pos, doc, fg, bg, opts):
        self._last_pos = pos
        self._erase(pos, pos, doc, opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if self._last_pos:
            self._erase(self._last_pos, pos, doc, opts)
        self._last_pos = pos

    def on_release(self, pos, doc, fg, bg, opts):
        self._last_pos = None

    def _erase(self, p1: QPoint, p2: QPoint, doc, opts: dict):
        layer = doc.get_active_layer()
        if not layer or layer.locked:
            return

        size = max(1, int(opts.get("brush_size", 20)))

        painter = QPainter(layer.image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)

        if doc.selection and not doc.selection.isEmpty():
            painter.setClipPath(doc.selection.translated(-layer.offset.x(), -layer.offset.y()))

        pen = QPen(Qt.GlobalColor.transparent, size,
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(p1 - layer.offset, p2 - layer.offset)
        painter.end()
