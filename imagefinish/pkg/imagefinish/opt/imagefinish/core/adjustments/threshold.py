from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog, _SliderRow


def apply_threshold(src: QImage, threshold: int) -> QImage:
    """Pixels with luma >= threshold → white; otherwise black. Alpha preserved."""
    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        arr = _in_place_arr(img)
        R = arr[:, :, 2].astype(np.uint16)
        G = arr[:, :, 1].astype(np.uint16)
        B = arr[:, :, 0].astype(np.uint16)
        luma  = (299 * R + 587 * G + 114 * B) // 1000
        white = (luma >= threshold).astype(np.uint8) * 255
        arr[:, :, 0] = white
        arr[:, :, 1] = white
        arr[:, :, 2] = white
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        result = img.copy()
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                a  = (px >> 24) & 0xFF
                r  = (px >> 16) & 0xFF
                g  = (px >>  8) & 0xFF
                b  = px & 0xFF
                v  = 255 if (299 * r + 587 * g + 114 * b) // 1000 >= threshold else 0
                result.setPixel(x, y, (a << 24) | (v << 16) | (v << 8) | v)
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class ThresholdDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.threshold.title"), layer, canvas_refresh, parent)
        self._thresh = _SliderRow(tr("adj.threshold.threshold"), 0, 255, 128)
        self._add_row(self._thresh)
        self._seal()

    def _apply_preview(self):
        self._layer.image = apply_threshold(
            self._orig_argb32, self._thresh.value())
        self._canvas_refresh()
