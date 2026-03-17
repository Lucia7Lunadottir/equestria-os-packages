from dataclasses import dataclass, field
from core.layer import Layer
from PyQt6.QtGui import QPainterPath
from PyQt6.QtCore import QPointF


def clone_work_path(wp: dict | None) -> dict:
    if not wp: return {"nodes": [], "closed": False}
    nodes = []
    for n in wp.get("nodes", []):
        nodes.append({
            "p": QPointF(n["p"]),
            "c1": QPointF(n["c1"]),
            "c2": QPointF(n["c2"])
        })
    return {"nodes": nodes, "closed": wp.get("closed", False)}


@dataclass
class HistoryState:
    description: str
    layers_snapshot: list[Layer]
    active_layer_index: int
    doc_width:  int = 0
    doc_height: int = 0
    selection_snapshot: QPainterPath | None = None
    work_path_snapshot: dict | None = None
    alpha_channels_snapshot: list[dict] | None = None
    color_mode_snapshot: str = "RGB"
    bit_depth_snapshot: int = 8


class HistoryManager:
    """
    Command-pattern history for undo / redo.
    Stores full layer snapshots (simple & reliable).
    Max states prevents unbounded memory use.
    """

    def __init__(self, max_states: int = 40):
        self.max_states = max_states
        self._undo_stack: list[HistoryState] = []
        self._redo_stack: list[HistoryState] = []

    # ---------------------------------------------------------------- Push
    def push(self, state: HistoryState):
        self._undo_stack.append(state)
        if len(self._undo_stack) > self.max_states:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    # --------------------------------------------------------------- Undo/Redo
    def undo(self) -> HistoryState | None:
        if self._undo_stack:
            return self._undo_stack.pop()
        return None

    def redo(self) -> HistoryState | None:
        if self._redo_stack:
            return self._redo_stack.pop()
        return None

    def save_for_redo(self, state: HistoryState):
        self._redo_stack.append(state)

    # ---------------------------------------------------------------- Queries
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo_description(self) -> str:
        return self._undo_stack[-1].description if self._undo_stack else ""

    def redo_description(self) -> str:
        return self._redo_stack[-1].description if self._redo_stack else ""

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
