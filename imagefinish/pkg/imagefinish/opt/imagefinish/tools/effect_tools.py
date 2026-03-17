"""
effect_tools.py — Blur, Sharpen, Smudge (палец).

Все три работают как кисть: зажал и тянешь.
Используют локальные операции над QImage через numpy (если есть)
или через pure-Qt fallback.
"""

from PyQt6.QtGui import QPainter, QColor, QImage, QPen
from PyQt6.QtCore import QPoint, QRect, Qt
from tools.base_tool import BaseTool

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ── helpers ───────────────────────────────────────────────────────────────────

def _clamp_rect(rect: QRect, w: int, h: int) -> QRect:
    x1 = max(0, rect.left())
    y1 = max(0, rect.top())
    x2 = min(w, rect.right() + 1)
    y2 = min(h, rect.bottom() + 1)
    return QRect(x1, y1, x2 - x1, y2 - y1)


def _qimage_to_np(img: QImage):
    """QImage ARGB32 → numpy (H, W, 4) uint8."""
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    import ctypes, numpy as np
    arr = np.empty((h, img.bytesPerLine() // 4, 4), dtype=np.uint8)
    ctypes.memmove(arr.ctypes.data, int(img.constBits()), img.sizeInBytes())
    return arr[:, :w, :]


def _np_to_qimage(arr) -> QImage:
    h, w = arr.shape[:2]
    import ctypes, numpy as np
    arr_c = np.ascontiguousarray(arr)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    ctypes.memmove(int(img.bits()), arr_c.ctypes.data, min(img.sizeInBytes(), arr_c.nbytes))
    return img


def _circle_mask(src_rect: QRect, cx: int, cy: int, r: int):
    """Float32 numpy mask (H, W, 1): 1.0 внутри круга, 0.0 снаружи."""
    pw, ph = src_rect.width(), src_rect.height()
    xs = np.arange(pw) + src_rect.left() - cx
    ys = np.arange(ph) + src_rect.top() - cy
    xx, yy = np.meshgrid(xs, ys)
    return (xx**2 + yy**2 <= r**2).astype(np.float32)[:, :, np.newaxis]


def _soft_circle_mask(src_rect: QRect, cx: int, cy: int, r: int):
    """Плавная радиальная маска (0.0 - 1.0) для мягкой кисти тонирования."""
    pw, ph = src_rect.width(), src_rect.height()
    xs = np.arange(pw) + src_rect.left() - cx
    ys = np.arange(ph) + src_rect.top() - cy
    xx, yy = np.meshgrid(xs, ys)
    dist = np.sqrt(xx**2 + yy**2)
    mask = np.clip(1.0 - (dist / max(1, r)), 0.0, 1.0)
    mask = mask * mask * (3.0 - 2.0 * mask) # Smoothstep
    return mask[:, :, np.newaxis].astype(np.float32)

def _box_blur_np(arr, radius: int):
    """Fast separable box blur на numpy."""
    from numpy import pad, cumsum
    r = max(1, radius)
    # horizontal pass
    padded = pad(arr.astype(np.float32), ((0,0),(r,r),(0,0)), mode='edge')
    cs = cumsum(padded, axis=1)
    blurred = (cs[:, 2*r:, :] - cs[:, :-2*r, :]) / (2*r)
    # vertical pass
    padded2 = pad(blurred, ((r,r),(0,0),(0,0)), mode='edge')
    cs2 = cumsum(padded2, axis=0)
    result = (cs2[2*r:, :, :] - cs2[:-2*r, :, :]) / (2*r)
    return result.clip(0, 255).astype(np.uint8)


def _sharpen_np(arr, strength: float = 1.0):
    """Unsharp mask: result = orig + strength*(orig - blurred)."""
    blurred = _box_blur_np(arr, 2)
    detail = arr.astype(np.float32) - blurred.astype(np.float32)
    result = arr.astype(np.float32) + strength * detail
    return result.clip(0, 255).astype(np.uint8)


# ── Qt-only fallback (без numpy): просто усредняем пиксели в радиусе ──────────

def _apply_qt_blur(image: QImage, cx: int, cy: int, radius: int, passes: int = 2):
    """Размываем круговую область вокруг (cx, cy) простым box blur."""
    r = radius
    rect = _clamp_rect(QRect(cx - r, cy - r, 2*r, 2*r), image.width(), image.height())
    if rect.isEmpty():
        return
    for _ in range(passes):
        for y in range(rect.top(), rect.bottom()):
            for x in range(rect.left(), rect.right()):
                # усредняем 3x3
                rs = gs = bs = als = n = 0
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        nx_, ny_ = x + dx, y + dy
                        if 0 <= nx_ < image.width() and 0 <= ny_ < image.height():
                            c = QColor(image.pixel(nx_, ny_))
                            rs += c.red(); gs += c.green()
                            bs += c.blue(); als += c.alpha()
                            n += 1
                if n:
                    image.setPixel(x, y, QColor(rs//n, gs//n, bs//n, als//n).rgba())


# ═══════════════════════════════════════════════════════════════ BlurTool
class BlurTool(BaseTool):
    """
    Размытие кистью. Зажал — размываешь всё под курсором.
    Использует numpy если доступен, иначе Qt fallback.
    """
    name     = "Blur"
    icon     = "💧"
    shortcut = "R"
    modifies_canvas_on_move = True

    def __init__(self):
        self._last: QPoint | None = None

    def on_press(self, pos, doc, fg, bg, opts):
        self._last = pos
        self._apply(pos, doc, opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if self._last:
            self._apply(pos, doc, opts)
        self._last = pos

    def on_release(self, pos, doc, fg, bg, opts):
        self._last = None

    def _apply(self, pos: QPoint, doc, opts: dict):
        layer = doc.get_active_layer()
        if not layer or layer.locked:
            return
        size     = max(4, int(opts.get("brush_size", 20)))
        strength = float(opts.get("effect_strength", 0.5))
        radius   = max(1, int(size * strength * 0.5))

        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()
        clip = doc.selection if (doc.selection and not doc.selection.isEmpty()) else None

        if _HAS_NUMPY:
            r = size // 2
            src_rect = _clamp_rect(
                QRect(cx - r, cy - r, size, size),
                layer.image.width(), layer.image.height())
            if clip:
                src_rect = src_rect.intersected(clip.boundingRect().toRect().translated(-layer.offset))
            if src_rect.isEmpty():
                return
            patch = _qimage_to_np(layer.image.copy(src_rect))
            blurred = _box_blur_np(patch, radius)
            # blend с оригиналом по strength, только внутри круга
            circle = _circle_mask(src_rect, cx, cy, r)
            blended = (patch.astype(float) * (1 - strength * circle) +
                       blurred.astype(float) * (strength * circle)).clip(0, 255).astype('uint8')
            result_img = _np_to_qimage(blended)
            p = QPainter(layer.image)
            if clip:
                p.setClipPath(clip.translated(-layer.offset.x(), -layer.offset.y()))
            p.drawImage(src_rect.topLeft(), result_img)
            p.end()
        else:
            _apply_qt_blur(layer.image, cx, cy, size // 2)


# ═══════════════════════════════════════════════════════════════ SharpenTool
class SharpenTool(BaseTool):
    """Резкость — противоположность размытию."""
    name     = "Sharpen"
    icon     = "🔺"
    shortcut = "Y"
    modifies_canvas_on_move = True

    def __init__(self):
        self._last: QPoint | None = None

    def on_press(self, pos, doc, fg, bg, opts):
        self._last = pos
        self._apply(pos, doc, opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if self._last:
            self._apply(pos, doc, opts)
        self._last = pos

    def on_release(self, pos, doc, fg, bg, opts):
        self._last = None

    def _apply(self, pos: QPoint, doc, opts: dict):
        if not _HAS_NUMPY:
            return  # резкость без numpy не делаем
        layer = doc.get_active_layer()
        if not layer or layer.locked:
            return
        size     = max(4, int(opts.get("brush_size", 20)))
        strength = float(opts.get("effect_strength", 1.0))

        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()
        clip = doc.selection if (doc.selection and not doc.selection.isEmpty()) else None

        r = size // 2
        src_rect = _clamp_rect(
            QRect(cx - r, cy - r, size, size),
            layer.image.width(), layer.image.height())
        if clip:
                src_rect = src_rect.intersected(clip.boundingRect().toRect().translated(-layer.offset))
        if src_rect.isEmpty():
            return
        patch = _qimage_to_np(layer.image.copy(src_rect))
        sharpened = _sharpen_np(patch, strength)
        circle = _circle_mask(src_rect, cx, cy, r)
        blended = (patch.astype(float) * (1 - circle) +
                   sharpened.astype(float) * circle).clip(0, 255).astype('uint8')
        result_img = _np_to_qimage(blended)
        p = QPainter(layer.image)
        if clip:
            p.setClipPath(clip.translated(-layer.offset.x(), -layer.offset.y()))
        p.drawImage(src_rect.topLeft(), result_img)
        p.end()


# ═══════════════════════════════════════════════════════════════ SmudgeTool
class SmudgeTool(BaseTool):
    """
    Палец — размазывает цвет по направлению движения.
    Тащит «каплю» пикселей за кистью.
    """
    name     = "Smudge"
    icon     = "👆"
    shortcut = "W"
    modifies_canvas_on_move = True

    def __init__(self):
        self._last:  QPoint | None = None
        self._color: QColor | None = None   # цвет под кистью в начале мазка

    def on_press(self, pos, doc, fg, bg, opts):
        self._last = pos
        layer = doc.get_active_layer()
        if layer:
            x, y = pos.x(), pos.y()
            if 0 <= x < layer.width() and 0 <= y < layer.height():
                self._color = QColor(layer.image.pixel(x, y))
            else:
                self._color = QColor(0, 0, 0, 0)

    def on_move(self, pos, doc, fg, bg, opts):
        if not self._last or not self._color:
            return
        layer = doc.get_active_layer()
        if not layer or layer.locked:
            self._last = pos
            return

        size     = max(2, int(opts.get("brush_size", 16)))
        strength = float(opts.get("effect_strength", 0.7))
        clip = doc.selection if (doc.selection and not doc.selection.isEmpty()) else None

        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()

        if _HAS_NUMPY:
            r = size // 2
            src_rect = _clamp_rect(
                QRect(cx - r, cy - r, size, size),
                layer.image.width(), layer.image.height())
            if clip:
                src_rect = src_rect.intersected(clip.boundingRect().toRect().translated(-layer.offset))
            if not src_rect.isEmpty():
                patch = _qimage_to_np(layer.image.copy(src_rect))
                # Смешиваем пиксели патча с «каплей» цвета, только внутри круга
                smudge = np.array([self._color.blue(), self._color.green(),
                                   self._color.red(), self._color.alpha()],
                                  dtype=np.float32)
                circle = _circle_mask(src_rect, cx, cy, r)
                blended = (patch.astype(float) * (1 - strength * circle) +
                           smudge * (strength * circle)).clip(0, 255).astype('uint8')
                result_img = _np_to_qimage(blended)
                p = QPainter(layer.image)
                if clip:
                    p.setClipPath(clip.translated(-layer.offset.x(), -layer.offset.y()))
                p.drawImage(src_rect.topLeft(), result_img)
                p.end()
                # Обновляем «каплю» — берём усреднённый цвет патча
                avg = patch.mean(axis=(0, 1))
                self._color = QColor(int(avg[2]), int(avg[1]),
                                     int(avg[0]), int(avg[3]))
        else:
            # Qt fallback: рисуем кружок с цветом «капли»
            p = QPainter(layer.image)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if clip:
                p.setClipPath(clip.translated(-layer.offset.x(), -layer.offset.y()))
            c = QColor(self._color)
            c.setAlphaF(strength * 0.6)
            pen = QPen(c, size, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawLine(self._last - layer.offset, pos - layer.offset)
            p.end()
            # обновляем каплю
            x, y = pos.x(), pos.y()
            if 0 <= x < layer.width() and 0 <= y < layer.height():
                orig = QColor(layer.image.pixel(x, y))
                self._color = QColor(
                    int(orig.red()   * (1-strength) + self._color.red()   * strength),
                    int(orig.green() * (1-strength) + self._color.green() * strength),
                    int(orig.blue()  * (1-strength) + self._color.blue()  * strength),
                )

        self._last = pos

    def on_release(self, pos, doc, fg, bg, opts):
        self._last  = None
        self._color = None


# ═══════════════════════════════════════════════════════════════ DodgeTool
class DodgeTool(BaseTool):
    name     = "Dodge"
    icon     = "🌔"
    shortcut = "O"
    modifies_canvas_on_move = True

    def __init__(self):
        self._last: QPoint | None = None

    def on_press(self, pos, doc, fg, bg, opts):
        self._last = pos
        self._apply(pos, doc, opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if self._last: self._apply(pos, doc, opts)
        self._last = pos

    def on_release(self, pos, doc, fg, bg, opts):
        self._last = None

    def _apply(self, pos: QPoint, doc, opts: dict):
        if not _HAS_NUMPY: return
        layer = doc.get_active_layer()
        if not layer or layer.locked: return
        
        size = max(4, int(opts.get("brush_size", 20)))
        strength = float(opts.get("effect_strength", 0.5))
        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()
        clip = doc.selection if (doc.selection and not doc.selection.isEmpty()) else None

        r = size // 2
        src_rect = _clamp_rect(QRect(cx - r, cy - r, size, size), layer.image.width(), layer.image.height())
        if clip: src_rect = src_rect.intersected(clip.boundingRect().toRect().translated(-layer.offset))
        if src_rect.isEmpty(): return

        patch = _qimage_to_np(layer.image.copy(src_rect))
        circle = _soft_circle_mask(src_rect, cx, cy, r)
        
        rgb = patch[..., :3].astype(np.float32)
        factor = strength * 0.2 * circle
        res_rgb = rgb + (255.0 - rgb) * factor
        patch[..., :3] = np.clip(res_rgb, 0, 255).astype(np.uint8)
        
        result_img = _np_to_qimage(patch)
        p = QPainter(layer.image)
        if clip: p.setClipPath(clip.translated(-layer.offset.x(), -layer.offset.y()))
        p.drawImage(src_rect.topLeft(), result_img)
        p.end()


# ═══════════════════════════════════════════════════════════════ BurnTool
class BurnTool(BaseTool):
    name     = "Burn"
    icon     = "🌒"
    shortcut = "O"
    modifies_canvas_on_move = True

    def __init__(self):
        self._last: QPoint | None = None

    def on_press(self, pos, doc, fg, bg, opts):
        self._last = pos
        self._apply(pos, doc, opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if self._last: self._apply(pos, doc, opts)
        self._last = pos

    def on_release(self, pos, doc, fg, bg, opts):
        self._last = None

    def _apply(self, pos: QPoint, doc, opts: dict):
        if not _HAS_NUMPY: return
        layer = doc.get_active_layer()
        if not layer or layer.locked: return
        
        size = max(4, int(opts.get("brush_size", 20)))
        strength = float(opts.get("effect_strength", 0.5))
        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()
        r = size // 2
        clip = doc.selection if (doc.selection and not doc.selection.isEmpty()) else None

        src_rect = _clamp_rect(QRect(cx - r, cy - r, size, size), layer.image.width(), layer.image.height())
        if clip: src_rect = src_rect.intersected(clip.boundingRect().toRect().translated(-layer.offset))
        if src_rect.isEmpty(): return

        patch = _qimage_to_np(layer.image.copy(src_rect))
        circle = _soft_circle_mask(src_rect, cx, cy, r)
        
        rgb = patch[..., :3].astype(np.float32)
        factor = strength * 0.2 * circle
        res_rgb = rgb * (1.0 - factor)
        patch[..., :3] = np.clip(res_rgb, 0, 255).astype(np.uint8)
        
        result_img = _np_to_qimage(patch)
        p = QPainter(layer.image)
        if clip: p.setClipPath(clip.translated(-layer.offset.x(), -layer.offset.y()))
        p.drawImage(src_rect.topLeft(), result_img)
        p.end()


# ═══════════════════════════════════════════════════════════════ SpongeTool
class SpongeTool(BaseTool):
    name     = "Sponge"
    icon     = "🧽"
    shortcut = "O"
    modifies_canvas_on_move = True

    def __init__(self):
        self._last: QPoint | None = None

    def on_press(self, pos, doc, fg, bg, opts):
        self._last = pos
        self._apply(pos, doc, opts)

    def on_move(self, pos, doc, fg, bg, opts):
        if self._last: self._apply(pos, doc, opts)
        self._last = pos

    def on_release(self, pos, doc, fg, bg, opts):
        self._last = None

    def _apply(self, pos: QPoint, doc, opts: dict):
        if not _HAS_NUMPY: return
        layer = doc.get_active_layer()
        if not layer or layer.locked: return
        
        size = max(4, int(opts.get("brush_size", 20)))
        strength = float(opts.get("effect_strength", 0.5))
        mode = opts.get("sponge_mode", "desaturate")
        cx, cy = pos.x() - layer.offset.x(), pos.y() - layer.offset.y()
        r = size // 2
        clip = doc.selection if (doc.selection and not doc.selection.isEmpty()) else None

        src_rect = _clamp_rect(QRect(cx - r, cy - r, size, size), layer.image.width(), layer.image.height())
        if clip: src_rect = src_rect.intersected(clip.boundingRect().toRect().translated(-layer.offset))
        if src_rect.isEmpty(): return

        patch = _qimage_to_np(layer.image.copy(src_rect))
        circle = _soft_circle_mask(src_rect, cx, cy, r)
        
        rgb = patch[..., :3].astype(np.float32)
        gray = (0.114 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.299 * rgb[..., 2])[..., np.newaxis]
        factor = strength * 0.2 * circle
        
        if mode == "desaturate":
            res_rgb = rgb * (1.0 - factor) + gray * factor
        else:
            res_rgb = rgb + (rgb - gray) * factor
            
        patch[..., :3] = np.clip(res_rgb, 0, 255).astype(np.uint8)
        
        result_img = _np_to_qimage(patch)
        p = QPainter(layer.image)
        if clip: p.setClipPath(clip.translated(-layer.offset.x(), -layer.offset.y()))
        p.drawImage(src_rect.topLeft(), result_img)
        p.end()
