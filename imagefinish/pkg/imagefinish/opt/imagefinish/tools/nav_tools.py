from PyQt6.QtCore import Qt
from tools.base_tool import BaseTool


class HandTool(BaseTool):
    name     = "Hand"
    icon     = "🖐"
    shortcut = "H"

    def needs_history_push(self) -> bool:
        return False

    def cursor(self):
        return Qt.CursorShape.OpenHandCursor


class ZoomTool(BaseTool):
    name     = "Zoom"
    icon     = "🔍"
    shortcut = "Z"

    def needs_history_push(self) -> bool:
        return False

    def cursor(self):
        return Qt.CursorShape.CrossCursor


class RotateViewTool(BaseTool):
    name     = "RotateView"
    icon     = "🔄"
    shortcut = ""

    def needs_history_push(self) -> bool:
        return False

    def cursor(self):
        return Qt.CursorShape.CrossCursor
