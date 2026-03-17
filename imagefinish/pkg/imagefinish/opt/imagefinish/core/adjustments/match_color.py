from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox
from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _const_arr, _in_place_arr, _AdjustDialog, _SliderRow


def _to_float_bgr(img: QImage):
    """Return H×W×3 float32 numpy array (BGR, 0..1) from an ARGB32 QImage."""
    import numpy as np
    arr = _const_arr(img).astype(np.float32) / 255.0
    return arr[:, :, :3]          # drop alpha, keep BGR


def _rgb_to_lab(bgr):
    """float32 H×W×3 BGR [0..1] → (L*, a*, b*) each float32 H×W."""
    import numpy as np

    B, G, R = bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2]

    def lin(c):   # sRGB → linear
        return np.where(c > 0.04045,
                        ((c + 0.055) / 1.055) ** 2.4,
                        c / 12.92)

    Rl, Gl, Bl = lin(R), lin(G), lin(B)

    X = 0.4124564 * Rl + 0.3575761 * Gl + 0.1804375 * Bl
    Y = 0.2126729 * Rl + 0.7151522 * Gl + 0.0721750 * Bl
    Z = 0.0193339 * Rl + 0.1191920 * Gl + 0.9503041 * Bl

    X /= 0.95047;  Z /= 1.08883       # normalise by D65 white point (Y=1)

    def f(t):
        return np.where(t > 0.008856, t ** (1.0 / 3.0), 7.787 * t + 16.0 / 116.0)

    fx, fy, fz = f(X), f(Y), f(Z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def _lab_to_bgr(L, a, b):
    """(L*, a*, b*) float32 H×W → float32 H×W×3 BGR, clipped to [0..1]."""
    import numpy as np

    fy = (L + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0

    def finv(t):
        return np.where(t > 0.20690, t ** 3.0,
                        (t - 16.0 / 116.0) / 7.787)

    X = finv(fx) * 0.95047
    Y = finv(fy)
    Z = finv(fz) * 1.08883

    Rl =  3.2404542 * X - 1.5371385 * Y - 0.4985314 * Z
    Gl = -0.9692660 * X + 1.8760108 * Y + 0.0415560 * Z
    Bl =  0.0556434 * X - 0.2040259 * Y + 1.0572252 * Z

    def gamma(c):
        c = np.clip(c, 0.0, 1.0)
        return np.where(c > 0.0031308,
                        1.055 * c ** (1.0 / 2.4) - 0.055,
                        12.92 * c)

    out = np.zeros(L.shape + (3,), dtype=np.float32)
    out[:, :, 0] = gamma(Bl)
    out[:, :, 1] = gamma(Gl)
    out[:, :, 2] = gamma(Rl)
    return out


def apply_match_color(src: QImage, source_img: QImage,
                      luminance: int, color_intensity: int,
                      fade: int) -> QImage:
    """Transfer colour statistics from *source_img* to *src* in Lab space.
    luminance / color_intensity in [1..200] (100 = identity).
    fade in [0..100]: 0 = full match, 100 = original unchanged."""
    img = _to_argb32(src)
    try:
        import numpy as np

        src_a32 = _to_argb32(source_img)
        tgt_bgr = _to_float_bgr(img)
        src_bgr = _to_float_bgr(src_a32)

        tL, ta, tb = _rgb_to_lab(tgt_bgr)
        sL, sa, sb = _rgb_to_lab(src_bgr)

        def transfer(t_ch, s_ch, scale):
            t_mean, t_std = t_ch.mean(), max(float(t_ch.std()), 1e-6)
            s_mean, s_std = s_ch.mean(), max(float(s_ch.std()), 1e-6)
            return (t_ch - t_mean) * (s_std / t_std) * scale + s_mean

        lum_scale = luminance       / 100.0
        ci_scale  = color_intensity / 100.0

        L2 = transfer(tL, sL, lum_scale)
        a2 = transfer(ta, sa, ci_scale)
        b2 = transfer(tb, sb, ci_scale)

        matched_bgr = np.clip(_lab_to_bgr(L2, a2, b2), 0.0, 1.0)

        # Fade: blend matched ↔ original
        blend = 1.0 - fade / 100.0
        result_bgr = tgt_bgr * (1.0 - blend) + matched_bgr * blend

        img = img.copy()
        arr = _in_place_arr(img)
        arr[:, :, :3] = np.clip(result_bgr * 255.0, 0, 255).astype(np.uint8)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class MatchColorDialog(_AdjustDialog):
    """sources: list of (display_name, QImage) for the source dropdown."""

    def __init__(self, layer, sources: list, canvas_refresh, parent=None):
        super().__init__(tr("adj.match_color.title"), layer, canvas_refresh, parent)
        self.setMinimumWidth(420)
        self._sources = sources          # [(name, QImage), ...]

        # Source selector
        src_row = QHBoxLayout()
        src_lbl = QLabel(tr("adj.match_color.source"))
        src_lbl.setFixedWidth(90)
        self._src_combo = QComboBox()
        self._src_combo.addItem(tr("adj.match_color.none"))
        for name, _ in sources:
            self._src_combo.addItem(name)
        self._src_combo.currentIndexChanged.connect(self._on_change)
        src_row.addWidget(src_lbl)
        src_row.addWidget(self._src_combo)
        src_row.addStretch()
        self._vbox.addLayout(src_row)

        self._lum  = _SliderRow(tr("adj.match_color.luminance"),  1, 200, 100)
        self._ci   = _SliderRow(tr("adj.match_color.intensity"),  1, 200, 100)
        self._fade = _SliderRow(tr("adj.match_color.fade"),       0, 100,   0)
        for row in (self._lum, self._ci, self._fade):
            self._add_row(row)

        self._seal(reset_fn=self._do_reset)

    def _source_image(self):
        idx = self._src_combo.currentIndex() - 1   # 0 = "None" offset
        if 0 <= idx < len(self._sources):
            return self._sources[idx][1]
        return None

    def _do_reset(self):
        self._timer.stop()
        self._src_combo.blockSignals(True)
        self._src_combo.setCurrentIndex(0)
        self._src_combo.blockSignals(False)
        self._lum.reset()
        self._ci.reset()
        self._fade.reset()
        self._apply_preview()

    def _apply_preview(self):
        src = self._source_image()
        if src is None:
            self._layer.image = self._original.copy()
            self._canvas_refresh()
            return
        self._layer.image = apply_match_color(
            self._orig_argb32, src,
            self._lum.value(), self._ci.value(), self._fade.value())
        self._canvas_refresh()
