from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog
from core.adjustments._widgets import _FSliderRow


def apply_exposure(src: QImage, exposure: float, offset: float,
                   gamma: float) -> QImage:
    """exposure: stops [-5..+5]; offset: additive [-0.5..+0.5];
    gamma correction [0.1..9.99].  Identity at all defaults = 0 / 0 / 1.0."""
    img = _to_argb32(src)
    try:
        import numpy as np
        v      = np.arange(256, dtype=np.float32) / 255.0
        linear = v ** 2.2
        linear = np.clip(linear * (2.0 ** exposure) + offset, 0.0, None)
        linear = linear ** (1.0 / gamma)
        lut    = np.clip(linear ** (1.0 / 2.2) * 255.0, 0, 255).astype(np.uint8)
        img = img.copy()
        arr = _in_place_arr(img)
        arr[:, :, :3] = lut[arr[:, :, :3]]
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        lut = []
        for i in range(256):
            lin = max(0.0, (i / 255.0) ** 2.2 * (2.0 ** exposure) + offset)
            lut.append(int(max(0, min(255, lin ** (1.0 / gamma)
                                          ** (1.0 / 2.2) * 255.0))))
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


class ExposureDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.exposure.title"), layer, canvas_refresh, parent)
        # Slider integers / 100 = actual float value
        self._exp    = _FSliderRow(tr("adj.exposure.exposure"),  -500, 500,   0, 100.0, 2)
        self._offset = _FSliderRow(tr("adj.exposure.offset"),     -50,  50,   0, 100.0, 2)
        self._gamma  = _FSliderRow(tr("adj.exposure.gamma"),       10, 999, 100, 100.0, 2)
        for row in (self._exp, self._offset, self._gamma):
            self._add_row(row)
        self._seal()

    def _apply_preview(self):
        self._layer.image = apply_exposure(
            self._orig_argb32,
            self._exp.value(), self._offset.value(), self._gamma.value())
        self._canvas_refresh()
