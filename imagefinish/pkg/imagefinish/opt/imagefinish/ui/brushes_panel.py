import os
from glob import glob

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QScrollArea, QGridLayout,
                             QLabel)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (QPixmap, QPainter, QBrush, QColor, QPen)

from core.locale import tr

DARK = "background:#1e1e2e;"
LABEL_STYLE = "color:#a6adc8;font-size:11px;"

# directory that holds custom brush images, relative to project root
_BRUSHES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "brushes")

_BUILTIN = [
    ("Round",   "round"),
    ("Square",  "square"),
    ("Cross",   "cross"),
    ("Scatter", "scatter"),
]


def _make_builtin_pixmap(shape: str, size: int = 64) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor("#cdd6f4")))
    p.setPen(Qt.PenStyle.NoPen)
    if shape == "round":
        p.drawEllipse(4, 4, 56, 56)
    elif shape == "square":
        p.drawRect(4, 4, 56, 56)
    elif shape == "cross":
        p.drawRect(26, 4, 12, 56)
        p.drawRect(4, 26, 56, 12)
    elif shape == "scatter":
        for x, y in [(16, 16), (48, 16), (32, 40), (10, 50), (54, 50)]:
            p.drawEllipse(x - 6, y - 6, 12, 12)
    p.end()
    return px


class _BrushThumb(QLabel):
    """64×64 clickable thumbnail for one brush entry."""

    clicked = pyqtSignal(str)   # emits brush mask value or file path

    _BORDER_NORMAL   = "border:2px solid transparent;background:#181825;"
    _BORDER_SELECTED = "border:2px solid #cba6f7;background:#181825;"

    def __init__(self, pixmap: QPixmap, mask_value: str, tooltip: str, parent=None):
        super().__init__(parent)
        self._mask_value = mask_value
        self.setPixmap(pixmap.scaled(60, 60,
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        self.setFixedSize(64, 64)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip(tooltip)
        self.setStyleSheet(self._BORDER_NORMAL)

    def set_selected(self, selected: bool):
        self.setStyleSheet(
            self._BORDER_SELECTED if selected else self._BORDER_NORMAL
        )

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._mask_value)
        super().mousePressEvent(ev)


class BrushesPanel(QWidget):
    """
    Panel listing built-in brush shapes and any PNG/JPG files found in brushes/.
    Clicking a brush emits brush_selected(mask_value).
    """

    brush_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        self._title = QLabel(self._title_text())
        self._title.setObjectName("panelTitle")
        layout.addWidget(self._title)

        # Scrollable grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea{border:none;background:#1e1e2e;}")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background:#1e1e2e;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(4)

        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

        self._thumbs: list[_BrushThumb] = []
        self._selected_value: str = "round"

        self._populate()

    # ----------------------------------------------------------------- public

    def refresh(self, canvas):
        """Select the currently active brush from canvas tool options."""
        try:
            current = canvas.tool_opts.get("brush_mask", "round")
        except Exception:
            current = "round"
        self._select(current)

    def retranslate(self):
        """Brush names are not translated; only update title."""
        self._title.setText(self._title_text())

    # ----------------------------------------------------------------- private

    def _title_text(self) -> str:
        val = tr("panel.brushes")
        return val if val != "panel.brushes" else "Brushes"

    def _populate(self):
        """Build grid with built-in shapes and any custom PNG/JPG brushes."""
        # Clear old items
        for thumb in self._thumbs:
            thumb.deleteLater()
        self._thumbs.clear()

        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        items: list[tuple[QPixmap, str, str]] = []

        # Built-ins
        for display_name, mask_value in _BUILTIN:
            pix = _make_builtin_pixmap(mask_value)
            items.append((pix, mask_value, display_name))

        # Custom brushes from disk
        if os.path.isdir(_BRUSHES_DIR):
            patterns = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"]
            for pat in patterns:
                for path in sorted(glob(os.path.join(_BRUSHES_DIR, pat))):
                    pix = QPixmap(path)
                    if not pix.isNull():
                        name = os.path.splitext(os.path.basename(path))[0]
                        items.append((pix, path, name))

        # Build grid (3 columns)
        cols = 3
        for idx, (pix, mask_value, tooltip) in enumerate(items):
            thumb = _BrushThumb(pix, mask_value, tooltip)
            thumb.clicked.connect(self._on_brush_clicked)
            self._grid.addWidget(thumb, idx // cols, idx % cols)
            self._thumbs.append(thumb)

        self._select(self._selected_value)

    def _select(self, value: str):
        self._selected_value = value
        for thumb in self._thumbs:
            thumb.set_selected(thumb._mask_value == value)

    def _on_brush_clicked(self, mask_value: str):
        self._select(mask_value)
        self.brush_selected.emit(mask_value)
