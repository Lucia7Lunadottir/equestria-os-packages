from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from tools.base_tool import BaseTool


class EyedropperTool(BaseTool):
    name = "Eyedropper"
    icon = "💉"
    shortcut = "I"

    color_picked_callback = None

    def on_press(self, pos, doc, fg, bg, opts):
        composite = doc.get_composite()
        x, y = pos.x(), pos.y()
        if 0 <= x < composite.width() and 0 <= y < composite.height():
            picked = QColor(composite.pixel(x, y))
            picked.setAlpha(255)
            if callable(self.color_picked_callback):
                self.color_picked_callback(picked)

    def needs_history_push(self):
        return False

    def cursor(self):
        return Qt.CursorShape.CrossCursor
