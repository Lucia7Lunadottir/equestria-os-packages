from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QLabel)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.locale import tr

LABEL_STYLE = "color:#a6adc8;font-size:11px;"
VALUE_STYLE = "color:#cdd6f4;font-size:11px;"
DARK = "background:#1e1e2e;"


class InfoPanel(QWidget):
    """
    Displays colour information (RGBA) and cursor position (X, Y)
    for the pixel under the cursor.

    Call update_info(x, y, color) whenever the mouse moves over the canvas.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # Title
        self._title = QLabel(self._title_text())
        self._title.setObjectName("panelTitle")
        main_layout.addWidget(self._title)

        # Grid layout for colour swatch + RGBA + XY
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        # Colour swatch — row 0, spans two columns of labels
        self._swatch = QLabel()
        self._swatch.setFixedSize(20, 20)
        self._swatch.setStyleSheet("background:#1e1e2e;border:1px solid #45475a;")
        grid.addWidget(self._swatch, 0, 0, 1, 1, Qt.AlignmentFlag.AlignTop)

        # Placeholder to keep swatch on same row
        grid.addWidget(QLabel(""), 0, 1)

        # R
        r_lbl = QLabel("R:")
        r_lbl.setStyleSheet(LABEL_STYLE)
        grid.addWidget(r_lbl, 1, 0)
        self._r_val = QLabel("—")
        self._r_val.setStyleSheet(VALUE_STYLE)
        grid.addWidget(self._r_val, 1, 1)

        # G
        g_lbl = QLabel("G:")
        g_lbl.setStyleSheet(LABEL_STYLE)
        grid.addWidget(g_lbl, 2, 0)
        self._g_val = QLabel("—")
        self._g_val.setStyleSheet(VALUE_STYLE)
        grid.addWidget(self._g_val, 2, 1)

        # B
        b_lbl = QLabel("B:")
        b_lbl.setStyleSheet(LABEL_STYLE)
        grid.addWidget(b_lbl, 3, 0)
        self._b_val = QLabel("—")
        self._b_val.setStyleSheet(VALUE_STYLE)
        grid.addWidget(self._b_val, 3, 1)

        # A
        a_lbl = QLabel("A:")
        a_lbl.setStyleSheet(LABEL_STYLE)
        grid.addWidget(a_lbl, 4, 0)
        self._a_val = QLabel("—")
        self._a_val.setStyleSheet(VALUE_STYLE)
        grid.addWidget(self._a_val, 4, 1)

        # Separator row (empty)
        grid.addWidget(QLabel(""), 5, 0)

        # X
        self._x_lbl = QLabel("X:")
        self._x_lbl.setStyleSheet(LABEL_STYLE)
        grid.addWidget(self._x_lbl, 6, 0)
        self._x_val = QLabel("—")
        self._x_val.setStyleSheet(VALUE_STYLE)
        grid.addWidget(self._x_val, 6, 1)

        # Y
        self._y_lbl = QLabel("Y:")
        self._y_lbl.setStyleSheet(LABEL_STYLE)
        grid.addWidget(self._y_lbl, 7, 0)
        self._y_val = QLabel("—")
        self._y_val.setStyleSheet(VALUE_STYLE)
        grid.addWidget(self._y_val, 7, 1)

        grid.setColumnStretch(1, 1)
        main_layout.addWidget(grid_widget)
        main_layout.addStretch()

    # ----------------------------------------------------------------- public

    def update_info(self, x: int, y: int, color: QColor):
        """Update all displayed values for the given pixel position and colour."""
        self._x_val.setText(str(x))
        self._y_val.setText(str(y))
        self._r_val.setText(str(color.red()))
        self._g_val.setText(str(color.green()))
        self._b_val.setText(str(color.blue()))
        self._a_val.setText(str(color.alpha()))
        # Swatch: show the opaque version so it is always visible
        swatch_color = QColor(color.red(), color.green(), color.blue())
        self._swatch.setStyleSheet(
            f"background:{swatch_color.name()};border:1px solid #45475a;"
        )

    def retranslate(self):
        """Update translatable strings (title only)."""
        self._title.setText(self._title_text())

    # ----------------------------------------------------------------- private

    def _title_text(self) -> str:
        val = tr("panel.info")
        return val if val != "panel.info" else "Info"
