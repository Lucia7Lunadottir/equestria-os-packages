"""core/filters/blur_filters.py — Gaussian blur filter + dialog."""

import math

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox
from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _AdjustDialog, _SliderRow, _to_argb32, _from_ba, _bits_ba


# ── numpy helpers ─────────────────────────────────────────────────────────────

def _box_blur_channel(ch, r: int):
    """2-D box blur via cumsum — O(n) regardless of r."""
    import numpy as np
    if r == 0:
        return ch.astype(np.float32)
    h, w = ch.shape
    f = ch.astype(np.float32)
    # Horizontal pass
    # Prepend zero column so that cs0[j] = sum of pad[0..j-1] (exclusive-end indexing)
    pad  = np.pad(f, ((0, 0), (r, r)), mode='edge')           # (h, w+2r)
    cs   = np.cumsum(pad, axis=1)                              # (h, w+2r)
    cs0  = np.concatenate([np.zeros((h, 1), dtype=np.float32), cs], axis=1)  # (h, w+2r+1)
    f    = (cs0[:, 2*r+1:2*r+1+w] - cs0[:, :w]) / (2*r + 1)  # (h, w)
    # Vertical pass
    pad  = np.pad(f, ((r, r), (0, 0)), mode='edge')            # (h+2r, w)
    cs   = np.cumsum(pad, axis=0)                              # (h+2r, w)
    cs0  = np.concatenate([np.zeros((1, w), dtype=np.float32), cs], axis=0)  # (h+2r+1, w)
    return (cs0[2*r+1:2*r+1+h, :] - cs0[:h, :]) / (2*r + 1)  # (h, w)


def _approx_gaussian_np(ch, sigma: float):
    """Three-pass box blur ≈ Gaussian (Kovesi algorithm, O(n))."""
    import numpy as np
    n  = 3
    wl = int(math.floor(math.sqrt((12 * sigma**2 / n) + 1)))
    if wl % 2 == 0:
        wl -= 1
    wl = max(wl, 1)
    wu = wl + 2
    m  = max(0, min(n, round(
        (12 * sigma**2 - n * wl**2 - 4 * n * wl - 3 * n) / (-4 * wl - 4)
    )))
    f = ch.astype(np.float32)
    for i in range(n):
        r = (wl if i < m else wu) // 2
        f = _box_blur_channel(f, r)
    return f


# ── apply function ────────────────────────────────────────────────────────────

def apply_gaussian_blur(src: QImage, radius: float) -> QImage:
    """Gaussian blur. radius in [0.1, 250] pixels. Alpha channel preserved."""
    if radius < 0.1:
        return src.copy()
    img   = _to_argb32(src)
    sigma = max(radius, 0.1)

    try:
        import numpy as np
        ba, arr = _bits_ba(img)

        try:
            from scipy.ndimage import gaussian_filter
            for c in range(3):  # BGR only — preserve alpha
                arr[:, :, c] = np.clip(
                    gaussian_filter(arr[:, :, c].astype(np.float32), sigma), 0, 255
                ).astype(np.uint8)
        except ImportError:
            for c in range(3):
                arr[:, :, c] = np.clip(
                    _approx_gaussian_np(arr[:, :, c], sigma), 0, 255
                ).astype(np.uint8)

        return _from_ba(ba, img)

    except ImportError:
        # Slow Python fallback: repeated 3×3 box blur
        passes = max(1, int(sigma / 1.5))
        for _ in range(passes):
            for y in range(1, img.height() - 1):
                for x in range(1, img.width() - 1):
                    r = g = b = 0
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            px = img.pixel(x + dx, y + dy)
                            r += (px >> 16) & 0xFF
                            g += (px >>  8) & 0xFF
                            b +=  px        & 0xFF
                    a = (img.pixel(x, y) >> 24) & 0xFF
                    img.setPixel(x, y,
                        (a << 24) | ((r // 9) << 16) | ((g // 9) << 8) | (b // 9))
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


# ── dialog ────────────────────────────────────────────────────────────────────

class GaussianBlurDialog(_AdjustDialog):
    """Gaussian Blur dialog with live preview. Radius 0.1–250 px."""

    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("flt.gaussian.title"), layer, canvas_refresh, parent)
        # Slider 1..2500 → displayed as value/10 = 0.1..250.0
        self._radius = _SliderRow(tr("flt.radius_px"), 1, 2500, 10)
        self._add_row(self._radius)
        self._seal(reset_fn=self._reset)
        # Show one decimal place instead of the raw integer
        self._radius._slider.valueChanged.connect(self._update_label)
        self._update_label(self._radius.value())

    def _update_label(self, v: int):
        self._radius._val_lbl.setText(f"{v / 10:.1f}")

    def _reset(self):
        self._radius.reset()
        self._layer.image = self._original.copy()
        self._canvas_refresh()

    def _apply_preview(self):
        self._layer.image = apply_gaussian_blur(
            self._orig_argb32, self._radius.value() / 10.0
        )
        self._canvas_refresh()


def apply_average(src: QImage) -> QImage:
    img = _to_argb32(src)
    try:
        import numpy as np
        ba, arr = _bits_ba(img)
        for c in range(3):
            arr[:, :, c] = int(arr[:, :, c].mean())
        return _from_ba(ba, img)
    except ImportError:
        total_r = total_g = total_b = 0
        n = img.width() * img.height()
        for y in range(img.height()):
            for x in range(img.width()):
                px = img.pixel(x, y)
                total_r += (px >> 16) & 0xFF
                total_g += (px >>  8) & 0xFF
                total_b +=  px        & 0xFF
        r, g, b = total_r // n, total_g // n, total_b // n
        img.fill((0xFF << 24) | (r << 16) | (g << 8) | b)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def apply_blur(src: QImage) -> QImage:
    return apply_gaussian_blur(src, 1.0)


def apply_blur_more(src: QImage) -> QImage:
    return apply_gaussian_blur(src, 3.0)


def apply_box_blur(src: QImage, radius: int) -> QImage:
    img = _to_argb32(src)
    r = max(1, radius)
    try:
        import numpy as np
        ba, arr = _bits_ba(img)
        for c in range(3):
            arr[:, :, c] = np.clip(_box_blur_channel(arr[:, :, c], r), 0, 255).astype(np.uint8)
        return _from_ba(ba, img)
    except ImportError:
        return apply_gaussian_blur(src, float(r))


class BoxBlurDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("flt.box.title"), layer, canvas_refresh, parent)
        self._radius = _SliderRow(tr("flt.radius_px"), 1, 100, 5)
        self._add_row(self._radius)
        self._seal(reset_fn=self._reset)

    def _reset(self):
        self._radius.reset()
        self._layer.image = self._original.copy()
        self._canvas_refresh()

    def _apply_preview(self):
        self._layer.image = apply_box_blur(self._orig_argb32, self._radius.value())
        self._canvas_refresh()


def apply_smart_blur(src: QImage, radius: int, threshold: int) -> QImage:
    img = _to_argb32(src)
    r = max(1, radius)
    try:
        import numpy as np
        ba, arr = _bits_ba(img)
        h, w = arr.shape[:2]

        # Luminance for edge detection (BGRA layout: B=0 G=1 R=2)
        lum = (0.114 * arr[:, :, 0] + 0.587 * arr[:, :, 1]
               + 0.299 * arr[:, :, 2]).astype(np.float32)

        # Local std_dev via box filter on lum and lum² — O(n) for any radius
        mean_l    = _box_blur_channel(lum, r)
        mean_l_sq = _box_blur_channel(lum * lum, r)
        std       = np.sqrt(np.maximum(mean_l_sq - mean_l * mean_l, 0.0))

        # threshold slider 0-100 → pixel std_dev 0-127
        smooth = std < (threshold * 1.27)

        for c in range(3):
            ch = arr[:, :, c].astype(np.float32)
            blurred = _box_blur_channel(ch, r)
            arr[:, :, c] = np.where(smooth, np.clip(blurred, 0, 255), ch).astype(np.uint8)

        return _from_ba(ba, img)
    except ImportError:
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def apply_surface_blur(src: QImage, radius: int, threshold: int) -> QImage:
    img = _to_argb32(src)
    r = max(1, radius)
    try:
        import numpy as np
        ba, arr = _bits_ba(img)
        h, w = arr.shape[:2]

        lum = (0.114 * arr[:, :, 0] + 0.587 * arr[:, :, 1]
               + 0.299 * arr[:, :, 2]).astype(np.float32)
        mean_l    = _box_blur_channel(lum, r)
        mean_l_sq = _box_blur_channel(lum * lum, r)
        std       = np.sqrt(np.maximum(mean_l_sq - mean_l * mean_l, 0.0))

        t_px  = max(1.0, threshold * 1.27)
        alpha = 1.0 / (1.0 + (std / t_px) ** 2)   # Cauchy: 1 on flat, 0 on edge

        for c in range(3):
            ch = arr[:, :, c].astype(np.float32)
            blurred = _box_blur_channel(ch, r)
            arr[:, :, c] = np.clip(alpha * blurred + (1.0 - alpha) * ch, 0, 255).astype(np.uint8)

        return _from_ba(ba, img)
    except ImportError:
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class SurfaceBlurDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("flt.surface.title"), layer, canvas_refresh, parent)
        self._radius    = _SliderRow(tr("flt.radius"),    1, 100, 5)
        self._threshold = _SliderRow(tr("flt.threshold"), 1, 100, 15)
        self._add_row(self._radius)
        self._add_row(self._threshold)
        self._seal(reset_fn=self._reset)

    def _reset(self):
        self._radius.reset()
        self._threshold.reset()
        self._layer.image = self._original.copy()
        self._canvas_refresh()

    def _apply_preview(self):
        self._layer.image = apply_surface_blur(
            self._orig_argb32,
            self._radius.value(),
            self._threshold.value(),
        )
        self._canvas_refresh()


class SmartBlurDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("flt.smart.title"), layer, canvas_refresh, parent)
        self._radius    = _SliderRow(tr("flt.radius"),    1, 100, 5)
        self._threshold = _SliderRow(tr("flt.threshold"), 0, 100, 15)
        self._add_row(self._radius)
        self._add_row(self._threshold)
        self._seal(reset_fn=self._reset)

    def _reset(self):
        self._radius.reset()
        self._threshold.reset()
        self._layer.image = self._original.copy()
        self._canvas_refresh()

    def _apply_preview(self):
        self._layer.image = apply_smart_blur(
            self._orig_argb32,
            self._radius.value(),
            self._threshold.value(),
        )
        self._canvas_refresh()


_SHAPES = ("Circle", "Square", "Triangle", "Diamond")
_SHAPE_KEYS = ("flt.shape.circle", "flt.shape.square", "flt.shape.triangle", "flt.shape.diamond")


def _shape_kernel(shape: str, r: int):
    import numpy as np
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    if shape == "Circle":
        mask = x * x + y * y <= r * r
    elif shape == "Square":
        mask = np.ones((2 * r + 1, 2 * r + 1), dtype=bool)
    elif shape == "Triangle":
        mask = (np.abs(x) * 2 <= y + r)
    else:  # Diamond
        mask = np.abs(x) + np.abs(y) <= r
    k = mask.astype(np.float32)
    total = k.sum()
    return k / total if total > 0 else k


def apply_shape_blur(src: QImage, radius: int, shape: str) -> QImage:
    img = _to_argb32(src)
    r = max(1, radius)
    try:
        import numpy as np
        from numpy.fft import rfft2, irfft2

        ba, arr  = _bits_ba(img)
        kernel   = _shape_kernel(shape, r)
        pad      = r
        h, w     = arr.shape[:2]

        padded0  = np.pad(arr[:, :, 0].astype(np.float32), pad, mode='edge')
        ph, pw   = padded0.shape

        k            = np.zeros((ph, pw), dtype=np.float32)
        kh, kw       = kernel.shape
        k[:kh, :kw]  = kernel
        k            = np.roll(np.roll(k, -pad, axis=0), -pad, axis=1)
        K_fft        = rfft2(k)

        for c in range(3):
            padded  = np.pad(arr[:, :, c].astype(np.float32), pad, mode='edge')
            blurred = irfft2(rfft2(padded) * K_fft, s=padded.shape)
            arr[:, :, c] = np.clip(blurred[pad:pad + h, pad:pad + w], 0, 255).astype(np.uint8)

        return _from_ba(ba, img)
    except ImportError:
        return apply_gaussian_blur(src, float(r))


class ShapeBlurDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("flt.shape.title"), layer, canvas_refresh, parent)

        row = QHBoxLayout()
        lbl = QLabel(tr("flt.shape.shape"))
        lbl.setFixedWidth(90)
        self._shape_combo = QComboBox()
        self._shape_combo.addItems([tr(k) for k in _SHAPE_KEYS])
        self._shape_combo.currentIndexChanged.connect(self._on_change)
        row.addWidget(lbl)
        row.addWidget(self._shape_combo, 1)
        self._vbox.addLayout(row)

        self._radius = _SliderRow(tr("flt.radius"), 1, 100, 10)
        self._add_row(self._radius)
        self._seal(reset_fn=self._reset)

    def _reset(self):
        self._shape_combo.setCurrentIndex(0)
        self._radius.reset()
        self._layer.image = self._original.copy()
        self._canvas_refresh()

    def _apply_preview(self):
        idx = self._shape_combo.currentIndex()
        shape = _SHAPES[idx] if 0 <= idx < len(_SHAPES) else _SHAPES[0]
        self._layer.image = apply_shape_blur(
            self._orig_argb32,
            self._radius.value(),
            shape,
        )
        self._canvas_refresh()


def _lens_kernel(r: int, curvature: int):
    import numpy as np
    y, x  = np.mgrid[-r:r + 1, -r:r + 1]
    dist  = np.sqrt(x * x + y * y).astype(np.float32)
    theta = np.arctan2(y.astype(np.float32), x.astype(np.float32))

    # Hexagonal boundary in polar coords (vertices at 0°, 60°, 120°, …)
    theta_mod  = theta % (np.pi / 3)
    r_hex      = r * np.cos(np.pi / 6) / np.cos(theta_mod - np.pi / 6)

    # Lerp: 0 → hexagon  …  100 → circle
    c          = curvature / 100.0
    r_boundary = (1.0 - c) * r_hex + c * r

    k     = (dist <= r_boundary).astype(np.float32)
    total = k.sum()
    return k / total if total > 0 else k


def apply_lens_blur(src: QImage, radius: int, curvature: int) -> QImage:
    img = _to_argb32(src)
    r   = max(1, radius)
    try:
        import numpy as np
        from numpy.fft import rfft2, irfft2

        ba, arr  = _bits_ba(img)
        kernel   = _lens_kernel(r, curvature)
        pad      = r
        h, w     = arr.shape[:2]

        padded0      = np.pad(arr[:, :, 0].astype(np.float32), pad, mode='edge')
        ph, pw       = padded0.shape
        k            = np.zeros((ph, pw), dtype=np.float32)
        kh, kw       = kernel.shape
        k[:kh, :kw]  = kernel
        k            = np.roll(np.roll(k, -pad, axis=0), -pad, axis=1)
        K_fft        = rfft2(k)

        for c in range(3):
            padded  = np.pad(arr[:, :, c].astype(np.float32), pad, mode='edge')
            blurred = irfft2(rfft2(padded) * K_fft, s=padded.shape)
            arr[:, :, c] = np.clip(blurred[pad:pad + h, pad:pad + w], 0, 255).astype(np.uint8)

        return _from_ba(ba, img)
    except ImportError:
        return apply_gaussian_blur(src, float(r))


class LensBlurDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("flt.lens.title"), layer, canvas_refresh, parent)
        self._radius    = _SliderRow(tr("flt.radius"),         1, 100, 10)
        self._curvature = _SliderRow(tr("flt.lens.curvature"), 0, 100, 50)
        self._add_row(self._radius)
        self._add_row(self._curvature)
        self._seal(reset_fn=self._reset)

    def _reset(self):
        self._radius.reset()
        self._curvature.reset()
        self._layer.image = self._original.copy()
        self._canvas_refresh()

    def _apply_preview(self):
        self._layer.image = apply_lens_blur(
            self._orig_argb32,
            self._radius.value(),
            self._curvature.value(),
        )
        self._canvas_refresh()
