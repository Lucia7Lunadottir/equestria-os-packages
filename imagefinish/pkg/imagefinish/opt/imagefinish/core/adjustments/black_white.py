from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog, _SliderRow


def apply_black_white(src: QImage, reds: int, yellows: int, greens: int,
                      cyans: int, blues: int, magentas: int) -> QImage:
    """Convert to greyscale with per-hue luminance weighting.
    Slider 100 = standard luminance; 0 = fully dark; 200 = doubly bright."""
    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        arr = _in_place_arr(img)
        B = arr[:, :, 0].astype(np.float32) / 255.0
        G = arr[:, :, 1].astype(np.float32) / 255.0
        R = arr[:, :, 2].astype(np.float32) / 255.0

        # Standard luminance
        L = 0.299 * R + 0.587 * G + 0.114 * B

        # HSV saturation (simpler than HLS for weighting purposes)
        Cmax  = np.maximum(R, np.maximum(G, B))
        Cmin  = np.minimum(R, np.minimum(G, B))
        delta = Cmax - Cmin
        S = np.where(Cmax < 1e-6, 0.0, delta / Cmax)

        # Hue in [0, 6)
        H = np.zeros_like(R)
        mask = delta > 1e-6
        d    = delta[mask]
        H[mask] = np.where(
            Cmax[mask] == R[mask], ((G[mask] - B[mask]) / d) % 6.0,
            np.where(Cmax[mask] == G[mask],
                     (B[mask] - R[mask]) / d + 2.0,
                     (R[mask] - G[mask]) / d + 4.0))

        # Sector weights: R=0, Y=1, G=2, C=3, B=4, M=5 (in hue[0..6))
        w = np.array([reds, yellows, greens, cyans, blues, magentas],
                     dtype=np.float32) / 100.0
        h_floor  = np.floor(H).astype(int) % 6
        h_frac   = H - np.floor(H)
        interp_w = w[h_floor] * (1.0 - h_frac) + w[(h_floor + 1) % 6] * h_frac

        # For grey pixels (S≈0) the sector weight has no effect
        # gray = L * (1 + (interp_w - 1) * S)
        gray = np.clip(L * (1.0 + (interp_w - 1.0) * S) * 255.0,
                       0, 255).astype(np.uint8)
        arr[:, :, 0] = gray
        arr[:, :, 1] = gray
        arr[:, :, 2] = gray
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        ws = [reds, yellows, greens, cyans, blues, magentas]
        result = img.copy()
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                a  = (px >> 24) & 0xFF
                r  = (px >> 16 & 0xFF) / 255.0
                g  = (px >>  8 & 0xFF) / 255.0
                b  = (px       & 0xFF) / 255.0
                lv = 0.299 * r + 0.587 * g + 0.114 * b
                Cmax = max(r, g, b); delta = Cmax - min(r, g, b)
                S = delta / Cmax if Cmax > 1e-6 else 0.0
                if delta > 1e-6:
                    if   Cmax == r: h6 = ((g - b) / delta) % 6.0
                    elif Cmax == g: h6 = (b - r) / delta + 2.0
                    else:           h6 = (r - g) / delta + 4.0
                    hi   = int(h6) % 6
                    frac = h6 - int(h6)
                    w_i  = ws[hi] * (1 - frac) + ws[(hi + 1) % 6] * frac
                else:
                    w_i = 100
                gv = int(max(0, min(255,
                    lv * (1.0 + (w_i / 100.0 - 1.0) * S) * 255.0)))
                result.setPixel(x, y, (a << 24) | (gv << 16) | (gv << 8) | gv)
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class BlackWhiteDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.bw.title"), layer, canvas_refresh, parent)
        self._reds     = _SliderRow(tr("adj.bw.reds"),     0, 200, 100)
        self._yellows  = _SliderRow(tr("adj.bw.yellows"),  0, 200, 100)
        self._greens   = _SliderRow(tr("adj.bw.greens"),   0, 200, 100)
        self._cyans    = _SliderRow(tr("adj.bw.cyans"),    0, 200, 100)
        self._blues    = _SliderRow(tr("adj.bw.blues"),    0, 200, 100)
        self._magentas = _SliderRow(tr("adj.bw.magentas"), 0, 200, 100)
        for row in (self._reds, self._yellows, self._greens,
                    self._cyans, self._blues, self._magentas):
            self._add_row(row)
        self._seal()

    def _apply_preview(self):
        self._layer.image = apply_black_white(
            self._orig_argb32,
            self._reds.value(), self._yellows.value(), self._greens.value(),
            self._cyans.value(), self._blues.value(), self._magentas.value())
        self._canvas_refresh()
