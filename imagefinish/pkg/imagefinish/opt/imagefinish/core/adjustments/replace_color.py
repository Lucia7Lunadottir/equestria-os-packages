from PyQt6.QtWidgets import QHBoxLayout, QLabel
from PyQt6.QtGui import QImage, QColor

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog, _SliderRow
from core.adjustments._widgets import _ColorButton


def apply_replace_color(src: QImage,
                        target_r: int, target_g: int, target_b: int,
                        fuzziness: int,
                        hue: int, sat: int, light: int) -> QImage:
    """Select pixels near (target_r, g, b) with soft edge defined by *fuzziness*
    (0..100) and shift their HLS by (hue °, sat %, light %)."""
    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        arr = _in_place_arr(img)
        B = arr[:, :, 0].astype(np.float32) / 255.0
        G = arr[:, :, 1].astype(np.float32) / 255.0
        R = arr[:, :, 2].astype(np.float32) / 255.0

        # Soft selection mask
        rt = target_r / 255.0
        gt = target_g / 255.0
        bt = target_b / 255.0
        dist  = np.sqrt((R - rt) ** 2 + (G - gt) ** 2 + (B - bt) ** 2) / 1.7321
        blend = np.clip(1.0 - dist / max(fuzziness / 100.0, 0.001), 0.0, 1.0)

        # HLS decomposition
        Cmax  = np.maximum(R, np.maximum(G, B))
        Cmin  = np.minimum(R, np.minimum(G, B))
        delta = Cmax - Cmin
        L     = (Cmax + Cmin) * 0.5
        denom = np.maximum(1e-9, 1.0 - np.abs(2.0 * L - 1.0))
        S     = np.where(delta < 1e-9, 0.0, np.clip(delta / denom, 0.0, 1.0))

        H = np.zeros_like(R)
        mask = delta > 1e-9
        d    = delta[mask]
        H[mask] = np.where(
            Cmax[mask] == R[mask], ((G[mask] - B[mask]) / d) % 6.0,
            np.where(Cmax[mask] == G[mask],
                     (B[mask] - R[mask]) / d + 2.0,
                     (R[mask] - G[mask]) / d + 4.0))
        H /= 6.0

        # Apply HLS shifts
        H2 = (H + hue  / 360.0) % 1.0
        S2 = np.clip(S + sat   / 100.0, 0.0, 1.0)
        L2 = np.clip(L + light / 100.0, 0.0, 1.0)

        # HLS → RGB
        C   = (1.0 - np.abs(2.0 * L2 - 1.0)) * S2
        H6  = H2 * 6.0
        X   = C * (1.0 - np.abs(H6 % 2.0 - 1.0))
        mv  = L2 - C * 0.5
        Z   = np.zeros_like(H)
        R2  = np.zeros_like(H)
        G2  = np.zeros_like(H)
        B2  = np.zeros_like(H)
        for i, (rv, gv, bv) in enumerate(
                [(C, X, Z), (X, C, Z), (Z, C, X),
                 (Z, X, C), (X, Z, C), (C, Z, X)]):
            mi = (H6 >= i) & (H6 < i + 1)
            R2[mi] = rv[mi]; G2[mi] = gv[mi]; B2[mi] = bv[mi]

        R2 = (R2 + mv) * 255.0
        G2 = (G2 + mv) * 255.0
        B2 = (B2 + mv) * 255.0

        # Blend original ↔ adjusted
        Rf = R * 255.0;  Gf = G * 255.0;  Bf = B * 255.0
        arr[:, :, 2] = np.clip(Rf + (R2 - Rf) * blend, 0, 255).astype(np.uint8)
        arr[:, :, 1] = np.clip(Gf + (G2 - Gf) * blend, 0, 255).astype(np.uint8)
        arr[:, :, 0] = np.clip(Bf + (B2 - Bf) * blend, 0, 255).astype(np.uint8)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        import colorsys
        result = img.copy()
        rt_f = target_r / 255.0
        gt_f = target_g / 255.0
        bt_f = target_b / 255.0
        thresh = max(fuzziness / 100.0, 0.001)
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                a  = (px >> 24) & 0xFF
                ri = (px >> 16) & 0xFF
                gi = (px >>  8) & 0xFF
                bi = px & 0xFF
                dist = ((ri/255 - rt_f)**2 +
                        (gi/255 - gt_f)**2 +
                        (bi/255 - bt_f)**2) ** 0.5 / 1.7321
                bl = max(0.0, 1.0 - dist / thresh)
                if bl > 0.0:
                    hv, lv, sv = colorsys.rgb_to_hls(ri/255, gi/255, bi/255)
                    hv2 = (hv + hue   / 360.0) % 1.0
                    sv2 = max(0.0, min(1.0, sv + sat   / 100.0))
                    lv2 = max(0.0, min(1.0, lv + light / 100.0))
                    r2, g2, b2 = colorsys.hls_to_rgb(hv2, lv2, sv2)
                    ri = int(ri + (r2 * 255 - ri) * bl)
                    gi = int(gi + (g2 * 255 - gi) * bl)
                    bi = int(bi + (b2 * 255 - bi) * bl)
                    result.setPixel(x, y,
                        (a << 24) | (ri << 16) | (gi << 8) | bi)
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class ReplaceColorDialog(_AdjustDialog):
    _DEFAULT_COLOR   = QColor(255, 0, 0)
    _DEFAULT_FUZZINESS = 40

    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.replace_color.title"), layer, canvas_refresh, parent)
        self.setMinimumWidth(400)

        # Target colour row
        color_row = QHBoxLayout()
        color_lbl = QLabel(tr("adj.replace_color.target"))
        color_lbl.setFixedWidth(90)
        self._color_btn = _ColorButton(self._DEFAULT_COLOR)
        self._color_btn.colorChanged.connect(self._on_change)
        color_row.addWidget(color_lbl)
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        self._vbox.addLayout(color_row)

        self._fuzz = _SliderRow(tr("adj.replace_color.fuzziness"), 1, 100, self._DEFAULT_FUZZINESS)
        self._add_row(self._fuzz)

        # Divider label
        sep = QLabel(tr("adj.replace_color.replacement"))
        sep.setStyleSheet("color: #7f849c; font-size: 11px; font-weight: bold;"
                          " padding-top: 6px;")
        self._vbox.addWidget(sep)

        self._hue   = _SliderRow(tr("adj.replace_color.hue"),        -180, 180)
        self._sat   = _SliderRow(tr("adj.replace_color.saturation"), -100, 100)
        self._light = _SliderRow(tr("adj.replace_color.lightness"),  -100, 100)
        for row in (self._hue, self._sat, self._light):
            self._add_row(row)

        self._seal(reset_fn=self._do_reset)

    def _do_reset(self):
        self._timer.stop()
        self._color_btn.set_color(self._DEFAULT_COLOR)
        self._fuzz.reset()
        self._hue.reset()
        self._sat.reset()
        self._light.reset()
        self._apply_preview()

    def _apply_preview(self):
        c = self._color_btn.color()
        self._layer.image = apply_replace_color(
            self._orig_argb32,
            c.red(), c.green(), c.blue(),
            self._fuzz.value(),
            self._hue.value(), self._sat.value(), self._light.value())
        self._canvas_refresh()
