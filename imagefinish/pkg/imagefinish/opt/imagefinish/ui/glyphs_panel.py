import unicodedata

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QScrollArea, QGridLayout, QLineEdit,
                             QFontComboBox, QSizePolicy, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QCursor

from core.locale import tr

# Default character ranges to show:
# Latin Basic U+0020..U+007E, Latin-1 Supplement U+00A0..U+00FF,
# Latin Extended-A U+0100..U+017E
_DEFAULT_RANGES = list(range(0x0020, 0x007F)) + list(range(0x00A0, 0x0100)) + list(range(0x0100, 0x017F))

COLUMNS = 16

HEADER_STYLE = ("color:#7f849c;font-size:10px;font-weight:bold;letter-spacing:1px;"
                "background:transparent;padding:8px 0 4px 0;")
SEARCH_STYLE = ("QLineEdit{background:#313244;color:#cdd6f4;border:none;"
                "padding:4px 8px;border-radius:3px;}")
CELL_NORMAL_STYLE = ("background:#1e1e2e;color:#cdd6f4;border:1px solid #313244;"
                     "border-radius:2px;font-size:14px;")
CELL_HOVER_STYLE  = ("background:#313244;color:#cba6f7;border:1px solid #45475a;"
                     "border-radius:2px;font-size:14px;")
PREVIEW_STYLE = ("background:#313244;color:#cdd6f4;border:1px solid #45475a;"
                 "border-radius:4px;font-size:32px;")
INFO_STYLE = "color:#a6adc8;font-size:11px;background:transparent;"


class _GlyphCell(QLabel):
    """A single clickable glyph cell."""
    clicked_char = pyqtSignal(str)

    def __init__(self, char: str, parent=None):
        super().__init__(char, parent)
        self._char = char
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(28, 28)
        self.setStyleSheet(CELL_NORMAL_STYLE)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        cp = ord(char)
        name = ""
        try:
            name = unicodedata.name(char, "")
        except Exception:
            pass
        self.setToolTip(f"U+{cp:04X}  {name}")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked_char.emit(self._char)
        super().mousePressEvent(ev)

    def enterEvent(self, ev):
        self.setStyleSheet(CELL_HOVER_STYLE)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.setStyleSheet(CELL_NORMAL_STYLE)
        super().leaveEvent(ev)


class GlyphsPanel(QWidget):
    char_inserted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        self._current_font_family = ""
        self._filter_text = ""
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(300)
        self._rebuild_timer.timeout.connect(self._rebuild_grid)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # ---------- Header ----------
        self._header_lbl = QLabel("GLYPHS")
        self._header_lbl.setStyleSheet(HEADER_STYLE)
        layout.addWidget(self._header_lbl)

        # ---------- Font selector ----------
        self._font_combo = QFontComboBox()
        self._font_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._font_combo.currentFontChanged.connect(self._on_font_changed)
        layout.addWidget(self._font_combo)

        # ---------- Search ----------
        self._search = QLineEdit()
        self._search.setPlaceholderText(
            tr("glyphs.search_hint") if tr("glyphs.search_hint") != "glyphs.search_hint"
            else "Search (name or U+XXXX)..."
        )
        self._search.setStyleSheet(SEARCH_STYLE)
        self._search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search)

        # ---------- Glyph grid ----------
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_host = QWidget()
        self._grid_host.setObjectName("panel")
        self._grid_layout = QGridLayout(self._grid_host)
        self._grid_layout.setContentsMargins(2, 2, 2, 2)
        self._grid_layout.setSpacing(2)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._scroll.setWidget(self._grid_host)
        layout.addWidget(self._scroll, 1)

        # ---------- Bottom bar: preview + info ----------
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#313244;background:#313244;max-height:1px;")
        layout.addWidget(sep)

        bottom_bar = QWidget()
        bottom_lo = QHBoxLayout(bottom_bar)
        bottom_lo.setContentsMargins(0, 4, 0, 0)
        bottom_lo.setSpacing(8)

        self._preview_lbl = QLabel("")
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setFixedSize(52, 52)
        self._preview_lbl.setStyleSheet(PREVIEW_STYLE)
        bottom_lo.addWidget(self._preview_lbl)

        info_widget = QWidget()
        info_lo = QVBoxLayout(info_widget)
        info_lo.setContentsMargins(0, 0, 0, 0)
        info_lo.setSpacing(2)

        self._info_code = QLabel("")
        self._info_code.setStyleSheet(INFO_STYLE)
        self._info_name = QLabel("")
        self._info_name.setStyleSheet(INFO_STYLE)
        self._info_name.setWordWrap(True)

        info_lo.addWidget(self._info_code)
        info_lo.addWidget(self._info_name)
        info_lo.addStretch()
        bottom_lo.addWidget(info_widget, 1)

        layout.addWidget(bottom_bar)

        # Initial population
        self._rebuild_grid()

    # ---------------------------------------------------------------- Event handlers

    def _on_font_changed(self, font: QFont):
        self._current_font_family = font.family()
        self._rebuild_timer.start()

    def _on_search_changed(self, text: str):
        self._filter_text = text.strip()
        self._rebuild_timer.start()

    def _on_cell_clicked(self, char: str):
        cp = ord(char)
        name = ""
        try:
            name = unicodedata.name(char, "")
        except Exception:
            pass

        # Update preview
        f = QFont(self._current_font_family if self._current_font_family else "")
        f.setPointSize(24)
        self._preview_lbl.setFont(f)
        self._preview_lbl.setText(char)
        self._info_code.setText(f"U+{cp:04X}")
        self._info_name.setText(name)

        self.char_inserted.emit(char)

    # ---------------------------------------------------------------- Grid rebuild

    def _get_chars(self) -> list[str]:
        ftext = self._filter_text
        if not ftext:
            result = []
            for cp in _DEFAULT_RANGES:
                try:
                    ch = chr(cp)
                    unicodedata.category(ch)  # ensure valid
                    if unicodedata.category(ch) not in ("Cc", "Cs"):
                        result.append(ch)
                except Exception:
                    pass
            return result

        # Search mode
        result = []

        # Check if it's a U+XXXX query
        upper = ftext.upper()
        if upper.startswith("U+"):
            hex_part = upper[2:]
            try:
                cp = int(hex_part, 16)
                ch = chr(cp)
                if unicodedata.category(ch) not in ("Cc", "Cs"):
                    result.append(ch)
                    return result
            except Exception:
                pass

        # Search by name substring (search first 65536 codepoints for speed)
        search_upper = ftext.upper()
        for cp in range(0x0020, 0x10000):
            try:
                ch = chr(cp)
                cat = unicodedata.category(ch)
                if cat in ("Cc", "Cs"):
                    continue
                name = unicodedata.name(ch, "")
                if search_upper in name:
                    result.append(ch)
                    if len(result) >= 256:
                        break
            except Exception:
                pass
        return result

    def _rebuild_grid(self):
        # Clear existing cells
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        chars = self._get_chars()
        font_family = self._current_font_family

        for idx, ch in enumerate(chars):
            row = idx // COLUMNS
            col = idx % COLUMNS
            cell = _GlyphCell(ch)
            if font_family:
                f = QFont(font_family)
                f.setPointSize(11)
                cell.setFont(f)
            cell.clicked_char.connect(self._on_cell_clicked)
            self._grid_layout.addWidget(cell, row, col)

        # Fill remaining columns in last row with empty spacers
        total = len(chars)
        if total > 0:
            last_row = (total - 1) // COLUMNS
            filled = total % COLUMNS
            if filled != 0:
                for col in range(filled, COLUMNS):
                    spacer = QLabel("")
                    spacer.setFixedSize(28, 28)
                    self._grid_layout.addWidget(spacer, last_row, col)

    # ---------------------------------------------------------------- Public

    def retranslate(self):
        self._header_lbl.setText(
            tr("glyphs.title") if tr("glyphs.title") != "glyphs.title" else "GLYPHS"
        )
        self._search.setPlaceholderText(
            tr("glyphs.search_hint") if tr("glyphs.search_hint") != "glyphs.search_hint"
            else "Search (name or U+XXXX)..."
        )
