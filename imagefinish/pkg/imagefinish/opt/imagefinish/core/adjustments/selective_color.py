from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox
from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog, _SliderRow


_SC_RANGES = ("Reds", "Yellows", "Greens", "Cyans",
              "Blues", "Magentas", "Whites", "Neutrals", "Blacks")
_SC_RANGE_KEYS = (
    "adj.selective_color.reds",     "adj.selective_color.yellows",
    "adj.selective_color.greens",   "adj.selective_color.cyans",
    "adj.selective_color.blues",    "adj.selective_color.magentas",
    "adj.selective_color.whites",   "adj.selective_color.neutrals",
    "adj.selective_color.blacks",
)


def apply_selective_color(src: QImage, adjustments: dict) -> QImage:
    """adjustments: dict range_name → [C, M, Y, K] each in [-100, +100].
    Uses CMYK ink model with per-range soft selection weights."""
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
        S_hsv = np.where(Cmax < 1e-6, 0.0, delta / Cmax)

        H = np.zeros_like(R)
        mask = delta > 1e-6
        d    = delta[mask]
        H[mask] = np.where(
            Cmax[mask] == R[mask], ((G[mask] - B[mask]) / d) % 6.0,
            np.where(Cmax[mask] == G[mask],
                     (B[mask] - R[mask]) / d + 2.0,
                     (R[mask] - G[mask]) / d + 4.0))
        H_deg = H * 60.0

        def hue_w(center, half_w):
            diff = np.abs(H_deg - center) % 360.0
            diff = np.minimum(diff, 360.0 - diff)
            return np.clip(1.0 - diff / half_w, 0.0, 1.0) * S_hsv

        weights = {
            "Reds":     hue_w(  0, 30),
            "Yellows":  hue_w( 60, 30),
            "Greens":   hue_w(120, 45),
            "Cyans":    hue_w(180, 30),
            "Blues":    hue_w(240, 45),
            "Magentas": hue_w(300, 30),
            "Whites":   np.clip((L - 0.5) / 0.5,         0.0, 1.0),
            "Neutrals": np.clip(1.0 - np.abs(L*2 - 1)*2, 0.0, 1.0),
            "Blacks":   np.clip((0.5 - L) / 0.5,         0.0, 1.0),
        }

        K    = 1.0 - Cmax
        safe = np.maximum(1.0 - K, 1e-9)
        C_c  = (1.0 - R - K) / safe
        M_c  = (1.0 - G - K) / safe
        Y_c  = (1.0 - B - K) / safe

        for name, vals in adjustments.items():
            ca, ma, ya, ka = vals
            if ca == ma == ya == ka == 0:
                continue
            w   = weights[name]
            C_c = np.clip(C_c + w * ca / 100.0, 0.0, 1.0)
            M_c = np.clip(M_c + w * ma / 100.0, 0.0, 1.0)
            Y_c = np.clip(Y_c + w * ya / 100.0, 0.0, 1.0)
            K   = np.clip(K   + w * ka / 100.0, 0.0, 1.0)

        inv_K = 1.0 - K
        arr[:, :, 2] = np.clip((1.0 - C_c) * inv_K * 255, 0, 255).astype(np.uint8)
        arr[:, :, 1] = np.clip((1.0 - M_c) * inv_K * 255, 0, 255).astype(np.uint8)
        arr[:, :, 0] = np.clip((1.0 - Y_c) * inv_K * 255, 0, 255).astype(np.uint8)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        result = img.copy()
        for y in range(result.height()):
            for x in range(result.width()):
                px  = result.pixel(x, y)
                a   = (px >> 24) & 0xFF
                rf  = (px >> 16 & 0xFF) / 255.0
                gf  = (px >>  8 & 0xFF) / 255.0
                bf  = (px       & 0xFF) / 255.0
                Cmx = max(rf, gf, bf);  Cmn = min(rf, gf, bf)
                dl  = Cmx - Cmn
                L   = (Cmx + Cmn) * 0.5
                S_h = dl / Cmx if Cmx > 1e-6 else 0.0
                if dl > 1e-6:
                    if   Cmx == rf: h6 = ((gf - bf) / dl) % 6.0
                    elif Cmx == gf: h6 = (bf - rf) / dl + 2.0
                    else:           h6 = (rf - gf) / dl + 4.0
                    H_d = h6 * 60.0
                else:
                    H_d = 0.0

                def hw(center, hw_):
                    dff = abs(H_d - center) % 360.0
                    dff = min(dff, 360.0 - dff)
                    return max(0.0, 1.0 - dff / hw_) * S_h

                ws = {
                    "Reds":     hw(0, 30),   "Yellows":  hw(60, 30),
                    "Greens":   hw(120, 45), "Cyans":    hw(180, 30),
                    "Blues":    hw(240, 45), "Magentas": hw(300, 30),
                    "Whites":   max(0.0, (L - 0.5) / 0.5),
                    "Neutrals": max(0.0, 1.0 - abs(L*2 - 1)*2),
                    "Blacks":   max(0.0, (0.5 - L) / 0.5),
                }
                K_c  = 1.0 - Cmx
                safe = max(1.0 - K_c, 1e-9)
                C_c  = (1 - rf - K_c) / safe
                M_c  = (1 - gf - K_c) / safe
                Y_c  = (1 - bf - K_c) / safe
                for name, (ca, ma, ya, ka) in adjustments.items():
                    if ca == ma == ya == ka == 0:
                        continue
                    w   = ws[name]
                    C_c = max(0, min(1, C_c + w * ca / 100.0))
                    M_c = max(0, min(1, M_c + w * ma / 100.0))
                    Y_c = max(0, min(1, Y_c + w * ya / 100.0))
                    K_c = max(0, min(1, K_c + w * ka / 100.0))
                iK  = 1.0 - K_c
                r2  = int(max(0, min(255, (1 - C_c) * iK * 255)))
                g2  = int(max(0, min(255, (1 - M_c) * iK * 255)))
                b2  = int(max(0, min(255, (1 - Y_c) * iK * 255)))
                result.setPixel(x, y, (a << 24) | (r2 << 16) | (g2 << 8) | b2)
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class SelectiveColorDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.selective_color.title"), layer, canvas_refresh, parent)
        self.setMinimumWidth(400)

        self._values        = {name: [0, 0, 0, 0] for name in _SC_RANGES}
        self._current_range = _SC_RANGES[0]

        # Range selector
        rng_row = QHBoxLayout()
        rng_lbl = QLabel(tr("adj.selective_color.colors"))
        rng_lbl.setFixedWidth(90)
        self._rng_combo = QComboBox()
        self._rng_combo.addItems([tr(k) for k in _SC_RANGE_KEYS])
        self._rng_combo.currentIndexChanged.connect(
            lambda i: self._switch_range(_SC_RANGES[i] if 0 <= i < len(_SC_RANGES) else _SC_RANGES[0]))
        rng_row.addWidget(rng_lbl)
        rng_row.addWidget(self._rng_combo)
        rng_row.addStretch()
        self._vbox.addLayout(rng_row)

        self._cyan    = _SliderRow(tr("adj.selective_color.cyan"),    -100, 100)
        self._magenta = _SliderRow(tr("adj.selective_color.magenta"), -100, 100)
        self._yellow  = _SliderRow(tr("adj.selective_color.yellow"),  -100, 100)
        self._black   = _SliderRow(tr("adj.selective_color.black"),   -100, 100)
        for row in (self._cyan, self._magenta, self._yellow, self._black):
            self._add_row(row)

        self._seal(reset_fn=self._do_reset)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _save_current(self):
        self._values[self._current_range] = [
            self._cyan.value(), self._magenta.value(),
            self._yellow.value(), self._black.value(),
        ]

    def _load_range(self, name):
        c, m, y, k = self._values[name]
        self._cyan.set_value(c);    self._magenta.set_value(m)
        self._yellow.set_value(y);  self._black.set_value(k)

    def _switch_range(self, name):
        self._save_current()
        self._current_range = name
        self._load_range(name)
        self._on_change()

    def _do_reset(self):
        self._timer.stop()
        self._values = {name: [0, 0, 0, 0] for name in _SC_RANGES}
        self._rng_combo.blockSignals(True)
        self._rng_combo.setCurrentIndex(0)
        self._rng_combo.blockSignals(False)
        self._current_range = _SC_RANGES[0]
        self._load_range(_SC_RANGES[0])
        self._apply_preview()

    def _apply_preview(self):
        self._save_current()
        self._layer.image = apply_selective_color(
            self._orig_argb32, self._values)
        self._canvas_refresh()
