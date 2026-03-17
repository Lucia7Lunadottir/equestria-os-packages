import os
import math, random
import numpy as np
from PyQt6.QtGui import (QPainter, QColor, QPen, QRadialGradient, QBrush,
                         QImage, QPixmap, QTransform)
from PyQt6.QtCore import QPoint, QPointF, Qt, QRect
from tools.base_tool import BaseTool


def _make_brush_stamp(size: int, hardness: float, mask: str) -> QImage:
    """
    Возвращает QImage (size×size ARGB32) — «штамп» кисти.
    Alpha-канал определяет форму: 255 = полная краска, 0 = пусто.

    mask:
      round   — круглая с мягкостью по hardness
      square  — квадратная
      scatter — круглая с шумом по краям
    """
    s = max(2, size)
    img = QImage(s, s, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, r = s / 2, s / 2, s / 2 - 0.5

    if mask == "square":
        margin = int(s * (1 - hardness) * 0.3)
        inner = QRect(margin, margin, s - 2 * margin, s - 2 * margin)
        p.fillRect(img.rect(), Qt.GlobalColor.transparent)
        p.setBrush(QBrush(QColor(0, 0, 0, 255)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(inner, margin * 0.5, margin * 0.5)

    elif mask == "scatter":
        # Основа — мягкий круг, по краю — случайные выбросы
        grad = QRadialGradient(cx, cy, r)
        inner_stop = max(0.0, min(1.0, hardness))
        grad.setColorAt(0,          QColor(0, 0, 0, 255))
        grad.setColorAt(inner_stop, QColor(0, 0, 0, 255))
        grad.setColorAt(1.0,        QColor(0, 0, 0, 0))
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)
        # Добавляем случайные "брызги" снаружи
        p.setBrush(QBrush(QColor(0, 0, 0, 180)))
        rng = random.Random(size)   # детерминированный seed
        for _ in range(int(s * 0.4)):
            angle = rng.uniform(0, 2 * math.pi)
            dist  = rng.uniform(r * 0.6, r * 1.3)
            sx = cx + math.cos(angle) * dist
            sy = cy + math.sin(angle) * dist
            dr = rng.uniform(0.5, max(1, s * 0.04))
            p.drawEllipse(QPointF(sx, sy), dr, dr)

    else:  # round (default)
        grad = QRadialGradient(cx, cy, r)
        inner_stop = max(0.0, min(0.99, hardness))

        # Common start for all round brushes
        grad.setColorAt(0, QColor(0, 0, 0, 255))
        grad.setColorAt(inner_stop, QColor(0, 0, 0, 255))

        # Smoother, quadratic falloff for soft brushes feels more natural
        if inner_stop < 0.1:  # Apply to very soft brushes (hardness < 10%)
            # Approximation of y=(1-x)^2 curve from inner_stop to 1.0
            span = 1.0 - inner_stop
            if span > 0:
                # y = (1 - (x-is)/span)^2. We start from t=0.25
                for i in range(1, 5):
                    t = i / 4.0
                    x = inner_stop + t * span
                    y = (1.0 - t)**2
                    grad.setColorAt(x, QColor(0, 0, 0, int(255 * y)))
            else:  # this case is inner_stop >= 1, but for safety
                grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        else:  # Original linear falloff for harder brushes
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)

    p.end()
    return img


class BrushTool(BaseTool):
    name     = "Brush"
    icon     = "🖌️"
    shortcut = "B"
    modifies_canvas_on_move = True

    def __init__(self):
        self._last_pos: QPoint | None = None
        self._last_pressure: float = 1.0
        self._stamp_cache: dict = {}  # key: (size, hardness, mask), val: QImage
        self._stroke_layer = None
        self._target_img: QImage | None = None
        self._stroke_img: QImage | None = None
        self._stroke_opacity: float = 1.0
        self._stroke_clip = None  # QPainterPath | None

    def on_press(self, pos, doc, fg, bg, opts):
        self._last_pos = pos
        layer = doc.get_active_layer()
        if not layer or layer.locked or getattr(layer, "lock_pixels", False):
            return
        self._last_pressure = float(opts.get("_pressure", 1.0))
        self._stroke_layer = layer
        
        if getattr(layer, "editing_mask", False) and getattr(layer, "mask", None) is not None:
            self._target_img = layer.mask
        else:
            self._target_img = layer.image
            
        self._stroke_img = QImage(self._target_img.size(), QImage.Format.Format_ARGB32_Premultiplied)
        self._stroke_img.fill(Qt.GlobalColor.transparent)
        self._stroke_opacity = float(opts.get("brush_opacity", 1.0))
        sel = doc.selection
        self._stroke_clip = sel if (sel and not sel.isEmpty()) else None
        
        layer.active_stroke = {
            "img": self._stroke_img,
            "opacity": self._stroke_opacity,
            "mode": self.stroke_composition_mode(opts),
            "clip": self._stroke_clip
        }
        
        self._paint(pos, pos, doc, fg, opts, self._last_pressure, self._last_pressure)

    def on_move(self, pos, doc, fg, bg, opts):
        curr_pressure = float(opts.get("_pressure", 1.0))
        if self._last_pos:
            self._paint(self._last_pos, pos, doc, fg, opts, self._last_pressure, curr_pressure)
        self._last_pos = pos
        self._last_pressure = curr_pressure

    def on_release(self, pos, doc, fg, bg, opts):
        # Apply stroke buffer once (opacity per stroke)
        layer = self._stroke_layer
        if layer and self._stroke_img is not None and not layer.locked:
            target = self._target_img
            lock_a = getattr(layer, "lock_alpha", False) and target is layer.image
            
            stroke_to_draw = self._stroke_img
            offset_style = (getattr(layer, "layer_styles", None) or {}).get("offset", {})
            if offset_style.get("enabled") and not getattr(layer, "editing_mask", False):
                dx_pct = offset_style.get("dx_pct", 0)
                dy_pct = offset_style.get("dy_pct", 0)
                edge_mode = offset_style.get("edge_mode", "wrap")
                if dx_pct != 0 or dy_pct != 0:
                    h, w = stroke_to_draw.height(), stroke_to_draw.width()
                    dx = -int(w * dx_pct / 100.0)
                    dy = -int(h * dy_pct / 100.0)
                    import numpy as np, ctypes
                    ptr = stroke_to_draw.constBits()
                    buf = (ctypes.c_uint8 * stroke_to_draw.sizeInBytes()).from_address(int(ptr))
                    arr = np.ndarray((h, stroke_to_draw.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
                    if edge_mode == "wrap":
                        res_arr = np.roll(np.roll(arr, dy, axis=0), dx, axis=1)
                    elif edge_mode == "repeat":
                        Y, X = np.ogrid[:h, :w]
                        Y = np.clip(Y - dy, 0, h - 1); X = np.clip(X - dx, 0, w - 1)
                        res_arr = arr[Y, X]
                    else:
                        res_arr = np.zeros_like(arr)
                        y1_src, y2_src = max(0, -dy), min(h, h - dy); x1_src, x2_src = max(0, -dx), min(w, w - dx)
                        y1_dst, y2_dst = max(0, dy), min(h, h + dy); x1_dst, x2_dst = max(0, dx), min(w, w + dx)
                        if y1_src < y2_src and x1_src < x2_src: res_arr[y1_dst:y2_dst, x1_dst:x2_dst] = arr[y1_src:y2_src, x1_src:x2_src]
                    stroke_to_draw = QImage(res_arr.data, w, h, w*4, QImage.Format.Format_ARGB32_Premultiplied)
                    stroke_to_draw.ndarray = res_arr

            if lock_a:
                import ctypes
                w, h = target.width(), target.height()
                ptr = target.bits()
                buf = (ctypes.c_uint8 * target.sizeInBytes()).from_address(int(ptr))
                arr = np.ndarray((h, target.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
                orig_alpha = arr[..., 3].copy()

            painter = QPainter(target)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if self._stroke_clip is not None:
                painter.setClipPath(self._stroke_clip.translated(-layer.offset.x(), -layer.offset.y()))
            painter.setCompositionMode(self.stroke_composition_mode(opts))
            painter.setOpacity(max(0.0, min(1.0, float(self._stroke_opacity))))
            painter.drawImage(0, 0, stroke_to_draw)
            painter.end()

            if lock_a:
                new_alpha = arr[..., 3].astype(np.float32)
                new_alpha[new_alpha == 0] = 1.0 
                ratio = orig_alpha.astype(np.float32) / new_alpha
                arr[..., 0] = np.clip(arr[..., 0] * ratio, 0, 255).astype(np.uint8)
                arr[..., 1] = np.clip(arr[..., 1] * ratio, 0, 255).astype(np.uint8)
                arr[..., 2] = np.clip(arr[..., 2] * ratio, 0, 255).astype(np.uint8)
                arr[..., 3] = orig_alpha

        if layer and hasattr(layer, "active_stroke"):
            del layer.active_stroke

        self._last_pos = None
        self._stroke_layer = None
        self._target_img = None
        self._stroke_img = None
        self._stroke_clip = None
        self._stroke_opacity = 1.0

    def stroke_preview(self):
        """Return (QImage, top_left: QPoint, opacity: float) for live canvas overlay."""
        if self._stroke_img is None:
            return None
        offset = self._stroke_layer.offset if self._stroke_layer else QPoint(0, 0)
        return (self._stroke_img, offset, float(self._stroke_opacity))

    def stroke_composition_mode(self, opts=None):
        if opts is None: opts = {}
        mode_str = opts.get("brush_blend_mode", "SourceOver")
        mapping = {
            "SourceOver": QPainter.CompositionMode.CompositionMode_SourceOver,
            "Multiply": QPainter.CompositionMode.CompositionMode_Multiply,
            "Screen": QPainter.CompositionMode.CompositionMode_Screen,
            "Overlay": QPainter.CompositionMode.CompositionMode_Overlay,
            "Darken": QPainter.CompositionMode.CompositionMode_Darken,
            "Lighten": QPainter.CompositionMode.CompositionMode_Lighten,
            "ColorDodge": QPainter.CompositionMode.CompositionMode_ColorDodge,
            "ColorBurn": QPainter.CompositionMode.CompositionMode_ColorBurn,
            "HardLight": QPainter.CompositionMode.CompositionMode_HardLight,
            "SoftLight": QPainter.CompositionMode.CompositionMode_SoftLight,
            "Difference": QPainter.CompositionMode.CompositionMode_Difference,
            "Exclusion": QPainter.CompositionMode.CompositionMode_Exclusion,
        }
        return mapping.get(mode_str, QPainter.CompositionMode.CompositionMode_SourceOver)

    def _get_stamp(self, size: int, hardness: float, mask) -> QImage:
        """
        Возвращает «штамп» кисти, используя кэш.
        """
        actual_mask = mask
        if isinstance(actual_mask, QPixmap):
            actual_mask = actual_mask.toImage()
        elif isinstance(actual_mask, str) and actual_mask not in ("round", "square", "scatter"):
            tmp = QImage(actual_mask)
            if not tmp.isNull():
                actual_mask = tmp

        cache_key = id(actual_mask) if isinstance(actual_mask, QImage) else actual_mask
        full_key = (size, hardness, cache_key)

        if full_key in self._stamp_cache:
            return self._stamp_cache[full_key]

        if isinstance(actual_mask, QImage) and not actual_mask.isNull():
            # Для кастомных кистей, маска — это QImage. Масштабируем его до размера кисти.
            # Игнорируем соотношение сторон, чтобы он соответствовал квадратной области штампа.
            stamp = actual_mask.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            # Если у кисти нет прозрачности (например, чёрно-белый исходник),
            # она нарисуется сплошным квадратом. Вытягиваем альфу из яркости!
            if not stamp.hasAlphaChannel():
                stamp = stamp.convertToFormat(QImage.Format.Format_ARGB32)
                import numpy as np
                import ctypes
                ptr = stamp.bits()
                buf = (ctypes.c_uint8 * stamp.sizeInBytes()).from_address(int(ptr))
                arr = np.ndarray((stamp.height(), stamp.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
                
                # Считаем яркость. Тёмное = кисть, белое = фон.
                luma = (arr[..., 2]*0.299 + arr[..., 1]*0.587 + arr[..., 0]*0.114).astype(np.uint8)
                
                # Делаем альфа-канал из инвертированной яркости
                arr[..., 3] = 255 - luma
                # Основной цвет делаем чёрным (потом он окрасится в нужный цвет при рисовании)
                arr[..., 0:3] = 0
        else:
            # Для стандартных кистей ("round", "square") генерируем штамп.
            stamp = _make_brush_stamp(size, hardness, actual_mask)

        # Ограничиваем кэш, чтобы не забить память при динамическом размере
        if len(self._stamp_cache) > 50:
            self._stamp_cache.clear()
        self._stamp_cache[full_key] = stamp
        return stamp

    # ── рисование штампами вдоль отрезка ────────────────────────────────────
    def _paint(self, p1: QPoint, p2: QPoint, doc, color: QColor, opts: dict, press1: float = 1.0, press2: float = 1.0):
        layer = self._stroke_layer
        if not layer or layer.locked or self._stroke_img is None:
            return

        # Opacity is applied once on release; keep full-strength within the stroke.
        hardness = float(opts.get("brush_hardness", 1.0))
        mask     = opts.get("brush_mask", "round")
        angle    = float(opts.get("brush_angle", 0.0))
        angle_random = bool(opts.get("brush_angle_random", False))
        size_base = max(1, int(opts.get("brush_size", 10)))
        size_dyn = bool(opts.get("brush_size_dynamic", False))
        op_dyn   = bool(opts.get("brush_opacity_dynamic", False))
        pattern_scale = float(opts.get("brush_pattern_scale", 100)) / 100.0
        mirror_x = bool(opts.get("brush_mirror_x", False))
        mirror_y = bool(opts.get("brush_mirror_y", False))
        cx_pct = float(opts.get("brush_mirror_cx", 0.5))
        cy_pct = float(opts.get("brush_mirror_cy", 0.5))
        doc_w, doc_h = doc.width, doc.height
        sym_x = doc_w * cx_pct
        sym_y = doc_h * cy_pct
        
        is_pattern_stamp = getattr(self, "name", "") == "PatternStamp"
        pattern_pixmap = None
        if is_pattern_stamp:
            pattern_path = opts.get("brush_pattern", "")
            if pattern_path and os.path.exists(pattern_path):
                pattern_pixmap = QPixmap(pattern_path)

        # Для очень жёстких круглых кистей — быстрый QPen
        if not is_pattern_stamp and mask == "round" and hardness >= 0.98 and not size_dyn and not op_dyn:
            self._paint_fast(p1, p2, layer, color, size_base, doc, opts)
            return

        # Штамп-кисть: рисуем вдоль отрезка с шагом size/3
        step  = max(1, size_base // 3)
        dx    = p2.x() - p1.x()
        dy    = p2.y() - p1.y()
        dist  = math.hypot(dx, dy)
        
        if dist == 0:
            steps = 0
            start_i = 0
        else:
            steps = max(1, int(dist / step))
            start_i = 1

        c = QColor(color)

        painter = QPainter(self._stroke_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._stroke_clip is not None:
            painter.setClipPath(self._stroke_clip.translated(-layer.offset.x(), -layer.offset.y()))
        
        if getattr(self, "name", "") == "MixerBrush":
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        else:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)

        for i in range(start_i, steps + 1):
            t = 0 if steps == 0 else i / steps
            cur_press = press1 + (press2 - press1) * t
            
            cur_size = size_base
            if size_dyn:
                cur_size = max(1, int(size_base * cur_press))
                
            stamp = self._get_stamp(cur_size, hardness, mask)
            
            cx = p1.x() + dx * t
            cy = p1.y() + dy * t
            
            centers = [(cx, cy)]
            if mirror_x: centers.extend([(2 * sym_x - c[0], c[1]) for c in centers])
            if mirror_y: centers.extend([(c[0], 2 * sym_y - c[1]) for c in centers])
            
            # dict.fromkeys убирает дубликаты (например, если рисуем прямо по оси), сохраняя порядок
            for target_cx, target_cy in list(dict.fromkeys(centers)):
                painter.save()
                painter.translate(target_cx - layer.offset.x(), target_cy - layer.offset.y())
                current_angle = random.uniform(0, 360) if angle_random else angle
                if current_angle != 0.0:
                    painter.rotate(current_angle)
                painter.translate(-cur_size / 2.0, -cur_size / 2.0)
                # Применяем alpha-маску штампа
                colored = QImage(stamp.size(), QImage.Format.Format_ARGB32)
                
                if pattern_pixmap and not pattern_pixmap.isNull():
                    colored.fill(Qt.GlobalColor.transparent)
                    ppat = QPainter(colored)
                    b = QBrush(pattern_pixmap)
                    xform = QTransform()
                    xform.translate(target_cx, target_cy)
                    if current_angle != 0.0: xform.rotate(current_angle)
                    xform.translate(-cur_size / 2.0, -cur_size / 2.0)
                    
                    brush_xform = QTransform()
                    brush_xform.scale(pattern_scale, pattern_scale)
                    brush_xform *= xform.inverted()[0]
                    b.setTransform(brush_xform)
                    
                    ppat.fillRect(colored.rect(), b)
                    if op_dyn:
                        ppat.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                        ppat.fillRect(colored.rect(), QColor(0, 0, 0, int(255 * cur_press)))
                    ppat.end()
                else:
                    stamp_color = QColor(c)
                    if op_dyn: stamp_color.setAlpha(int(255 * cur_press))
                    colored.fill(stamp_color)
                
                cp = QPainter(colored)
                cp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                cp.drawImage(0, 0, stamp)
                cp.end()
                painter.drawImage(0, 0, colored)
                painter.restore()

        painter.end()

    def _paint_fast(self, p1, p2, layer, color, size, doc, opts):
        """Быстрый путь: QPen без штампа."""
        c = QColor(color)
        painter = QPainter(self._stroke_img)
        if getattr(self, "name", "") != "Pencil":
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._stroke_clip is not None:
            painter.setClipPath(self._stroke_clip.translated(-layer.offset.x(), -layer.offset.y()))
            
        mirror_x = bool(opts.get("brush_mirror_x", False))
        mirror_y = bool(opts.get("brush_mirror_y", False))
        cx_pct = float(opts.get("brush_mirror_cx", 0.5))
        cy_pct = float(opts.get("brush_mirror_cy", 0.5))
        doc_w, doc_h = doc.width, doc.height
        sym_x = doc_w * cx_pct
        sym_y = doc_h * cy_pct
        
        pairs = [((p1.x(), p1.y()), (p2.x(), p2.y()))]
        if mirror_x: pairs.extend([((2 * sym_x - a[0], a[1]), (2 * sym_x - b[0], b[1])) for a, b in pairs])
        if mirror_y: pairs.extend([((a[0], 2 * sym_y - a[1]), (b[0], 2 * sym_y - b[1])) for a, b in pairs])
        
        pen = QPen(c, size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        for a, b in list(dict.fromkeys(pairs)):
            painter.drawLine(QPoint(int(a[0] - layer.offset.x()), int(a[1] - layer.offset.y())), 
                             QPoint(int(b[0] - layer.offset.x()), int(b[1] - layer.offset.y())))
        painter.end()


class PatternStampTool(BrushTool):
    name     = "PatternStamp"
    icon     = "💠"
    shortcut = "S"


class EraserTool(BrushTool):
    name     = "Eraser"
    icon     = "🧽"
    shortcut = "E"

    def stroke_composition_mode(self, opts=None):
        return QPainter.CompositionMode.CompositionMode_DestinationOut


class CloneStampTool(BrushTool):
    name     = "CloneStamp"
    icon     = "⎘"
    shortcut = "S"

    def __init__(self):
        super().__init__()
        self._source_pos = None
        self._paint_offset = None
        self._source_img = None
        self._crosshair_pos = None

    def on_press(self, pos, doc, fg, bg, opts):
        if opts.get("_alt", False):
            self._source_pos = pos
            return
            
        if self._source_pos is None:
            return

        self._paint_offset = pos - self._source_pos
        layer = doc.get_active_layer()
        if not layer or layer.locked:
            return
        self._source_img = layer.image.copy()
        self._source_offset = layer.offset

        super().on_press(pos, doc, fg, bg, opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if opts.get("_alt", False):
            self._source_pos = pos
            return
        if self._source_pos is None or self._source_img is None:
            return
            
        self._crosshair_pos = pos - self._paint_offset
        super().on_move(pos, doc, fg, bg, opts)

    def on_release(self, pos, doc, fg, bg, opts):
        if opts.get("_alt", False) or self._source_pos is None or self._source_img is None:
            return
        super().on_release(pos, doc, fg, bg, opts)
        self._paint_offset = None
        self._source_img = None
        self._source_offset = None
        self._crosshair_pos = None

    def _paint(self, p1: QPoint, p2: QPoint, doc, color: QColor, opts: dict, press1: float = 1.0, press2: float = 1.0):
        layer = self._stroke_layer
        if not layer or layer.locked or self._stroke_img is None or self._source_img is None:
            return

        hardness = float(opts.get("brush_hardness", 1.0))
        mask     = opts.get("brush_mask", "round")
        angle    = float(opts.get("brush_angle", 0.0))
        angle_random = bool(opts.get("brush_angle_random", False))
        size_base = max(1, int(opts.get("brush_size", 10)))
        size_dyn = bool(opts.get("brush_size_dynamic", False))
        mirror_x = bool(opts.get("brush_mirror_x", False))
        mirror_y = bool(opts.get("brush_mirror_y", False))
        cx_pct = float(opts.get("brush_mirror_cx", 0.5))
        cy_pct = float(opts.get("brush_mirror_cy", 0.5))
        doc_w, doc_h = doc.width, doc.height
        sym_x = doc_w * cx_pct
        sym_y = doc_h * cy_pct

        step  = max(1, size_base // 3)
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        dist  = math.hypot(dx, dy)
        
        steps = 0 if dist == 0 else max(1, int(dist / step))
        start_i = 0 if dist == 0 else 1

        painter = QPainter(self._stroke_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._stroke_clip is not None:
            painter.setClipPath(self._stroke_clip.translated(-layer.offset.x(), -layer.offset.y()))
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        for i in range(start_i, steps + 1):
            t = 0 if steps == 0 else i / steps
            cur_press = press1 + (press2 - press1) * t
            cur_size = max(1, int(size_base * cur_press)) if size_dyn else size_base
            stamp = self._get_stamp(cur_size, hardness, mask)
            
            cx, cy = p1.x() + dx * t, p1.y() + dy * t
            
            centers_doc = [(cx, cy)]
            if mirror_x: centers_doc.extend([(2 * sym_x - c[0], c[1]) for c in centers_doc])
            if mirror_y: centers_doc.extend([(c[0], 2 * sym_y - c[1]) for c in centers_doc])
            
            for target_doc_cx, target_doc_cy in list(dict.fromkeys(centers_doc)):
                target_cx = target_doc_cx - layer.offset.x()
                target_cy = target_doc_cy - layer.offset.y()
                
                orig_src_doc_cx = target_doc_cx - self._paint_offset.x()
                orig_src_doc_cy = target_doc_cy - self._paint_offset.y()
                src_cx = orig_src_doc_cx - self._source_offset.x()
                src_cy = orig_src_doc_cy - self._source_offset.y()
                
                painter.save()
                painter.translate(target_cx, target_cy)
                current_angle = random.uniform(0, 360) if angle_random else angle
                if current_angle != 0.0:
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    painter.rotate(current_angle)
                painter.translate(-cur_size / 2.0, -cur_size / 2.0)
                
                patch = QImage(stamp.size(), QImage.Format.Format_ARGB32_Premultiplied)
                patch.fill(Qt.GlobalColor.transparent)
                
                pp = QPainter(patch)
                pp.drawImage(0, 0, stamp)
                pp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                pp.translate(cur_size / 2.0, cur_size / 2.0)
                pp.translate(-src_cx, -src_cy)
                pp.drawImage(0, 0, self._source_img)
                pp.end()
                
                if opts.get("brush_opacity_dynamic", False):
                    alpha_mask = QImage(patch.size(), QImage.Format.Format_ARGB32_Premultiplied)
                    alpha_mask.fill(QColor(0,0,0, int(255*cur_press)))
                    pp2 = QPainter(patch)
                    pp2.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                    pp2.drawImage(0, 0, alpha_mask)
                    pp2.end()
                
                painter.drawImage(0, 0, patch)
                painter.restore()

        painter.end()


class PencilTool(BrushTool):
    name     = "Pencil"
    icon     = "✏️"
    shortcut = "B"

    def _get_stamp(self, size: int, hardness: float, mask) -> QImage:
        # Карандаш всегда имеет 100% жесткость и бинарный альфа-канал
        stamp = super()._get_stamp(size, 1.0, mask).copy()
        import ctypes
        ptr = stamp.bits()
        buf = (ctypes.c_uint8 * stamp.sizeInBytes()).from_address(int(ptr))
        arr = np.ndarray((stamp.height(), stamp.bytesPerLine() // 4, 4), dtype=np.uint8, buffer=buf)
        arr[arr[..., 3] < 128, 3] = 0
        arr[arr[..., 3] >= 128, 3] = 255
        return stamp


class ColorReplacementTool(BrushTool):
    name     = "ColorReplacement"
    icon     = "🖌️🎨"
    shortcut = "B"

    def stroke_composition_mode(self, opts=None):
        # В Qt нет нативного режима Color, используем Overlay для сохранения текстуры слоя
        return QPainter.CompositionMode.CompositionMode_Overlay


class MixerBrushTool(BrushTool):
    name     = "MixerBrush"
    icon     = "🖌️💧"
    shortcut = "B"

    def __init__(self):
        super().__init__()
        self._mix_color = None

    def on_press(self, pos, doc, fg, bg, opts):
        self._mix_color = QColor(fg)
        super().on_press(pos, doc, self._mix_color, bg, opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if self._last_pos and self._target_img:
            cx, cy = pos.x(), pos.y()
            if 0 <= cx < self._target_img.width() and 0 <= cy < self._target_img.height():
                canvas_color = QColor(self._target_img.pixel(cx, cy))
                if canvas_color.alpha() > 0:
                    # Замедляем скорость смешивания для более предсказуемого результата
                    factor = 0.05
                    r = int(self._mix_color.red() * (1 - factor) + canvas_color.red() * factor)
                    g = int(self._mix_color.green() * (1 - factor) + canvas_color.green() * factor)
                    b = int(self._mix_color.blue() * (1 - factor) + canvas_color.blue() * factor)
                    self._mix_color = QColor(r, g, b, 255)
        
        super().on_move(pos, doc, self._mix_color, bg, opts)


class HistoryBrushTool(BrushTool):
    name     = "HistoryBrush"
    icon     = "🕰️"
    shortcut = "Y"

    def __init__(self):
        super().__init__()
        self._source_img = None

    def on_press(self, pos, doc, fg, bg, opts):
        layer = doc.get_active_layer()
        if not layer or layer.locked or getattr(layer, "lock_pixels", False):
            return

        history = getattr(doc, "history", None)
        if history and history._undo_stack:
            # Берём оригинальный снимок самого первого состояния документа
            initial_state = history._undo_stack[0]
            src_layer = next((l for l in initial_state.layers_snapshot if l.layer_id == layer.layer_id), None)
            if src_layer:
                self._source_img = src_layer.image.copy()
            elif initial_state.layers_snapshot:
                self._source_img = initial_state.layers_snapshot[0].image.copy()
        
        if not self._source_img:
            self._source_img = layer.image.copy()

        super().on_press(pos, doc, fg, bg, opts)

    def on_release(self, pos, doc, fg, bg, opts):
        super().on_release(pos, doc, fg, bg, opts)
        self._source_img = None

    def _paint(self, p1: QPoint, p2: QPoint, doc, color: QColor, opts: dict, press1: float = 1.0, press2: float = 1.0):
        if not self._source_img: return
        layer = self._stroke_layer
        if not layer or layer.locked or self._stroke_img is None:
            return

        hardness = float(opts.get("brush_hardness", 1.0))
        mask     = opts.get("brush_mask", "round")
        angle    = float(opts.get("brush_angle", 0.0))
        angle_random = bool(opts.get("brush_angle_random", False))
        size_base = max(1, int(opts.get("brush_size", 10)))
        size_dyn = bool(opts.get("brush_size_dynamic", False))
        mirror_x = bool(opts.get("brush_mirror_x", False))
        mirror_y = bool(opts.get("brush_mirror_y", False))
        cx_pct = float(opts.get("brush_mirror_cx", 0.5))
        cy_pct = float(opts.get("brush_mirror_cy", 0.5))
        doc_w, doc_h = doc.width, doc.height
        sym_x = doc_w * cx_pct
        sym_y = doc_h * cy_pct

        step  = max(1, size_base // 3)
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        dist  = math.hypot(dx, dy)
        
        steps = 0 if dist == 0 else max(1, int(dist / step))
        start_i = 0 if dist == 0 else 1

        painter = QPainter(self._stroke_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._stroke_clip is not None:
            painter.setClipPath(self._stroke_clip.translated(-layer.offset.x(), -layer.offset.y()))
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        for i in range(start_i, steps + 1):
            t = 0 if steps == 0 else i / steps
            cur_press = press1 + (press2 - press1) * t
            cur_size = max(1, int(size_base * cur_press)) if size_dyn else size_base
            stamp = self._get_stamp(cur_size, hardness, mask)
            
            cx, cy = p1.x() + dx * t, p1.y() + dy * t
            
            centers_doc = [(cx, cy)]
            if mirror_x: centers_doc.extend([(2 * sym_x - c[0], c[1]) for c in centers_doc])
            if mirror_y: centers_doc.extend([(c[0], 2 * sym_y - c[1]) for c in centers_doc])
            
            for target_doc_cx, target_doc_cy in list(dict.fromkeys(centers_doc)):
                target_cx = target_doc_cx - layer.offset.x()
                target_cy = target_doc_cy - layer.offset.y()
                painter.save()
                painter.translate(target_cx, target_cy)
                current_angle = random.uniform(0, 360) if angle_random else angle
                if current_angle != 0.0:
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    painter.rotate(current_angle)
                painter.translate(-cur_size / 2.0, -cur_size / 2.0)
                
                patch = QImage(stamp.size(), QImage.Format.Format_ARGB32_Premultiplied)
                patch.fill(Qt.GlobalColor.transparent)
                
                pp = QPainter(patch)
                pp.drawImage(0, 0, stamp)
                pp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                pp.translate(cur_size / 2.0, cur_size / 2.0)
                if current_angle != 0.0:
                    pp.rotate(-current_angle)  # Отменяем вращение кисти, чтобы текстура истории оставалась прямой
                pp.translate(-target_cx, -target_cy)
                pp.drawImage(0, 0, self._source_img)
                pp.end()
                
                if opts.get("brush_opacity_dynamic", False):
                    alpha_mask = QImage(patch.size(), QImage.Format.Format_ARGB32_Premultiplied)
                    alpha_mask.fill(QColor(0,0,0, int(255*cur_press)))
                    pp2 = QPainter(patch)
                    pp2.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                    pp2.drawImage(0, 0, alpha_mask)
                    pp2.end()
                
                painter.drawImage(0, 0, patch)
                painter.restore()

        painter.end()