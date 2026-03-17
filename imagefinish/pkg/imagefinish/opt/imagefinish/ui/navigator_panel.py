from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QSlider, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

from core.locale import tr

DARK = "background:#1e1e2e;"
BTN_STYLE = ("QPushButton{background:#313244;color:#cdd6f4;border:none;"
             "padding:4px 10px;border-radius:4px;}"
             "QPushButton:hover{background:#45475a;}"
             "QPushButton:pressed{background:#585b70;}")
LABEL_STYLE = "color:#a6adc8;font-size:11px;"


class NavigatorPanel(QWidget):
    """
    Shows a thumbnail of the composite + a zoom slider.

    Signal zoom_changed(float): emits the desired zoom factor (e.g. 1.5 = 150 %).
    """

    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Title
        self._title = QLabel(self._title_text())
        self._title.setObjectName("panelTitle")
        layout.addWidget(self._title)

        # Thumbnail
        self._thumb = QLabel()
        self._thumb.setFixedHeight(120)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet("background:#181825;border:none;")
        layout.addWidget(self._thumb)

        # Zoom percent label
        self._zoom_label = QLabel("100%")
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setStyleSheet(LABEL_STYLE)
        layout.addWidget(self._zoom_label)

        # Slider row: [-] [slider] [+]
        slider_row = QWidget()
        slider_lo = QHBoxLayout(slider_row)
        slider_lo.setContentsMargins(0, 0, 0, 0)
        slider_lo.setSpacing(4)

        self._btn_minus = QPushButton("−")
        self._btn_minus.setFixedSize(24, 24)
        self._btn_minus.setStyleSheet(BTN_STYLE)
        self._btn_minus.setToolTip("Zoom out")
        slider_lo.addWidget(self._btn_minus)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(2, 3200)   # 2% … 3200%
        self._slider.setValue(100)
        slider_lo.addWidget(self._slider, 1)

        self._btn_plus = QPushButton("+")
        self._btn_plus.setFixedSize(24, 24)
        self._btn_plus.setStyleSheet(BTN_STYLE)
        self._btn_plus.setToolTip("Zoom in")
        slider_lo.addWidget(self._btn_plus)

        layout.addWidget(slider_row)

        # Connections
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._btn_minus.clicked.connect(self._on_minus)
        self._btn_plus.clicked.connect(self._on_plus)

        self._updating = False

    # ----------------------------------------------------------------- public

    def refresh(self, canvas):
        """Update thumbnail and slider from canvas state."""
        self._updating = True

        # Update thumbnail
        try:
            composite = canvas.document.get_composite()
            if composite and not composite.isNull():
                pix = QPixmap.fromImage(composite)
                scaled = pix.scaled(200, 120,
                                    Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
                self._thumb.setPixmap(scaled)
            else:
                self._thumb.clear()
        except Exception:
            self._thumb.clear()

        # Update slider to match canvas.zoom (float, e.g. 1.0 = 100%)
        zoom_pct = int(getattr(canvas, "zoom", 1.0) * 100)
        zoom_pct = max(2, min(3200, zoom_pct))
        self._slider.setValue(zoom_pct)
        self._zoom_label.setText(f"{zoom_pct}%")

        self._updating = False

    def retranslate(self):
        """Update translatable strings."""
        self._title.setText(self._title_text())

    # ----------------------------------------------------------------- private

    def _title_text(self) -> str:
        val = tr("panel.navigator")
        return val if val != "panel.navigator" else "Navigator"

    def _on_slider_changed(self, value: int):
        if self._updating:
            return
        self._zoom_label.setText(f"{value}%")
        self.zoom_changed.emit(value / 100.0)

    def _on_minus(self):
        current_factor = self._slider.value() / 100.0
        new_factor = current_factor / 1.25
        new_factor = max(0.02, new_factor)
        self.zoom_changed.emit(new_factor)

    def _on_plus(self):
        current_factor = self._slider.value() / 100.0
        new_factor = current_factor * 1.25
        new_factor = min(32.0, new_factor)
        self.zoom_changed.emit(new_factor)
