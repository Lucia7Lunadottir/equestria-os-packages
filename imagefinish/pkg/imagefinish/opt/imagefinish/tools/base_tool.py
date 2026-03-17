from abc import ABC, abstractmethod
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor


class BaseTool(ABC):
    """
    Abstract base for all drawing / editing tools.
    Each tool receives document-space coordinates.
    """

    #: Short display name shown in the UI
    name: str = "Tool"
    #: Unicode icon / emoji for the toolbar button
    icon: str = "🔧"
    #: Keyboard shortcut letter (optional)
    shortcut: str = ""
    #: Tells CanvasWidget whether to trigger a heavy get_composite() during on_move
    modifies_canvas_on_move: bool = False

    def on_press(self, pos: QPoint, doc, fg: QColor, bg: QColor, opts: dict):
        """Called on mouse-button-down."""

    def on_move(self, pos: QPoint, doc, fg: QColor, bg: QColor, opts: dict):
        """Called on mouse-move while button held."""

    def on_release(self, pos: QPoint, doc, fg: QColor, bg: QColor, opts: dict):
        """Called on mouse-button-up."""

    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.CrossCursor

    def needs_history_push(self) -> bool:
        """Return True if this tool should snapshot history on press."""
        return True

    def __repr__(self) -> str:
        return f"<Tool:{self.name}>"
