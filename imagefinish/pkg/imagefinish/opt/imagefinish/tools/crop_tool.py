import math
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QPen, QColor
from tools.base_tool import BaseTool


class CropTool(BaseTool):
    name = "Crop"
    icon = "✂️"
    shortcut = "C"

    def __init__(self):
        super().__init__()
        self.pending_rect: QRect | None = None
        self._mode = None
        self._start_pos = None
        self._orig_rect = None
        self._hover_mode = None
        self._smart_guides = []

    def _get_handle_hit(self, pos: QPoint, zoom: float):
        if not self.pending_rect: return None
        r = QRectF(self.pending_rect)
        hit_dist = 8 / max(0.01, zoom)

        handles = {
            'tl': r.topLeft(),
            't':  QPointF(r.center().x(), r.top()),
            'tr': r.topRight(),
            'r':  QPointF(r.right(), r.center().y()),
            'br': r.bottomRight(),
            'b':  QPointF(r.center().x(), r.bottom()),
            'bl': r.bottomLeft(),
            'l':  QPointF(r.left(), r.center().y()),
        }
        min_d = float('inf')
        best_h = None
        for name, pt in handles.items():
            d = math.hypot(pos.x() - pt.x(), pos.y() - pt.y())
            if d < min_d:
                min_d = d
                best_h = name
                
        if min_d <= hit_dist: return best_h
        if r.contains(QPointF(pos)): return 'move'
        return None

    def on_press(self, pos, doc, fg, bg, opts):
        hit = self._get_handle_hit(pos, opts.get("_zoom", 1.0))
        if hit:
            self._mode = hit
            self._start_pos = pos
            self._orig_rect = QRect(self.pending_rect)
        else:
            self._mode = "new"
            self._start_pos = pos
            self.pending_rect = None

    def on_move(self, pos, doc, fg, bg, opts):
        pos_f = QPointF(pos)
        self._smart_guides = []
        
        if not opts.get("_ctrl", False) and getattr(doc, "snap_enabled", True):
            snap = 8 / max(0.01, opts.get("_zoom", 1.0))
            txs, tys = [], []
            if getattr(doc, "snap_to_bounds", True):
                txs.extend([0, doc.width / 2.0, doc.width])
                tys.extend([0, doc.height / 2.0, doc.height])
            if getattr(doc, "snap_to_guides", True) and getattr(doc, "show_guides", True):
                txs.extend(getattr(doc, "guides_v", []))
                tys.extend(getattr(doc, "guides_h", []))
            if getattr(doc, "snap_to_grid", False) and getattr(doc, "show_grid", False):
                gs = getattr(doc, "grid_size", 50)
                gx1, gx2 = int(pos_f.x() // gs) - 1, int(pos_f.x() // gs) + 2
                gy1, gy2 = int(pos_f.y() // gs) - 1, int(pos_f.y() // gs) + 2
                txs.extend([i * gs for i in range(gx1, gx2+1)])
                tys.extend([i * gs for i in range(gy1, gy2+1)])

            if self._mode == "move" and self._orig_rect and self._start_pos:
                delta = pos - self._start_pos
                new_br = QRectF(self._orig_rect).translated(delta.x(), delta.y())
                pxs = [new_br.left(), new_br.center().x(), new_br.right()]
                pys = [new_br.top(), new_br.center().y(), new_br.bottom()]
                
                min_dx, min_dy = snap, snap
                best_dx, best_dy = 0, 0
                snapped_x, snapped_y = None, None
                for tx in txs:
                    for px in pxs:
                        if abs(tx - px) < min_dx:
                            min_dx, best_dx, snapped_x = abs(tx - px), tx - px, tx
                for ty in tys:
                    for py in pys:
                        if abs(ty - py) < min_dy:
                            min_dy, best_dy, snapped_y = abs(ty - py), ty - py, ty
                            
                pos = QPoint(int(pos.x() + best_dx), int(pos.y() + best_dy))
                if snapped_x is not None: self._smart_guides.append(('v', snapped_x))
                if snapped_y is not None: self._smart_guides.append(('h', snapped_y))
            else:
                min_dx, min_dy = snap, snap
                best_dx, best_dy = 0, 0
                snapped_x, snapped_y = None, None
                for tx in txs:
                    if abs(tx - pos_f.x()) < min_dx:
                        min_dx, best_dx, snapped_x = abs(tx - pos_f.x()), tx - pos_f.x(), tx
                for ty in tys:
                    if abs(ty - pos_f.y()) < min_dy:
                        min_dy, best_dy, snapped_y = abs(ty - pos_f.y()), ty - pos_f.y(), ty
                        
                pos = QPoint(int(pos.x() + best_dx), int(pos.y() + best_dy))
                if snapped_x is not None: self._smart_guides.append(('v', snapped_x))
                if snapped_y is not None: self._smart_guides.append(('h', snapped_y))

        if self._mode == "new":
            if self._start_pos:
                self.pending_rect = QRect(self._start_pos, pos).normalized()
        elif self._mode == "move" and self._orig_rect and self._start_pos:
            delta = pos - self._start_pos
            self.pending_rect = self._orig_rect.translated(delta)
        elif self._mode and self._orig_rect and self._start_pos:
            r = QRect(self._orig_rect)
            dx = pos.x() - self._start_pos.x()
            dy = pos.y() - self._start_pos.y()
            
            if 'l' in self._mode: r.setLeft(r.left() + dx)
            if 'r' in self._mode: r.setRight(r.right() + dx)
            if 't' in self._mode: r.setTop(r.top() + dy)
            if 'b' in self._mode: r.setBottom(r.bottom() + dy)
            
            self.pending_rect = r.normalized()

    def on_release(self, pos, doc, fg, bg, opts):
        if self.pending_rect and (self.pending_rect.width() < 5 or self.pending_rect.height() < 5):
            self.pending_rect = None
        self._mode = None
        self._start_pos = None
        self._orig_rect = None
        self._smart_guides = []

    def on_hover(self, pos: QPoint, doc, fg, bg, opts):
        self._hover_mode = self._get_handle_hit(pos, opts.get("_zoom", 1.0))

    def needs_history_push(self):
        return False

    def cursor(self):
        m = self._hover_mode
        if m == 'move': return Qt.CursorShape.SizeAllCursor
        if m in ('tl', 'br'): return Qt.CursorShape.SizeFDiagCursor
        if m in ('tr', 'bl'): return Qt.CursorShape.SizeBDiagCursor
        if m in ('l', 'r'): return Qt.CursorShape.SizeHorCursor
        if m in ('t', 'b'): return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.CrossCursor
        
    def get_transform_params(self):
        if not self.pending_rect: return None
        return {'x': self.pending_rect.x(), 'y': self.pending_rect.y(), 'w': self.pending_rect.width(), 'h': self.pending_rect.height()}

    def set_transform_params(self, doc, params: dict):
        if not self.pending_rect: return
        self.pending_rect = QRect(
            int(params.get('x', self.pending_rect.x())),
            int(params.get('y', self.pending_rect.y())),
            int(params.get('w', self.pending_rect.width())),
            int(params.get('h', self.pending_rect.height()))
        ).normalized()

    def draw_overlays(self, painter, pw, doc):
        if hasattr(self, "_smart_guides") and self._smart_guides:
            painter.save()
            painter.setPen(QPen(QColor(255, 0, 255, 200), max(1.0, pw)))
            for gtype, val in self._smart_guides:
                if gtype == 'v': painter.drawLine(QPointF(val, -10000), QPointF(val, 10000))
                elif gtype == 'h': painter.drawLine(QPointF(-10000, val), QPointF(10000, val))
            painter.restore()
