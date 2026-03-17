"""core/filters/motion_blur.py — Motion Blur filter + dialog."""

import math

from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _AdjustDialog, _SliderRow, _to_argb32, _from_ba, _bits_ba


# ── kernel builder ────────────────────────────────────────────────────────────

def _motion_kernel(angle_deg: float, strength: int):
    """Return a normalized 2-D motion-blur kernel (odd size, ready for FFT)."""
    import numpy as np
    size   = max(strength | 1, 3)   # force odd, at least 3
    center = size // 2
    kernel = np.zeros((size, size), dtype=np.float32)
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    for i in range(-center, center + 1):
        x = int(round(center + i * cos_a))
        y = int(round(center + i * sin_a))
        if 0 <= y < size and 0 <= x < size:
            kernel[y, x] = 1.0
    total = kernel.sum()
    return kernel / total if total > 0 else kernel


# ── apply function ────────────────────────────────────────────────────────────

def apply_motion_blur(src: QImage, angle_deg: float, strength: int) -> QImage:
    """Motion blur at angle_deg (0–360°), strength 1–999 px. Alpha preserved."""
    if strength < 1:
        return src.copy()
    img = _to_argb32(src)

    try:
        import numpy as np
        from numpy.fft import rfft2, irfft2  # real FFT: ~2× faster than complex fft2

        ba, arr = _bits_ba(img)
        kernel  = _motion_kernel(angle_deg, strength)
        pad     = kernel.shape[0] // 2
        h, w    = arr.shape[:2]

        # Pad and FFT the kernel once — reuse for all channels
        ch0    = arr[:, :, 0].astype(np.float32)
        padded = np.pad(ch0, pad, mode='edge')
        ph, pw = padded.shape

        k          = np.zeros((ph, pw), dtype=np.float32)
        kh, kw     = kernel.shape
        k[:kh, :kw] = kernel
        k           = np.roll(np.roll(k, -pad, axis=0), -pad, axis=1)
        K_fft       = rfft2(k)  # compute kernel FFT once

        for c in range(3):  # BGR only — preserve alpha
            ch     = arr[:, :, c].astype(np.float32)
            padded = np.pad(ch, pad, mode='edge')
            blurred = irfft2(rfft2(padded) * K_fft, s=padded.shape)
            arr[:, :, c] = np.clip(
                blurred[pad:pad + h, pad:pad + w], 0, 255
            ).astype(np.uint8)

        return _from_ba(ba, img)

    except ImportError:
        # Slow Python fallback: sample along motion direction per pixel
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        half  = strength // 2
        out   = img.copy()
        W, H  = img.width(), img.height()
        for y in range(H):
            for x in range(W):
                r = g = b = count = 0
                for i in range(-half, half + 1):
                    sx = int(round(x + i * cos_a))
                    sy = int(round(y + i * sin_a))
                    if 0 <= sx < W and 0 <= sy < H:
                        px = img.pixel(sx, sy)
                        r += (px >> 16) & 0xFF
                        g += (px >>  8) & 0xFF
                        b +=  px        & 0xFF
                        count += 1
                if count:
                    a = (img.pixel(x, y) >> 24) & 0xFF
                    out.setPixel(x, y,
                        (a << 24) | ((r // count) << 16) |
                        ((g // count) << 8) | (b // count))
        return out.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


# ── dialog ────────────────────────────────────────────────────────────────────

class MotionBlurDialog(_AdjustDialog):
    """Motion Blur dialog with live preview."""

    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("flt.motion.title"), layer, canvas_refresh, parent)
        self._angle    = _SliderRow(tr("flt.motion.angle"),    0, 360, 0)
        self._strength = _SliderRow(tr("flt.motion.strength"), 1, 999, 10)
        self._add_row(self._angle)
        self._add_row(self._strength)
        self._seal(reset_fn=self._reset)

    def _reset(self):
        self._angle.reset()
        self._strength.reset()
        self._layer.image = self._original.copy()
        self._canvas_refresh()

    def _apply_preview(self):
        self._layer.image = apply_motion_blur(
            self._orig_argb32,
            self._angle.value(),
            self._strength.value(),
        )
        self._canvas_refresh()
