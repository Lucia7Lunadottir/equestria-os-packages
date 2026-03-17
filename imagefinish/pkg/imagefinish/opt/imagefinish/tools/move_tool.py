import math
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QImage, QPainterPath, QTransform, QPen, QPolygonF
from tools.base_tool import BaseTool
from core.document import Document


class MoveTool(BaseTool):
    name = "Move"
    icon = "✋"
    shortcut = "V"
    modifies_canvas_on_move = True

    def __init__(self):
        super().__init__()
        self.is_transforming = False
        self._target_layer = None
        self._mode = None
        self._hover_mode = None
        self._start_pos = None
        
        self._layer_backup = None
        self._offset_backup = None
        
        self._original_rect = None
        self._original_img = None
        self._original_offset = None
        self._sel_origin = None
        
        self._total_transform = QTransform()
        self._base_transform = QTransform()
        self._bounds = QRectF()
        self._is_floating = False
        self._linked_children = []
        self._start_poly = []
        self._smart_guides = []
        self._snap_targets = []

    def _get_handle_hit(self, pos: QPointF, opts: dict):
        if self._bounds.isEmpty(): return 'move'
        orig_poly = QPolygonF([self._bounds.topLeft(), self._bounds.topRight(), self._bounds.bottomRight(), self._bounds.bottomLeft()])
        poly = self._total_transform.map(orig_poly)
        pts = [QPointF(poly[i]) for i in range(4)]
        handles = {
            'tl': pts[0],
            't':  (pts[0] + pts[1]) / 2.0,
            'tr': pts[1],
            'r':  (pts[1] + pts[2]) / 2.0,
            'br': pts[2],
            'b':  (pts[2] + pts[3]) / 2.0,
            'bl': pts[3],
            'l':  (pts[3] + pts[0]) / 2.0,
        }
        hit_dist = 8 / max(0.01, opts.get("_zoom", 1.0))
        rot_dist = 24 / max(0.01, opts.get("_zoom", 1.0))
        
        min_d = float('inf')
        best_h = None
        for name, pt in handles.items():
            d = math.hypot(pos.x() - pt.x(), pos.y() - pt.y())
            if d < min_d:
                min_d = d
                best_h = name
                
        if min_d <= hit_dist: return best_h
        if min_d <= rot_dist: return 'rotate'
        if poly.containsPoint(pos, Qt.FillRule.OddEvenFill): return 'move'
        return 'move'

    def on_press(self, pos, doc, fg, bg, opts):
        if not self.is_transforming and opts.get("move_auto_select", False):
            for i in range(len(doc.layers) - 1, -1, -1):
                l = doc.layers[i]
                if not l.visible or l.locked: continue
                
                if getattr(l, "layer_type", "raster") == "artboard":
                    if l.artboard_rect and l.artboard_rect.contains(pos):
                        doc.active_layer_index = i
                        break
                elif getattr(l, "layer_type", "raster") == "group":
                    continue
                else:
                    if l.image.isNull(): continue
                    lx, ly = int(pos.x() - l.offset.x()), int(pos.y() - l.offset.y())
                    if 0 <= lx < l.width() and 0 <= ly < l.height():
                        if (l.image.pixel(lx, ly) >> 24) & 0xFF > 0:
                            doc.active_layer_index = i
                            break
                            
        layer = doc.get_active_layer()
        if not layer or layer.locked: return
        
        sel = doc.selection
        has_sel = sel and not sel.isEmpty()
        if getattr(layer, "lock_position", False) and not has_sel: return
        if getattr(layer, "lock_pixels", False) and has_sel: return

        if not self.is_transforming:
            self.is_transforming = True
            self._target_layer = layer
            self._layer_backup = layer.image.copy()
            self._offset_backup = QPoint(layer.offset)
            self._total_transform = QTransform()
            self._linked_children = []
            
            self._snap_targets = []
            if getattr(doc, "snap_to_layers", True):
                for l in doc.layers:
                    if l is layer or not l.visible: continue
                    lr = None
                    if getattr(l, "layer_type", "raster") == "artboard" and getattr(l, "artboard_rect", None):
                        lr = QRectF(l.artboard_rect)
                    elif not l.image.isNull():
                        b = Document._nontransparent_bounds(l.image)
                        if not b.isEmpty(): lr = QRectF(b).translated(QPointF(l.offset))
                    if lr:
                        self._snap_targets.append(lr)
            
            target_id = getattr(layer, "layer_id", None)
            visited_ids = set()
            def get_descendants(p_id):
                if not p_id or p_id in visited_ids: return []
                visited_ids.add(p_id)
                res = []
                for l in doc.layers:
                    if getattr(l, "parent_id", None) == p_id:
                        res.append(l)
                        res.extend(get_descendants(getattr(l, "layer_id", None)))
                return res
                
            if target_id and getattr(layer, "layer_type", "raster") in ("artboard", "group"):
                for kid in get_descendants(target_id):
                    self._linked_children.append({"layer": kid, "backup_offset": QPoint(kid.offset)})
                    
            link_id = getattr(layer, "link_id", None)
            if link_id:
                for l in doc.layers:
                    if getattr(l, "link_id", None) == link_id and l != layer:
                        if not any(k["layer"] == l for k in self._linked_children):
                            self._linked_children.append({"layer": l, "backup_offset": QPoint(l.offset)})

            sel = doc.selection
            if getattr(layer, "layer_type", "raster") in ("artboard", "group"):
                self._is_floating = False
                if getattr(layer, "layer_type", "raster") == "artboard":
                    self._bounds = QRectF(getattr(layer, "artboard_rect", QRect()))
                    self._original_rect = QRect(getattr(layer, "artboard_rect", QRect()))
                else:
                    union_br = QRectF()
                    for k_data in self._linked_children:
                        kid = k_data["layer"]
                        if kid.image and not kid.image.isNull():
                            br = Document._nontransparent_bounds(kid.image)
                            if not br.isEmpty():
                                union_br = union_br.united(QRectF(br).translated(QPointF(kid.offset)))
                    if union_br.isEmpty():
                        union_br = QRectF(layer.offset.x(), layer.offset.y(), 100, 100)
                    self._bounds = union_br
                    self._original_rect = union_br.toRect()
                    
                self._original_img = QImage(1, 1, QImage.Format.Format_ARGB32)
                self._original_offset = layer.offset
                self._sel_origin = None
                
            elif sel and not sel.isEmpty():
                self._is_floating = True
                self._bounds = sel.boundingRect()
                br = self._bounds.toRect()
                
                local_br = br.translated(-layer.offset).intersected(layer.image.rect())
                if local_br.isEmpty():
                    self.is_transforming = False
                    return
                    
                self._original_img = layer.image.copy(local_br)
                self._original_offset = layer.offset + local_br.topLeft()
                self._sel_origin = QPainterPath(sel)
                
                # Clean Numpy Cut for perfectly smooth selection extraction
                import numpy as np
                import ctypes
                mask_img = QImage(local_br.width(), local_br.height(), QImage.Format.Format_Grayscale8)
                mask_img.fill(0)
                p = QPainter(mask_img)
                p.translate(-self._original_offset.x(), -self._original_offset.y())
                p.fillPath(sel, QColor(255, 255, 255))
                p.end()
                
                m_arr = np.empty((local_br.height(), mask_img.bytesPerLine()), dtype=np.uint8)
                ctypes.memmove(m_arr.ctypes.data, int(mask_img.constBits()), mask_img.sizeInBytes())
                mask_f = m_arr[:, :local_br.width()].astype(np.float32) / 255.0
                
                f_arr = np.empty((local_br.height(), self._original_img.bytesPerLine() // 4, 4), dtype=np.uint8)
                ctypes.memmove(f_arr.ctypes.data, int(self._original_img.constBits()), self._original_img.sizeInBytes())
                for c in range(4): f_arr[:local_br.height(), :local_br.width(), c] = (f_arr[:local_br.height(), :local_br.width(), c] * mask_f).astype(np.uint8)
                ctypes.memmove(int(self._original_img.bits()), f_arr.ctypes.data, self._original_img.sizeInBytes())
                
                l_arr = np.empty((layer.height(), layer.image.bytesPerLine() // 4, 4), dtype=np.uint8)
                ctypes.memmove(l_arr.ctypes.data, int(layer.image.constBits()), layer.image.sizeInBytes())
                
                inv_mask_f = 1.0 - mask_f
                sy, sx = local_br.y(), local_br.x()
                l_roi = l_arr[sy:sy+local_br.height(), sx:sx+local_br.width()]
                for c in range(4): l_roi[..., c] = (l_roi[..., c] * inv_mask_f).astype(np.uint8)
                ctypes.memmove(int(layer.image.bits()), l_arr.ctypes.data, layer.image.sizeInBytes())
                
            else:
                self._is_floating = False
                if getattr(layer, "layer_type", "raster") == "frame":
                    self._bounds = QRectF(getattr(layer, "frame_data", {}).get("rect", QRectF(0,0,100,100)))
                    self._original_rect = self._bounds.toRect()
                else:
                    br = Document._nontransparent_bounds(layer.image)
                    if br.isEmpty():
                        self._bounds = QRectF(layer.offset.x(), layer.offset.y(), layer.width(), layer.height())
                    else:
                        self._bounds = QRectF(br).translated(QPointF(layer.offset))
                self._original_img = layer.image.copy()
                self._original_offset = layer.offset
                self._sel_origin = None
                layer.image = QImage(1, 1, QImage.Format.Format_ARGB32)
                layer.image.fill(Qt.GlobalColor.transparent)

        self._base_transform = QTransform(self._total_transform)
        self._start_pos = QPointF(pos)
        orig_poly = QPolygonF([self._bounds.topLeft(), self._bounds.topRight(), self._bounds.bottomRight(), self._bounds.bottomLeft()])
        mapped = self._base_transform.map(orig_poly)
        self._start_poly = [QPointF(mapped[i]) for i in range(4)]
        self._mode = self._get_handle_hit(QPointF(pos), opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if not self._mode or not self.is_transforming: return
        layer = self._target_layer
        if not layer: return
        
        pos_f = QPointF(pos)
        delta = pos_f - self._start_pos
        pts = [QPointF(p) for p in self._start_poly]
        
        ctrl = opts.get("_ctrl", False)
        shift = opts.get("_shift", False)
        alt = opts.get("_alt", False)
        
        corner_indices = {'tl': 0, 'tr': 1, 'br': 2, 'bl': 3}
        edge_indices = {'t': (0,1), 'r': (1,2), 'b': (2,3), 'l': (3,0)}
        
        if self._mode == 'move':
            dx, dy = delta.x(), delta.y()
            orig_poly = QPolygonF([self._bounds.topLeft(), self._bounds.topRight(), self._bounds.bottomRight(), self._bounds.bottomLeft()])
            br = self._base_transform.map(orig_poly).boundingRect()
            new_br = br.translated(dx, dy)
            
            self._smart_guides = []
            
            if not opts.get("_ctrl", False) and getattr(doc, "snap_enabled", True):
                snap_threshold = 8 / max(0.01, opts.get("_zoom", 1.0))
                best_dx, best_dy = dx, dy
                min_dx, min_dy = float('inf'), float('inf')
                
                txs, tys = [], []
                if getattr(doc, "snap_to_bounds", True):
                    txs.extend([0, doc.width / 2.0, doc.width]); tys.extend([0, doc.height / 2.0, doc.height])
                if getattr(doc, "snap_to_guides", True) and getattr(doc, "show_guides", True):
                    txs.extend(getattr(doc, "guides_v", [])); tys.extend(getattr(doc, "guides_h", []))
                if getattr(doc, "snap_to_grid", False) and getattr(doc, "show_grid", False):
                    gs = getattr(doc, "grid_size", 50)
                    gx1, gx2 = int(new_br.left() // gs), int(new_br.right() // gs) + 1
                    gy1, gy2 = int(new_br.top() // gs), int(new_br.bottom() // gs) + 1
                    txs.extend([i * gs for i in range(gx1, gx2+1)])
                    tys.extend([i * gs for i in range(gy1, gy2+1)])
                if getattr(doc, "snap_to_layers", True) and hasattr(self, "_snap_targets"):
                    for lr in self._snap_targets:
                        txs.extend([lr.left(), lr.center().x(), lr.right()])
                        tys.extend([lr.top(), lr.center().y(), lr.bottom()])
                            
                txs = list(set(txs)); tys = list(set(tys))
                pxs = [new_br.left(), new_br.center().x(), new_br.right()]
                pys = [new_br.top(), new_br.center().y(), new_br.bottom()]
                
                snapped_x, snapped_y = None, None
                for tx in txs:
                    for px in pxs:
                        if abs(tx - px) < snap_threshold and abs(tx - px) < min_dx:
                            min_dx, best_dx, snapped_x = abs(tx - px), dx + (tx - px), tx
                for ty in tys:
                    for py in pys:
                        if abs(ty - py) < snap_threshold and abs(ty - py) < min_dy:
                            min_dy, best_dy, snapped_y = abs(ty - py), dy + (ty - py), ty
                            
                delta = QPointF(best_dx, best_dy)
                if snapped_x is not None: self._smart_guides.append(('v', snapped_x))
                if snapped_y is not None: self._smart_guides.append(('h', snapped_y))
                
            for i in range(4): pts[i] = self._start_poly[i] + delta
            
        elif self._mode == 'rotate':
            center = self._base_transform.map(self._bounds.center())
            a1 = math.atan2(self._start_pos.y() - center.y(), self._start_pos.x() - center.x())
            a2 = math.atan2(pos_f.y() - center.y(), pos_f.x() - center.x())
            da = math.degrees(a2 - a1)
            if shift:
                da = round(da / 15.0) * 15.0
            t = QTransform().translate(center.x(), center.y()).rotate(da).translate(-center.x(), -center.y())
            pts = [t.map(p) for p in self._start_poly]
            
        elif ctrl:
            if self._mode in corner_indices:
                idx = corner_indices[self._mode]
                opp_idx = (idx + 2) % 4
                
                if alt and shift:
                    e1 = pts[(idx+1)%4] - pts[idx]
                    e2 = pts[(idx+3)%4] - pts[idx]
                    l1 = math.hypot(e1.x(), e1.y())
                    l2 = math.hypot(e2.x(), e2.y())
                    n1 = QPointF(e1.x()/l1, e1.y()/l1) if l1 else QPointF(1,0)
                    n2 = QPointF(e2.x()/l2, e2.y()/l2) if l2 else QPointF(0,1)
                    
                    dot1 = abs(delta.x()*n1.x() + delta.y()*n1.y())
                    dot2 = abs(delta.x()*n2.x() + delta.y()*n2.y())
                    if dot1 > dot2:
                        proj = delta.x()*n1.x() + delta.y()*n1.y()
                        n = n1
                        opp_adj = (idx+1)%4
                    else:
                        proj = delta.x()*n2.x() + delta.y()*n2.y()
                        n = n2
                        opp_adj = (idx+3)%4
                        
                    move_vec = QPointF(n.x()*proj, n.y()*proj)
                    pts[idx] = pts[idx] + move_vec
                    pts[opp_adj] = pts[opp_adj] - move_vec

                elif shift:
                    e1 = pts[(idx+1)%4] - pts[idx]
                    e2 = pts[(idx+3)%4] - pts[idx]
                    l1 = math.hypot(e1.x(), e1.y())
                    l2 = math.hypot(e2.x(), e2.y())
                    n1 = QPointF(e1.x()/l1, e1.y()/l1) if l1 else QPointF(1,0)
                    n2 = QPointF(e2.x()/l2, e2.y()/l2) if l2 else QPointF(0,1)
                    
                    dot1 = abs(delta.x()*n1.x() + delta.y()*n1.y())
                    dot2 = abs(delta.x()*n2.x() + delta.y()*n2.y())
                    if dot1 > dot2:
                        proj = delta.x()*n1.x() + delta.y()*n1.y()
                        n = n1
                    else:
                        proj = delta.x()*n2.x() + delta.y()*n2.y()
                        n = n2
                        
                    move_vec = QPointF(n.x()*proj, n.y()*proj)
                    pts[idx] = pts[idx] + move_vec

                elif alt:
                    pts[idx] = pts[idx] + delta
                    pts[opp_idx] = pts[opp_idx] - delta
                else:
                    pts[idx] = pts[idx] + delta
                    
            elif self._mode in edge_indices:
                i1, i2 = edge_indices[self._mode]
                opp1, opp2 = (i1+2)%4, (i2+2)%4
                
                if shift:
                    edge_vec = pts[i2] - pts[i1]
                    l = math.hypot(edge_vec.x(), edge_vec.y())
                    n = QPointF(edge_vec.x()/l, edge_vec.y()/l) if l else QPointF(1,0)
                    proj = delta.x()*n.x() + delta.y()*n.y()
                    move_vec = QPointF(n.x()*proj, n.y()*proj)
                else:
                    move_vec = delta
                    
                if alt:
                    pts[i1] = pts[i1] + move_vec
                    pts[i2] = pts[i2] + move_vec
                    pts[opp1] = pts[opp1] - move_vec
                    pts[opp2] = pts[opp2] - move_vec
                else:
                    pts[i1] = pts[i1] + move_vec
                    pts[i2] = pts[i2] + move_vec
                    
        else:
            inv_base, ok = self._base_transform.inverted()
            if ok:
                local_start = inv_base.map(self._start_pos)
                local_pos = inv_base.map(pos_f)
                
                b = self._bounds
                local_pts = {
                    'tl': b.topLeft(), 't': QPointF(b.center().x(), b.top()), 'tr': b.topRight(),
                    'r':  QPointF(b.right(), b.center().y()), 'br': b.bottomRight(),
                    'b':  QPointF(b.center().x(), b.bottom()), 'bl': b.bottomLeft(),
                    'l':  QPointF(b.left(), b.center().y())
                }
                anchors = {
                    'br': ('tl', 'br'), 'tl': ('br', 'tl'),
                    'tr': ('bl', 'tr'), 'bl': ('tr', 'bl'),
                    'r':  ('l', 'r'),   'l':  ('r', 'l'),
                    'b':  ('t', 'b'),   't':  ('b', 't'),
                }
                
                if self._mode in anchors:
                    anchor_name, drag_name = anchors[self._mode]
                    anchor_pt = local_pts[anchor_name]
                    drag_pt = local_pts[drag_name]
                    
                    if alt:
                        anchor_pt = b.center()
            
                    v_orig_x = drag_pt.x() - anchor_pt.x()
                    v_orig_y = drag_pt.y() - anchor_pt.y()
                    v_cur_x = local_pos.x() - anchor_pt.x()
                    v_cur_y = local_pos.y() - anchor_pt.y()
            
                    sx = v_cur_x / v_orig_x if abs(v_orig_x) > 0.001 else 1.0
                    sy = v_cur_y / v_orig_y if abs(v_orig_y) > 0.001 else 1.0
            
                    if self._mode in ('r', 'l'): sy = 1.0
                    if self._mode in ('t', 'b'): sx = 1.0
                    
                    if shift and self._mode in corner_indices:
                        s = max(abs(sx), abs(sy))
                        sx = s * (1 if sx >= 0 else -1)
                        sy = s * (1 if sy >= 0 else -1)
                
                    scale_t = QTransform().translate(anchor_pt.x(), anchor_pt.y()).scale(sx, sy).translate(-anchor_pt.x(), -anchor_pt.y())
                    new_local_poly = scale_t.map(QPolygonF([b.topLeft(), b.topRight(), b.bottomRight(), b.bottomLeft()]))
                pts = [self._base_transform.map(QPointF(new_local_poly[i])) for i in range(4)]

        orig_poly = QPolygonF([self._bounds.topLeft(), self._bounds.topRight(), self._bounds.bottomRight(), self._bounds.bottomLeft()])
        new_poly = QPolygonF(pts)
        
        final_t = QTransform()
        ok = QTransform.quadToQuad(orig_poly, new_poly, final_t)
        if ok:
            self._total_transform = final_t
            
            if getattr(layer, "layer_type", "raster") == "artboard":
                layer.artboard_rect = final_t.mapRect(QRectF(self._original_rect)).toRect()
            elif self._is_floating and self._sel_origin:
                doc.selection = final_t.map(self._sel_origin)
                
            if self._mode == 'move':
                dx, dy = final_t.dx(), final_t.dy()
                for kid_data in self._linked_children:
                    kid_data["layer"].offset = kid_data["backup_offset"] + QPoint(int(dx), int(dy))

    def on_hover(self, pos: QPoint, doc, fg, bg, opts):
        if self.is_transforming:
            self._hover_mode = self._get_handle_hit(QPointF(pos), opts)
        else:
            self._hover_mode = None

    def on_release(self, pos, doc, fg, bg, opts):
        self._mode = None
        self._start_poly = []
        self._base_transform = QTransform()

    def floating_preview(self):
        if self.is_transforming and self._original_img is not None:
            return ("transform", self._original_img, self._original_offset, self._total_transform)
        return None

    def draw_overlays(self, painter: QPainter, pw: float, doc):
        if not self.is_transforming: return
        
        if hasattr(self, "_smart_guides") and self._smart_guides:
            painter.save()
            painter.setPen(QPen(QColor(255, 0, 255, 200), max(1.0, pw)))
            for gtype, val in self._smart_guides:
                if gtype == 'v': painter.drawLine(QPointF(val, -10000), QPointF(val, 10000))
                elif gtype == 'h': painter.drawLine(QPointF(-10000, val), QPointF(10000, val))
            painter.restore()
            
        orig_poly = QPolygonF([self._bounds.topLeft(), self._bounds.topRight(), self._bounds.bottomRight(), self._bounds.bottomLeft()])
        poly = self._total_transform.map(orig_poly)
        pts = [QPointF(poly[i]) for i in range(4)]
            
        painter.save()
        painter.setPen(QPen(QColor(0, 0, 0, 180), pw))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(poly)
        painter.setPen(QPen(QColor(255, 255, 255, 200), pw, Qt.PenStyle.DashLine))
        painter.drawPolygon(poly)
        
        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(QPen(QColor(0, 0, 0), pw))
        s = 3 * pw
        handles = [
            pts[0], (pts[0]+pts[1])/2, pts[1], (pts[1]+pts[2])/2,
            pts[2], (pts[2]+pts[3])/2, pts[3], (pts[3]+pts[0])/2
        ]
        for pt in handles:
            painter.drawRect(QRectF(pt.x() - s, pt.y() - s, s*2, s*2))
        painter.restore()
        
    def apply_transform(self, doc):
        if not self.is_transforming: return
        layer = self._target_layer
        if not layer: return
        
        final_t = self._total_transform
        
        dx, dy = final_t.dx(), final_t.dy()
        for kid_data in getattr(self, "_linked_children", []):
            kid_data["layer"].offset = kid_data["backup_offset"] + QPoint(int(dx), int(dy))
            
        if getattr(layer, "layer_type", "raster") == "artboard":
            new_rect = final_t.mapRect(QRectF(self._original_rect)).toRect()
            layer.artboard_rect = new_rect
            self._reset_state()
            doc.fit_to_artboards()
            return
        elif getattr(layer, "layer_type", "raster") == "frame":
            layer.frame_data["rect"] = final_t.mapRect(QRectF(self._original_rect))
        elif getattr(layer, "layer_type", "raster") == "group":
            self._reset_state()
            return
            
        if not final_t.isIdentity():
            src_rect = QRectF(0, 0, self._original_img.width(), self._original_img.height())
            doc_transform = QTransform().translate(self._original_offset.x(), self._original_offset.y()) * final_t
            mapped_rect = doc_transform.mapRect(src_rect)
            
            new_w, new_h = int(math.ceil(mapped_rect.width())), int(math.ceil(mapped_rect.height()))
            if new_w > 0 and new_h > 0:
                new_img = QImage(new_w, new_h, QImage.Format.Format_ARGB32_Premultiplied)
                new_img.fill(Qt.GlobalColor.transparent)
                p = QPainter(new_img)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                local_transform = doc_transform * QTransform().translate(-mapped_rect.left(), -mapped_rect.top())
                p.setTransform(local_transform)
                p.drawImage(0, 0, self._original_img)
                p.end()
                self._original_img = new_img
                self._original_offset = QPoint(int(mapped_rect.left()), int(mapped_rect.top()))
                
        if self._is_floating:
            p = QPainter(layer.image)
            p.drawImage(self._original_offset, self._original_img)
            p.end()
        else:
            layer.image = self._original_img
            layer.offset = self._original_offset
            
        self._reset_state()

    def cancel_transform(self, doc):
        if not self.is_transforming: return
        layer = self._target_layer
        if layer and self._layer_backup is not None:
            layer.image = self._layer_backup
            layer.offset = self._offset_backup
            if getattr(layer, "layer_type", "raster") == "artboard":
                layer.artboard_rect = QRect(self._original_rect) if self._original_rect else None
            elif getattr(layer, "layer_type", "raster") == "frame":
                layer.frame_data["rect"] = QRectF(self._original_rect) if self._original_rect else QRectF()
            if self._sel_origin: doc.selection = self._sel_origin
            
        for kid_data in getattr(self, "_linked_children", []):
            kid_data["layer"].offset = kid_data["backup_offset"]
        self._reset_state()
        
    def get_transform_params(self):
        if not self.is_transforming: return None
        t = self._total_transform
        m11, m12, m21, m22 = t.m11(), t.m12(), t.m21(), t.m22()
        
        scale_x = math.hypot(m11, m12)
        angle = math.atan2(m12, m11)
        det = m11 * m22 - m12 * m21
        scale_y = det / scale_x if scale_x != 0 else math.hypot(m21, m22)
        
        orig_poly = QPolygonF([self._bounds.topLeft(), self._bounds.topRight(), self._bounds.bottomRight(), self._bounds.bottomLeft()])
        poly = t.map(orig_poly)
        cx = sum(p.x() for p in poly) / 4.0
        cy = sum(p.y() for p in poly) / 4.0
        
        return {'x': cx, 'y': cy, 'w': scale_x * 100.0, 'h': scale_y * 100.0, 'angle': math.degrees(angle)}
        
    def set_transform_params(self, doc, params: dict):
        if not self.is_transforming: return
        cx, cy = params.get('x', self._bounds.center().x()), params.get('y', self._bounds.center().y())
        w_pct, h_pct = params.get('w', 100.0) / 100.0, params.get('h', 100.0) / 100.0
        angle = params.get('angle', 0.0)
        
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(angle)
        t.scale(w_pct, h_pct)
        t.translate(-self._bounds.center().x(), -self._bounds.center().y())
        self._total_transform = t
        
        layer = self._target_layer
        if getattr(layer, "layer_type", "raster") == "artboard":
            layer.artboard_rect = self._total_transform.mapRect(QRectF(self._original_rect)).toRect()
        elif getattr(layer, "layer_type", "raster") == "frame":
            layer.frame_data["rect"] = self._total_transform.mapRect(QRectF(self._original_rect))
        elif self._is_floating and self._sel_origin:
            doc.selection = self._total_transform.map(self._sel_origin)
            
        dx, dy = self._total_transform.dx(), self._total_transform.dy()
        for kid_data in getattr(self, "_linked_children", []):
            kid_data["layer"].offset = kid_data["backup_offset"] + QPoint(int(dx), int(dy))

    def _reset_state(self):
        self.is_transforming = False
        self._target_layer = None
        self._layer_backup = None
        self._offset_backup = None
        self._original_rect = None
        self._original_img = None
        self._sel_origin = None
        self._linked_children = []
        self._total_transform = QTransform()
        self._base_transform = QTransform()
        self._bounds = QRectF()
        self._mode = None
        self._start_poly = []
        self._smart_guides = []

    def needs_history_push(self): return False

    def cursor(self):
        if not self.is_transforming: return Qt.CursorShape.SizeAllCursor
        m = getattr(self, "_hover_mode", None)
        if m == 'rotate': return Qt.CursorShape.CrossCursor
        if m in ('tl', 'br'): return Qt.CursorShape.SizeFDiagCursor
        if m in ('tr', 'bl'): return Qt.CursorShape.SizeBDiagCursor
        if m in ('l', 'r'): return Qt.CursorShape.SizeHorCursor
        if m in ('t', 'b'): return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.SizeAllCursor
