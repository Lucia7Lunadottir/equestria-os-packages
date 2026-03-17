from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog, _SliderRow


def apply_shadows_highlights(src: QImage, shadows: int,
                              highlights: int) -> QImage:
    """shadows/highlights each in [0, 100].
    Shadows lifts dark tones; Highlights pulls down bright tones.
    Applied as a per-channel LUT using smooth power curves."""
    img = _to_argb32(src)
    try:
        import numpy as np
        v  = np.arange(256, dtype=np.float32)
        sd = shadows    / 100.0 * np.power(1.0 - v / 255.0, 1.5) * (255.0 - v) * 0.5
        hd = highlights / 100.0 * np.power(v / 255.0,       1.5) * v            * 0.5
        lut = np.clip(v + sd - hd, 0, 255).astype(np.uint8)
        img = img.copy()
        arr = _in_place_arr(img)
        arr[:, :, :3] = lut[arr[:, :, :3]]
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        lut = []
        for v in range(256):
            sd = shadows    / 100.0 * ((1 - v / 255.0) ** 1.5) * (255.0 - v) * 0.5
            hd = highlights / 100.0 * ((v / 255.0)      ** 1.5) * v            * 0.5
            lut.append(int(max(0, min(255, v + sd - hd))))
        result = img.copy()
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                a  = (px >> 24) & 0xFF
                r  = lut[(px >> 16) & 0xFF]
                g  = lut[(px >>  8) & 0xFF]
                b  = lut[px & 0xFF]
                result.setPixel(x, y, (a << 24) | (r << 16) | (g << 8) | b)
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class ShadowsHighlightsDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.shadows_hl.title"), layer, canvas_refresh, parent)
        self._shadows    = _SliderRow(tr("adj.shadows_hl.shadows"),    0, 100)
        self._highlights = _SliderRow(tr("adj.shadows_hl.highlights"), 0, 100)
        self._add_row(self._shadows)
        self._add_row(self._highlights)
        self._seal(reset_fn=self._do_reset)

    def _do_reset(self):
        self._timer.stop()
        self._shadows.reset()
        self._highlights.reset()
        self._apply_preview()

    def _apply_preview(self):
        self._layer.image = apply_shadows_highlights(
            self._orig_argb32,
            self._shadows.value(), self._highlights.value())
        self._canvas_refresh()
