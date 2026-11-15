import shlex
from PyQt6.QtCore import QRectF, QSize, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                             QMessageBox, QPushButton, QVBoxLayout, QWidget)

import library
from kit import call, qt, tr


def chip(text, level=""):
    """Small rounded label. level: '', 'ok', 'warn' or 'fail'."""
    label = QLabel(str(text))
    label.setObjectName("chip")
    label.setProperty("lvl", level)
    return label


def tile(text, seed=None, width=48, height=48, radius=12):
    """Coloured square with a letter. The colour comes from the name, so every project looks different."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(clip)
    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0, QColor.fromHsl(library.seed(seed or text) % 360, 110, 70))
    gradient.setColorAt(1, qt.theme_color("surface1"))
    painter.fillRect(0, 0, width, height, gradient)
    font = QFont()
    font.setPixelSize(int(height * (0.5 if len(text) < 2 else 0.34)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255, 220))
    painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return pixmap


def icon(text, seed=None, size=QSize(220, 124)):
    return QIcon(tile(text, seed, size.width(), size.height(), 14))


def open_folder(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class Worker(QThread):
    """Runs a function off the interface thread and hands its result (or exception) back."""
    done = pyqtSignal(object)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            result = self.function()
        except Exception as error:  # reported to the caller, not lost in a thread
            result = error
        self.done.emit(result)


class Page(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.config = window.config
        self.jobs = window.jobs
        self.workers = set()
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(28, 24, 28, 20)
        self.layout_box.setSpacing(14)

    def title(self, key, *widgets):
        """Page heading on the left, optional widgets on the right. Returns the heading row."""
        layout = QHBoxLayout()
        layout.setSpacing(8)
        label = call(QLabel, tr(key))
        label.setObjectName("title")
        layout.addWidget(label)
        layout.addStretch()
        for widget in widgets:
            layout.addWidget(widget)
        self.layout_box.addLayout(layout)
        return layout

    def row(self):
        layout = QHBoxLayout()
        self.layout_box.addLayout(layout)
        return layout

    def card(self, parent=None, name="card"):
        """A rounded panel. Returns (frame, inner vertical layout); the frame is added to `parent`."""
        frame = QFrame()
        frame.setObjectName(name)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(16, 14, 16, 14)
        inner.setSpacing(10)
        (parent if parent is not None else self.layout_box).addWidget(frame)
        return frame, inner

    def button(self, layout, key, callback, name="small"):
        button = call(QPushButton, tr(key))
        button.setObjectName(name)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda: callback())
        layout.addWidget(button)
        return button

    def label(self, layout, key, name="hint"):
        label = call(QLabel, tr(key))
        label.setObjectName(name)
        label.setWordWrap(True)
        layout.addWidget(label)
        return label

    def text(self, key, initial=""):
        value, ok = QInputDialog.getText(self, self.window.windowTitle(), tr(key), text=initial)
        return value.strip() if ok else ""

    def confirm(self, key, *args):
        return QMessageBox.question(self, self.window.windowTitle(), tr(key, *args),
                                    defaultButton=QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def edit_arguments(self, key, current, save):
        value, ok = QInputDialog.getText(self, self.window.windowTitle(), tr(key), text=current)
        if ok:
            try:
                shlex.split(value)
            except ValueError as error:
                self.warning(error)
                return
            save(value.strip())

    def folder(self, key, start=""):
        return QFileDialog.getExistingDirectory(self, tr(key), start)

    def warning(self, message):
        QMessageBox.warning(self, self.window.windowTitle(), str(message))

    def save(self, key, value):
        return self.config.set(key, value)

    def background(self, function, done):
        worker = Worker(function, self)
        self.workers.add(worker)

        def finished():
            self.workers.discard(worker)
            worker.deleteLater()

        worker.done.connect(done, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        worker.start()
