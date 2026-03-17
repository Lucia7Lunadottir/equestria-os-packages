from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog, _SliderRow


def apply_vibrance(src: QImage, vibrance: int, saturation: int) -> QImage:
    """vibrance / saturation each in [-100, 100].
    Vibrance selectively boosts less-saturated colours."""
    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        arr = _in_place_arr(img)
        B = arr[:, :, 0].astype(np.float32) / 255.0
        G = arr[:, :, 1].astype(np.float32) / 255.0
        R = arr[:, :, 2].astype(np.float32) / 255.0

        Cmax  = np.maximum(R, np.maximum(G, B))
        Cmin  = np.minimum(R, np.minimum(G, B))
        delta = Cmax - Cmin

        L     = (Cmax + Cmin) * 0.5
        denom = np.maximum(1e-9, 1.0 - np.abs(2.0 * L - 1.0))
        S     = np.where(delta < 1e-9, 0.0, np.clip(delta / denom, 0.0, 1.0))

        # Vibrance: proportionally less boost for already-saturated pixels
        vib_boost = vibrance / 100.0 * (1.0 - S)
        S_new = np.clip(S + vib_boost + saturation / 100.0, 0.0, 1.0)

        # Reconstruct RGB with modified saturation (hue unchanged)
        H = np.zeros_like(R)
        mask = delta > 1e-9
        d    = delta[mask]
        H[mask] = np.where(
            Cmax[mask] == R[mask], ((G[mask] - B[mask]) / d) % 6.0,
            np.where(Cmax[mask] == G[mask],
                     (B[mask] - R[mask]) / d + 2.0,
                     (R[mask] - G[mask]) / d + 4.0))
        H /= 6.0

        C  = (1.0 - np.abs(2.0 * L - 1.0)) * S_new
        H6 = H * 6.0
        X  = C * (1.0 - np.abs(H6 % 2.0 - 1.0))
        mv = L - C * 0.5
        Z  = np.zeros_like(H)

        R2 = np.zeros_like(H); G2 = np.zeros_like(H); B2 = np.zeros_like(H)
        for i, (rv, gv, bv) in enumerate(
                [(C, X, Z), (X, C, Z), (Z, C, X),
                 (Z, X, C), (X, Z, C), (C, Z, X)]):
            mi = (H6 >= i) & (H6 < i + 1)
            R2[mi] = rv[mi]; G2[mi] = gv[mi]; B2[mi] = bv[mi]

        arr[:, :, 2] = np.clip((R2 + mv) * 255, 0, 255).astype(np.uint8)
        arr[:, :, 1] = np.clip((G2 + mv) * 255, 0, 255).astype(np.uint8)
        arr[:, :, 0] = np.clip((B2 + mv) * 255, 0, 255).astype(np.uint8)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        import colorsys
        result = img.copy()
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                a  = (px >> 24) & 0xFF
                r  = (px >> 16) & 0xFF
                g  = (px >>  8) & 0xFF
                b  = px & 0xFF
                hv, lv, sv = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
                sv = max(0.0, min(1.0,
                                  sv + vibrance / 100.0 * (1.0 - sv)
                                  + saturation / 100.0))
                r2, g2, b2 = colorsys.hls_to_rgb(hv, lv, sv)
                result.setPixel(x, y,
                    (a << 24) | (int(r2 * 255) << 16) |
                    (int(g2 * 255) << 8) | int(b2 * 255))
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class VibranceDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.vibrance.title"), layer, canvas_refresh, parent)
        self._vib = _SliderRow(tr("adj.vibrance.vibrance"),   -100, 100)
        self._sat = _SliderRow(tr("adj.vibrance.saturation"), -100, 100)
        self._add_row(self._vib)
        self._add_row(self._sat)
        self._seal()

    def _apply_preview(self):
        self._layer.image = apply_vibrance(
            self._orig_argb32, self._vib.value(), self._sat.value())
        self._canvas_refresh()
