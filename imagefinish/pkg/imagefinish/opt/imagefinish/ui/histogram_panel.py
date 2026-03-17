from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QImage

from core.locale import tr

COMBO_STYLE = ("QComboBox{background:#313244;color:#cdd6f4;border:none;"
               "padding:3px 6px;border-radius:3px;}"
               "QComboBox::drop-down{border:none;}")
LABEL_STYLE = "color:#a6adc8;font-size:11px;"

# Channel display colours
_CH_COLORS = {
    "R":   ("#f38ba8", False),
    "G":   ("#a6e3a1", False),
    "B":   ("#89b4fa", False),
    "Lum": ("#cdd6f4", False),
    "RGB": (None,       True),   # special: draw all three with opacity
}


class _HistogramView(QWidget):
    """Custom widget that renders a histogram graph."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)
        self._data: dict = {}        # {"r": [...], "g": [...], "b": [...], "lum": [...]}
        self._channel: str = "RGB"

    def set_data(self, data: dict, channel: str):
        self._data = data
        self._channel = channel
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Background
        p.fillRect(self.rect(), QColor("#181825"))

        if not self._data:
            p.end()
            return

        w = self.width()
        h = self.height()

        channel = self._channel

        if channel == "RGB":
            # Draw R, G, B with opacity
            for key, color_hex in (("r", "#f38ba8"), ("g", "#a6e3a1"), ("b", "#89b4fa")):
                hist = self._data.get(key, [])
                if hist:
                    color = QColor(color_hex)
                    color.setAlphaF(0.7)
                    self._draw_histogram(p, hist, color, w, h)
        elif channel == "Red":
            hist = self._data.get("r", [])
            self._draw_histogram(p, hist, QColor("#f38ba8"), w, h)
        elif channel == "Green":
            hist = self._data.get("g", [])
            self._draw_histogram(p, hist, QColor("#a6e3a1"), w, h)
        elif channel == "Blue":
            hist = self._data.get("b", [])
            self._draw_histogram(p, hist, QColor("#89b4fa"), w, h)
        elif channel == "Luminosity":
            hist = self._data.get("lum", [])
            self._draw_histogram(p, hist, QColor("#cdd6f4"), w, h)

        p.end()

    def _draw_histogram(self, p: QPainter, hist: list, color: QColor,
                        w: int, h: int):
        if not hist or len(hist) == 0:
            return
        max_val = max(hist) if max(hist) > 0 else 1
        n = len(hist)   # 256
        pen = QPen(color, 1)
        p.setPen(pen)

        for i in range(n):
            bar_h = int((hist[i] / max_val) * (h - 2))
            x = int(i * w / n)
            x_next = int((i + 1) * w / n)
            bar_w = max(1, x_next - x)
            # Draw vertical line from bottom
            p.fillRect(x, h - bar_h, bar_w, bar_h, color)


class HistogramPanel(QWidget):
    """
    Displays an RGB / per-channel / luminosity histogram of the active document.
    """

    _CHANNEL_KEYS = ["RGB", "Red", "Green", "Blue", "Luminosity"]
    _CHANNEL_LOC  = [
        "hist.rgb", "hist.red", "hist.green", "hist.blue", "hist.luminosity"
    ]
    _CHANNEL_FALLBACKS = ["RGB", "Red", "Green", "Blue", "Luminosity"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Title
        from PyQt6.QtWidgets import QLabel
        self._title = QLabel(self._title_text())
        self._title.setObjectName("panelTitle")
        layout.addWidget(self._title)

        # Channel selector
        self._combo = QComboBox()
        self._combo.setStyleSheet(COMBO_STYLE)
        for i, key in enumerate(self._CHANNEL_KEYS):
            loc = tr(self._CHANNEL_LOC[i])
            text = loc if loc != self._CHANNEL_LOC[i] else self._CHANNEL_FALLBACKS[i]
            self._combo.addItem(text, key)
        self._combo.currentIndexChanged.connect(self._on_channel_changed)
        layout.addWidget(self._combo)

        # Histogram view
        self._view = _HistogramView()
        layout.addWidget(self._view)
        layout.addStretch()

        self._current_data: dict = {}

    # ----------------------------------------------------------------- public

    def refresh(self, canvas):
        """Recompute histogram from canvas.document.get_composite()."""
        try:
            composite = canvas.document.get_composite()
        except Exception:
            return

        if composite is None or composite.isNull():
            self._current_data = {}
            self._view.set_data({}, self._current_channel())
            return

        try:
            import numpy as np
            img = composite.convertToFormat(QImage.Format.Format_ARGB32)
            ptr = img.bits()
            ptr.setsize(img.sizeInBytes())
            arr = (
                __import__("numpy")
                .frombuffer(ptr, dtype=__import__("numpy").uint8)
                .reshape(img.height(), img.width(), 4)
            )
            import numpy as np
            mask = arr[..., 3] > 0
            r_hist = np.bincount(arr[..., 2][mask].flatten(), minlength=256).tolist()
            g_hist = np.bincount(arr[..., 1][mask].flatten(), minlength=256).tolist()
            b_hist = np.bincount(arr[..., 0][mask].flatten(), minlength=256).tolist()
            lum = (0.299 * arr[..., 2] + 0.587 * arr[..., 1]
                   + 0.114 * arr[..., 0]).astype(np.uint8)
            lum_hist = np.bincount(lum[mask].flatten(), minlength=256).tolist()
        except ImportError:
            # Slow pixel-by-pixel fallback
            img = composite.convertToFormat(QImage.Format.Format_ARGB32)
            r_hist = [0] * 256
            g_hist = [0] * 256
            b_hist = [0] * 256
            lum_hist = [0] * 256
            for y in range(img.height()):
                for x in range(img.width()):
                    px = img.pixel(x, y)
                    c = QColor(px)
                    if c.alpha() > 0:
                        r_hist[c.red()] += 1
                        g_hist[c.green()] += 1
                        b_hist[c.blue()] += 1
                        lv = int(0.299 * c.red() + 0.587 * c.green()
                                 + 0.114 * c.blue())
                        lum_hist[min(255, lv)] += 1

        self._current_data = {
            "r": r_hist,
            "g": g_hist,
            "b": b_hist,
            "lum": lum_hist,
        }
        self._view.set_data(self._current_data, self._current_channel())

    def retranslate(self):
        """Update combo items and title to current locale."""
        self._title.setText(self._title_text())
        for i, loc_key in enumerate(self._CHANNEL_LOC):
            loc = tr(loc_key)
            text = loc if loc != loc_key else self._CHANNEL_FALLBACKS[i]
            self._combo.setItemText(i, text)

    # ----------------------------------------------------------------- private

    def _title_text(self) -> str:
        val = tr("panel.histogram")
        return val if val != "panel.histogram" else "Histogram"

    def _current_channel(self) -> str:
        idx = self._combo.currentIndex()
        if idx < 0:
            return "RGB"
        return self._combo.itemData(idx) or "RGB"

    def _on_channel_changed(self, _idx: int):
        self._view.set_data(self._current_data, self._current_channel())
