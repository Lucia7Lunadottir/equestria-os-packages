"""HDR Toning — local tone-compression to simulate HDR look.

Algorithm:
  1. Gaussian-blur the image (3× box-blur passes ≈ Gaussian).
  2. High-frequency detail = original - blurred.
  3. Enhanced = blurred^gamma  +  detail_hf * (1 + detail).
  4. Blend with original by *strength*.

Performance strategy (dialog):
  • Pixel data is pre-extracted as float32 once in __init__.
  • The blur — the only expensive step — is cached by radius.
    Dragging Strength / Gamma / Detail costs only fast numpy ops (~5 ms).
    Dragging Radius recomputes the blur once and caches it.
"""

from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _const_arr, _in_place_arr, _AdjustDialog
from core.adjustments._widgets import _FSliderRow


# ── separable box-blur (O(n) via cumulative sum) ──────────────────────────────

def _box_blur_ch(ch, r):
    """2-D separable box blur of a 2-D float32 array."""
    import numpy as np
    h, w = ch.shape
    r = max(1, min(r, min(h, w) // 2 - 1))

    cs = np.cumsum(ch, axis=1, dtype=np.float32)
    cs = np.hstack([np.zeros((h, 1), dtype=np.float32), cs])
    e  = np.minimum(np.arange(w) + r + 1, w)
    s  = np.maximum(np.arange(w) - r,     0)
    row = (cs[:, e] - cs[:, s]) / (e - s).astype(np.float32)

    cs2 = np.cumsum(row, axis=0, dtype=np.float32)
    cs2 = np.vstack([np.zeros((1, w), dtype=np.float32), cs2])
    ev  = np.minimum(np.arange(h) + r + 1, h)          # 1-D (h,)
    sv  = np.maximum(np.arange(h) - r,     0)          # 1-D (h,)
    col = (cs2[ev, :] - cs2[sv, :])                    # (h, w)
    col /= (ev - sv).astype(np.float32).reshape(-1, 1) # broadcast /= (h,1)
    return col.astype(np.float32)


def _gauss_blur(arr_f, r):
    """Approximate Gaussian blur via 3 box-blur passes on each channel.
    arr_f: H×W×3 float32, r: kernel half-width."""
    import numpy as np
    out = np.empty_like(arr_f)
    for c in range(3):
        ch = arr_f[:, :, c]
        ch = _box_blur_ch(ch, r)
        ch = _box_blur_ch(ch, r)
        ch = _box_blur_ch(ch, r)
        out[:, :, c] = ch
    return out


# ── standalone apply function (correct; used for final commit & fallback) ─────

def apply_hdr_toning(src: QImage, radius: int, strength: float,
                     gamma: float, detail: float) -> QImage:
    """
    radius   : 1..500   blur kernel half-width
    strength : 0..1     blend factor
    gamma    : 0.1..3.0 gamma applied to the blurred (low-freq) image
    detail   : 0..1     local contrast boost
    """
    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        arr = _in_place_arr(img)
        orig_f = arr[:, :, :3].astype(np.float32) / 255.0

        blurred = np.clip(_gauss_blur(orig_f, max(1, int(radius))), 0.0, 1.0)
        result  = _hdr_combine(np, orig_f, blurred, strength, gamma, detail)

        arr[:, :, :3] = result
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    except ImportError:
        return _hdr_fallback(img, radius, strength, gamma, detail)


def _hdr_combine(np, orig_f, blurred, strength, gamma, detail):
    """Fast numpy core shared by standalone function and dialog preview."""
    inv_gamma  = 1.0 / max(gamma, 0.001)
    blurred_g  = np.power(blurred, inv_gamma)          # gamma on low-freq
    hf         = orig_f - blurred                      # high-freq detail
    enhanced   = np.clip(blurred_g + hf * (1.0 + detail), 0.0, 1.0)
    result     = orig_f + (enhanced - orig_f) * strength
    return np.clip(result * 255.0, 0, 255).astype(np.uint8)


def _hdr_fallback(img, radius, strength, gamma, detail):
    """Qt-only fallback (no numpy): coarse blur via rescale."""
    from PyQt6.QtCore import Qt
    w, h = img.width(), img.height()
    factor  = max(2, min(16, radius // 10 + 2))
    sw, sh  = max(1, w // factor), max(1, h // factor)
    small   = img.scaled(sw, sh,
                         Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    blurred = small.scaled(w, h,
                           Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    blurred = blurred.convertToFormat(QImage.Format.Format_ARGB32)
    result  = img.copy()
    gi = 1.0 / max(gamma, 0.001)
    for y in range(h):
        for x in range(w):
            sp = img.pixel(x, y)
            bp = blurred.pixel(x, y)
            a  = (sp >> 24) & 0xFF
            px = a << 24
            for shift in (16, 8, 0):
                co = ((sp >> shift) & 0xFF) / 255.0
                cb = ((bp >> shift) & 0xFF) / 255.0
                enh = min(1.0, max(0.0, cb ** gi + (co - cb) * (1.0 + detail)))
                out = co + (enh - co) * strength
                px |= int(max(0, min(255, out * 255.0))) << shift
            result.setPixel(x, y, px)
    return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


# ── dialog ─────────────────────────────────────────────────────────────────────

class HDRToningDialog(_AdjustDialog):
    """HDR Toning dialog with real-time preview.

    Optimisations
    -------------
    • _orig_bgr / _orig_f / _orig_alpha: extracted once in __init__.
    • _blur_cache: expensive blur recomputed only when Radius changes.
      All other sliders use fast numpy ops on the cached blur array.
    """

    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.hdr.title"), layer, canvas_refresh, parent)

        # Pre-extract pixel data once (like _orig_argb32 in base class)
        self._np_ok = False
        try:
            import numpy as np
            _arr = _const_arr(self._orig_argb32)
            self._orig_bgr   = np.ascontiguousarray(_arr[:, :, :3])  # BGR uint8
            self._orig_f     = self._orig_bgr.astype(np.float32) / 255.0
            self._orig_alpha = _arr[:, :, 3].copy()
            self._np_ok = True
        except ImportError:
            pass

        # Blur cache — invalidated when Radius slider changes
        self._blur_radius = None
        self._blur_cache  = None   # H×W×3 float32, blur of _orig_f

        self._radius   = _FSliderRow(tr("adj.hdr.radius"),    1, 500, 50,  1.0,   0)
        self._strength = _FSliderRow(tr("adj.hdr.strength"),  0, 100, 50,  1.0,   0)
        self._gamma    = _FSliderRow(tr("adj.hdr.gamma"),    10, 300, 100, 100.0, 2)
        self._detail   = _FSliderRow(tr("adj.hdr.detail"),    0, 100,  0,  1.0,   0)

        for row in (self._radius, self._strength, self._gamma, self._detail):
            self._add_row(row)
        self._seal(reset_fn=self._reset)

    def _reset(self):
        for row in (self._radius, self._strength, self._gamma, self._detail):
            row.reset()

    def _apply_preview(self):
        if not self._np_ok:
            # No numpy — delegate to standalone function (slow but correct)
            self._layer.image = apply_hdr_toning(
                self._orig_argb32,
                radius   = int(self._radius.value()),
                strength = self._strength.value() / 100.0,
                gamma    = self._gamma.value(),
                detail   = self._detail.value() / 100.0,
            )
            self._canvas_refresh()
            return

        import numpy as np

        radius   = int(self._radius.value())
        strength = self._strength.value() / 100.0
        gamma    = self._gamma.value()
        detail   = self._detail.value() / 100.0

        # ── 1. Blur (cached by radius) ────────────────────────────────────
        if self._blur_radius != radius:
            self._blur_radius = radius
            self._blur_cache  = np.clip(
                _gauss_blur(self._orig_f, max(1, radius)), 0.0, 1.0)

        # ── 2. Gamma + detail + blend (fast, no blur needed) ─────────────
        result_u8 = _hdr_combine(
            np, self._orig_f, self._blur_cache, strength, gamma, detail)

        # ── 3. Write output (preserve alpha) ─────────────────────────────
        h, w = self._orig_argb32.height(), self._orig_argb32.width()
        out = np.empty((h, w, 4), dtype=np.uint8)
        out[:, :, :3] = result_u8
        out[:, :,  3] = self._orig_alpha
        
        new_img = QImage(w, h, QImage.Format.Format_ARGB32)
        import ctypes
        ctypes.memmove(int(new_img.bits()), out.ctypes.data, new_img.sizeInBytes())
        self._layer.image = new_img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        self._canvas_refresh()
