from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QPainterPath
from tools.base_tool import BaseTool


class SelectTool(BaseTool):
    """
    Прямоугольное выделение:
      • Drag вне выделения      → новое выделение
      • Ctrl+drag               → добавить к выделению (union)
      • Alt+drag                → вычесть из выделения (subtract)
      • Ctrl+Alt+drag            → пересечь (intersect)
      • Drag ВНУТРИ выделения   → переместить контур выделения
    """
    name = "Select"
    icon = "⬜"
    shortcut = "M"

    def __init__(self):
        self._start:            QPoint       | None = None
        self._drag_end:         QPoint       | None = None
        self._mode:             str                 = "new"
        self._move_origin:      QPoint       | None = None
        self._move_origin_path: QPainterPath | None = None
        self._drag_base_path:   QPainterPath | None = None

    @staticmethod
    def _path_from_rect(r: QRect) -> QPainterPath:
        p = QPainterPath()
        p.addRect(QRectF(r))
        return p

    @staticmethod
    def _rect_from_drag(start: QPoint, end: QPoint, *, constrain_square: bool) -> QRect:
        if not constrain_square:
            return QRect(start, end).normalized()
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        side = max(abs(dx), abs(dy))
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        return QRect(start, QPoint(start.x() + sx * side, start.y() + sy * side)).normalized()

    def on_press(self, pos, doc, fg, bg, opts):
        sel     = doc.selection
        ctrl    = bool(opts.get("_ctrl",  False))
        alt     = bool(opts.get("_alt",   False))
        has_sel = sel and not sel.isEmpty()

        if has_sel and sel.contains(QPointF(pos)):
            self._mode             = "move"
            self._move_origin      = pos
            self._move_origin_path = QPainterPath(sel)
            return

        if ctrl and alt and has_sel:
            self._mode           = "intersect"
            self._drag_base_path = QPainterPath(sel)
        elif ctrl and has_sel:
            self._mode           = "add"
            self._drag_base_path = QPainterPath(sel)
        elif alt and has_sel:
            self._mode           = "sub"
            self._drag_base_path = QPainterPath(sel)
        else:
            self._mode           = "new"
            self._drag_base_path = None
            doc.selection        = QPainterPath()
        self._start    = pos
        self._drag_end = pos

    def on_move(self, pos, doc, fg, bg, opts):
        if self._mode == "move" and self._move_origin and self._move_origin_path:
            delta = pos - self._move_origin
            doc.selection = self._move_origin_path.translated(delta.x(), delta.y())
            return

        if self._start:
            self._drag_end = pos
            constrain = self._mode != "move" and bool(opts.get("_shift", False))
            drag_path = self._path_from_rect(self._rect_from_drag(self._start, pos, constrain_square=constrain))
            if self._mode == "add" and self._drag_base_path:
                doc.selection = self._drag_base_path.united(drag_path)
            elif self._mode == "sub" and self._drag_base_path:
                doc.selection = self._drag_base_path.subtracted(drag_path)
            elif self._mode == "intersect" and self._drag_base_path:
                doc.selection = self._drag_base_path.intersected(drag_path)
            else:
                doc.selection = drag_path

    def on_release(self, pos, doc, fg, bg, opts):
        self._start = self._drag_end = None
        self._move_origin = self._move_origin_path = None
        self._drag_base_path = None
        self._mode = "new"

    def sub_drag_rect(self) -> QRect | None:
        if self._mode == "sub" and self._start and self._drag_end:
            return QRect(self._start, self._drag_end).normalized()
        return None

    def needs_history_push(self) -> bool:
        return True

    def cursor(self):
        return Qt.CursorShape.CrossCursor


class EllipticalSelectTool(BaseTool):
    """
    Эллиптическое выделение (аналог Elliptical Marquee):
      • Drag вне выделения      → новое выделение
      • Ctrl+drag               → добавить к выделению (union)
      • Alt+drag                → вычесть из выделения (subtract)
      • Ctrl+Alt+drag            → пересечь (intersect)
      • Drag ВНУТРИ выделения   → переместить контур выделения
    """
    name = "EllipseSelect"
    icon = "⭕"
    shortcut = ""

    def __init__(self):
        self._start:            QPoint       | None = None
        self._drag_end:         QPoint       | None = None
        self._mode:             str                 = "new"
        self._move_origin:      QPoint       | None = None
        self._move_origin_path: QPainterPath | None = None
        self._drag_base_path:   QPainterPath | None = None

    @staticmethod
    def _path_from_ellipse(r: QRect) -> QPainterPath:
        p = QPainterPath()
        p.addEllipse(QRectF(r))
        return p

    @staticmethod
    def _rect_from_drag(start: QPoint, end: QPoint, *, constrain_circle: bool) -> QRect:
        if not constrain_circle:
            return QRect(start, end).normalized()
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        side = max(abs(dx), abs(dy))
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        return QRect(start, QPoint(start.x() + sx * side, start.y() + sy * side)).normalized()

    def on_press(self, pos, doc, fg, bg, opts):
        sel     = doc.selection
        ctrl    = bool(opts.get("_ctrl",  False))
        alt     = bool(opts.get("_alt",   False))
        has_sel = sel and not sel.isEmpty()

        if has_sel and sel.contains(QPointF(pos)):
            self._mode             = "move"
            self._move_origin      = pos
            self._move_origin_path = QPainterPath(sel)
            return

        if ctrl and alt and has_sel:
            self._mode           = "intersect"
            self._drag_base_path = QPainterPath(sel)
        elif ctrl and has_sel:
            self._mode           = "add"
            self._drag_base_path = QPainterPath(sel)
        elif alt and has_sel:
            self._mode           = "sub"
            self._drag_base_path = QPainterPath(sel)
        else:
            self._mode           = "new"
            self._drag_base_path = None
            doc.selection        = QPainterPath()

        self._start    = pos
        self._drag_end = pos

    def on_move(self, pos, doc, fg, bg, opts):
        if self._mode == "move" and self._move_origin and self._move_origin_path:
            delta = pos - self._move_origin
            doc.selection = self._move_origin_path.translated(delta.x(), delta.y())
            return

        if self._start:
            self._drag_end = pos
            constrain = self._mode != "move" and bool(opts.get("_shift", False))
            drag_path = self._path_from_ellipse(self._rect_from_drag(self._start, pos, constrain_circle=constrain))
            if self._mode == "add" and self._drag_base_path:
                doc.selection = self._drag_base_path.united(drag_path)
            elif self._mode == "sub" and self._drag_base_path:
                doc.selection = self._drag_base_path.subtracted(drag_path)
            elif self._mode == "intersect" and self._drag_base_path:
                doc.selection = self._drag_base_path.intersected(drag_path)
            else:
                doc.selection = drag_path

    def on_release(self, pos, doc, fg, bg, opts):
        self._start = self._drag_end = None
        self._move_origin = self._move_origin_path = None
        self._drag_base_path = None
        self._mode = "new"

    def sub_drag_path(self) -> QPainterPath | None:
        if self._mode == "sub" and self._start and self._drag_end:
            r = QRect(self._start, self._drag_end).normalized()
            return self._path_from_ellipse(r)
        return None

    def needs_history_push(self) -> bool:
        return True

    def cursor(self):
        return Qt.CursorShape.CrossCursor
