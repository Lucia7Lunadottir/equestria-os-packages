from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog, _SliderRow


def apply_posterize(src: QImage, levels: int) -> QImage:
    """Reduce each RGB channel to *levels* discrete values (2..255)."""
    img = _to_argb32(src)
    try:
        import numpy as np
        step = 255.0 / (levels - 1)
        idx  = np.round(np.arange(256, dtype=np.float32) / step).astype(int)
        lut  = np.clip(np.round(idx * step), 0, 255).astype(np.uint8)
        img = img.copy()
        arr = _in_place_arr(img)
        arr[:, :, :3] = lut[arr[:, :, :3]]
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        step = 255.0 / (levels - 1)
        lut  = [int(round(round(i / step) * step)) for i in range(256)]
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


class PosterizeDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.posterize.title"), layer, canvas_refresh, parent)
        self._levels = _SliderRow(tr("adj.posterize.levels"), 2, 255, 4)
        self._add_row(self._levels)
        self._seal()

    def _apply_preview(self):
        self._layer.image = apply_posterize(
            self._orig_argb32, self._levels.value())
        self._canvas_refresh()
