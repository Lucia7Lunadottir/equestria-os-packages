from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QImage, QColor

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _in_place_arr, _AdjustDialog
from core.adjustments._widgets import _ColorButton, _GradientPreview


def apply_gradient_map(src: QImage,
                       shadow: tuple, highlight: tuple) -> QImage:
    """Map each pixel's luminance to a gradient from *shadow* to *highlight*
    (each is an (r, g, b) int tuple)."""
    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        arr = _in_place_arr(img)
        R = arr[:, :, 2].astype(np.uint32)
        G = arr[:, :, 1].astype(np.uint32)
        B = arr[:, :, 0].astype(np.uint32)
        t = (299 * R + 587 * G + 114 * B).astype(np.float32) / (1000.0 * 255.0)
        sr, sg, sb = shadow
        hr, hg, hb = highlight
        arr[:, :, 2] = np.clip(sr + (hr - sr) * t, 0, 255).astype(np.uint8)
        arr[:, :, 1] = np.clip(sg + (hg - sg) * t, 0, 255).astype(np.uint8)
        arr[:, :, 0] = np.clip(sb + (hb - sb) * t, 0, 255).astype(np.uint8)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        sr, sg, sb = shadow
        hr, hg, hb = highlight
        result = img.copy()
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                a  = (px >> 24) & 0xFF
                ri = (px >> 16) & 0xFF
                gi = (px >>  8) & 0xFF
                bi = px & 0xFF
                t  = (299 * ri + 587 * gi + 114 * bi) / (1000.0 * 255.0)
                result.setPixel(x, y,
                    (a << 24) |
                    (int(sr + (hr - sr) * t) << 16) |
                    (int(sg + (hg - sg) * t) <<  8) |
                    int(sb + (hb - sb) * t))
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class GradientMapDialog(_AdjustDialog):
    def __init__(self, layer, canvas_refresh, parent=None):
        super().__init__(tr("adj.gradient_map.title"), layer, canvas_refresh, parent)
        self.setMinimumWidth(420)

        # Gradient preview strip
        self._preview_strip = _GradientPreview()
        self._vbox.addWidget(self._preview_strip)
        self._vbox.addSpacing(6)

        # Swatches row
        swatch_row = QHBoxLayout()
        shad_lbl = QLabel(tr("adj.gradient_map.shadows"))
        shad_lbl.setFixedWidth(70)
        self._shadow_btn = _ColorButton(QColor(0, 0, 0))
        self._shadow_btn.colorChanged.connect(self._on_swatch_change)

        swap_btn = QPushButton("\u21c4")      # ⇄
        swap_btn.setFixedWidth(30)
        swap_btn.setToolTip(tr("adj.gradient_map.swap_tip"))
        swap_btn.clicked.connect(self._swap)

        high_lbl = QLabel(tr("adj.gradient_map.highlights"))
        high_lbl.setFixedWidth(72)
        self._highlight_btn = _ColorButton(QColor(255, 255, 255))
        self._highlight_btn.colorChanged.connect(self._on_swatch_change)

        swatch_row.addWidget(shad_lbl)
        swatch_row.addWidget(self._shadow_btn)
        swatch_row.addStretch()
        swatch_row.addWidget(swap_btn)
        swatch_row.addStretch()
        swatch_row.addWidget(high_lbl)
        swatch_row.addWidget(self._highlight_btn)
        self._vbox.addLayout(swatch_row)

        self._seal(reset_fn=self._do_reset)
        self._update_strip()

    def _on_swatch_change(self):
        self._update_strip()
        self._on_change()

    def _update_strip(self):
        self._preview_strip.set_colors(
            self._shadow_btn.color(), self._highlight_btn.color())

    def _swap(self):
        s = self._shadow_btn.color()
        h = self._highlight_btn.color()
        self._shadow_btn.set_color(h)
        self._highlight_btn.set_color(s)
        self._update_strip()
        self._on_change()

    def _do_reset(self):
        self._timer.stop()
        self._shadow_btn.set_color(QColor(0, 0, 0))
        self._highlight_btn.set_color(QColor(255, 255, 255))
        self._update_strip()
        self._apply_preview()

    def _apply_preview(self):
        s = self._shadow_btn.color()
        h = self._highlight_btn.color()
        self._layer.image = apply_gradient_map(
            self._orig_argb32,
            (s.red(), s.green(), s.blue()),
            (h.red(), h.green(), h.blue()))
        self._canvas_refresh()
