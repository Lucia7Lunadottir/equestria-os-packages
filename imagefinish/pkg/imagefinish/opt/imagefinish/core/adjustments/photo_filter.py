from PyQt6.QtWidgets import QHBoxLayout, QLabel, QCheckBox
from PyQt6.QtGui import QImage, QColor

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog, _SliderRow
from core.adjustments._widgets import _ColorButton


def apply_photo_filter(src: QImage, r: int, g: int, b: int,
                       density: int, preserve_lum: bool) -> QImage:
    """Blend image with a filter colour at *density* %.
    If *preserve_lum*: scale result to retain original luminance."""
    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        arr = _in_place_arr(img)
        R = arr[:, :, 2].astype(np.float32)
        G = arr[:, :, 1].astype(np.float32)
        B = arr[:, :, 0].astype(np.float32)

        d  = density / 100.0
        R2 = R * (1.0 - d) + r * d
        G2 = G * (1.0 - d) + g * d
        B2 = B * (1.0 - d) + b * d

        if preserve_lum:
            L_orig = 0.299 * R  + 0.587 * G  + 0.114 * B
            L_res  = 0.299 * R2 + 0.587 * G2 + 0.114 * B2
            scale  = np.where(L_res > 0.5, L_orig / np.maximum(L_res, 0.5), 1.0)
            R2 = np.clip(R2 * scale, 0, 255)
            G2 = np.clip(G2 * scale, 0, 255)
            B2 = np.clip(B2 * scale, 0, 255)

        arr[:, :, 2] = np.clip(R2, 0, 255).astype(np.uint8)
        arr[:, :, 1] = np.clip(G2, 0, 255).astype(np.uint8)
        arr[:, :, 0] = np.clip(B2, 0, 255).astype(np.uint8)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        result = img.copy()
        d = density / 100.0
        for y in range(result.height()):
            for x in range(result.width()):
                px  = result.pixel(x, y)
                a   = (px >> 24) & 0xFF
                ri  = (px >> 16) & 0xFF
                gi  = (px >>  8) & 0xFF
                bi  = px & 0xFF
                r2  = ri * (1 - d) + r * d
                g2  = gi * (1 - d) + g * d
                b2  = bi * (1 - d) + b * d
                if preserve_lum:
                    lo = 0.299 * ri + 0.587 * gi + 0.114 * bi
                    lr = 0.299 * r2 + 0.587 * g2 + 0.114 * b2
                    if lr > 0.5:
                        s = lo / max(lr, 0.5)
                        r2 = min(255, r2 * s)
                        g2 = min(255, g2 * s)
                        b2 = min(255, b2 * s)
                result.setPixel(x, y,
                    (a << 24) | (int(r2) << 16) | (int(g2) << 8) | int(b2))
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class PhotoFilterDialog(_AdjustDialog):
    _DEFAULT_COLOR   = QColor(235, 115, 25)   # warm Kodak orange
    _DEFAULT_DENSITY = 25

    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.photo_filter.title"), layer, canvas_refresh, parent)

        color_row = QHBoxLayout()
        color_lbl = QLabel(tr("adj.photo_filter.color"))
        color_lbl.setFixedWidth(90)
        self._color_btn = _ColorButton(self._DEFAULT_COLOR)
        self._color_btn.colorChanged.connect(self._on_change)
        color_row.addWidget(color_lbl)
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        self._vbox.addLayout(color_row)

        self._density = _SliderRow(tr("adj.photo_filter.density"), 1, 100, self._DEFAULT_DENSITY)
        self._add_row(self._density)

        self._preserve = QCheckBox(tr("adj.photo_filter.preserve"))
        self._preserve.setChecked(True)
        self._preserve.stateChanged.connect(self._on_change)
        self._vbox.addWidget(self._preserve)

        self._seal(reset_fn=self._do_reset)

    def _do_reset(self):
        self._timer.stop()
        self._color_btn.set_color(self._DEFAULT_COLOR)
        self._density.reset()
        self._preserve.blockSignals(True)
        self._preserve.setChecked(True)
        self._preserve.blockSignals(False)
        self._apply_preview()

    def _apply_preview(self):
        c = self._color_btn.color()
        self._layer.image = apply_photo_filter(
            self._orig_argb32,
            c.red(), c.green(), c.blue(),
            self._density.value(), self._preserve.isChecked())
        self._canvas_refresh()
