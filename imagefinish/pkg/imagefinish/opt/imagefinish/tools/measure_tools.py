import math
from PyQt6.QtCore import QPoint, Qt
from tools.base_tool import BaseTool


class ColorSamplerTool(BaseTool):
    name = "ColorSampler"
    icon = "🎯"
    shortcut = "I"

    def __init__(self):
        super().__init__()
        self.markers = []

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        if opts.get("_alt", False):
            if not self.markers: return
            dists = [((p.x()-pos.x())**2 + (p.y()-pos.y())**2, p) for p in self.markers]
            dists.sort()
            if dists[0][0] < 100:  # Удаляем, если кликнули рядом (в пределах 10 пкс)
                self.markers.remove(dists[0][1])
        else:
            if len(self.markers) < 10:
                self.markers.append(pos)

    def on_move(self, pos, doc, fg, bg, opts): pass
    def on_release(self, pos, doc, fg, bg, opts): pass
    def cursor(self): return Qt.CursorShape.CrossCursor


class RulerTool(BaseTool):
    name = "Ruler"
    icon = "📏"
    shortcut = "I"

    def __init__(self):
        super().__init__()
        self.lines = []
        self._start = None
        self._end = None
        self._dragging = False

    def on_press(self, pos: QPoint, doc, fg, bg, opts):
        if opts.get("_alt", False):
            if not self.lines: return
            best_dist = float('inf')
            best_idx = -1
            for i, (p1, p2) in enumerate(self.lines):
                d1 = (p1.x() - pos.x())**2 + (p1.y() - pos.y())**2
                d2 = (p2.x() - pos.x())**2 + (p2.y() - pos.y())**2
                if min(d1, d2) < best_dist:
                    best_dist = min(d1, d2)
                    best_idx = i
            if best_dist < 100:  # Удаляем линейку, если кликнули рядом с её точкой (10 пкс)
                self.lines.pop(best_idx)
                return
                
        self._start = pos; self._end = pos; self._dragging = True

    def on_move(self, pos, doc, fg, bg, opts):
        if self._dragging:
            if opts.get("_shift", False) and self._start:
                dx = pos.x() - self._start.x()
                dy = pos.y() - self._start.y()
                angle = math.atan2(dy, dx)
                # Округляем угол до ближайших 45 градусов (pi / 4)
                snapped_angle = round(angle / (math.pi / 4)) * (math.pi / 4)
                dist = math.hypot(dx, dy)
                self._end = QPoint(
                    int(self._start.x() + dist * math.cos(snapped_angle)),
                    int(self._start.y() + dist * math.sin(snapped_angle))
                )
            else:
                self._end = pos

    def on_release(self, pos, doc, fg, bg, opts):
        if self._dragging:
            self.on_move(pos, doc, fg, bg, opts)
            self._dragging = False
            if self._start and self._end and self._start != self._end:
                self.lines.append((self._start, self._end))
            self._start = None
            self._end = None
            
    def get_lines(self):
        res = list(self.lines)
        if self._dragging and self._start and self._end:
            res.append((self._start, self._end))
        return res
        
    def clear(self): self.lines.clear(); self._start = None; self._end = None; self._dragging = False
    def cursor(self): return Qt.CursorShape.CrossCursor