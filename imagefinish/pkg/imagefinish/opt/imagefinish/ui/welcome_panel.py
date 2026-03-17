import os

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QFont

from core.locale import tr


class _RecentItem(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(80)
        self.setStyleSheet("border-radius: 6px;")

        h = QHBoxLayout(self)
        h.setContentsMargins(8, 8, 8, 8)
        h.setSpacing(10)

        # Thumbnail
        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(64, 64)
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img = QImage(path)
        if not img.isNull():
            px = QPixmap.fromImage(
                img.scaled(64, 64,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation))
        else:
            px = QPixmap(64, 64)
            px.fill(Qt.GlobalColor.darkGray)
        thumb_lbl.setPixmap(px)
        h.addWidget(thumb_lbl)

        # Text
        text_v = QVBoxLayout()
        text_v.setSpacing(2)

        name_lbl = QLabel(os.path.basename(path))
        name_font = QFont()
        name_font.setBold(True)
        name_lbl.setFont(name_font)
        name_lbl.setStyleSheet("color: #cdd6f4; background: transparent;")

        path_lbl = QLabel()
        path_lbl.setStyleSheet("color: #a6adc8; font-size: 11px; background: transparent;")

        text_v.addStretch()
        text_v.addWidget(name_lbl)
        text_v.addWidget(path_lbl)
        text_v.addStretch()
        h.addLayout(text_v, 1)

        # Store reference to set elided text after widget is shown
        self._path_lbl = path_lbl
        self._full_path = path

    def showEvent(self, event):
        super().showEvent(event)
        fm = self._path_lbl.fontMetrics()
        elided = fm.elidedText(self._full_path, Qt.TextElideMode.ElideLeft,
                               self._path_lbl.width() or 260)
        self._path_lbl.setText(elided)

    def mousePressEvent(self, event):
        self.clicked.emit(self._path)

    def enterEvent(self, event):
        self.setStyleSheet("background: #313244; border-radius: 6px;")

    def leaveEvent(self, event):
        self.setStyleSheet("border-radius: 6px;")


class WelcomePanel(QWidget):
    new_requested       = pyqtSignal()
    open_requested      = pyqtSignal()
    open_path_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("welcomePanel")
        self.setStyleSheet("#welcomePanel { background: #1e1e2e; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setFixedWidth(520)
        inner.setStyleSheet("background: transparent;")
        v = QVBoxLayout(inner)
        v.setSpacing(16)
        v.setContentsMargins(0, 0, 0, 0)

        outer.addStretch()
        outer.addWidget(inner, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()

        # Title
        title = QLabel("LinuxPhotoshop")
        title_font = QFont()
        title_font.setPointSize(28)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #cba6f7; background: transparent;")
        v.addWidget(title)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        self._btn_new = QPushButton()
        self._btn_new.setFixedWidth(160)
        self._btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_new.clicked.connect(self.new_requested)

        self._btn_open = QPushButton()
        self._btn_open.setFixedWidth(160)
        self._btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open.clicked.connect(self.open_requested)

        btn_row.addWidget(self._btn_new)
        btn_row.addWidget(self._btn_open)
        btn_row.addStretch()
        v.addLayout(btn_row)

        # Recent separator label
        self._recent_lbl = QLabel()
        self._recent_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._recent_lbl.setStyleSheet("color: #585b70; font-size: 12px; background: transparent;")
        v.addWidget(self._recent_lbl)

        # Scroll area for recent files
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.setFixedHeight(320)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_v = QVBoxLayout(self._list_widget)
        self._list_v.setContentsMargins(0, 0, 0, 0)
        self._list_v.setSpacing(4)
        self._list_v.addStretch()

        self._scroll.setWidget(self._list_widget)
        v.addWidget(self._scroll)

        # Empty state label
        self._no_recent_lbl = QLabel()
        self._no_recent_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_recent_lbl.setStyleSheet("color: #585b70; background: transparent;")
        v.addWidget(self._no_recent_lbl)

        self._retranslate()

    def _retranslate(self):
        self._btn_new.setText(tr("welcome.new"))
        self._btn_open.setText(tr("welcome.open"))
        self._recent_lbl.setText(f"\u2500\u2500 {tr('welcome.recent')} \u2500\u2500")
        self._no_recent_lbl.setText(tr("welcome.no_recent"))

    def retranslate(self):
        self._retranslate()

    def refresh_recent(self, files: list):
        # Clear existing items (all except the trailing stretch)
        while self._list_v.count() > 1:
            item = self._list_v.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._retranslate()

        if not files:
            self._scroll.hide()
            self._no_recent_lbl.show()
            return

        self._no_recent_lbl.hide()
        self._scroll.show()

        for path in files:
            row = _RecentItem(path)
            row.clicked.connect(self.open_path_requested)
            self._list_v.insertWidget(self._list_v.count() - 1, row)
