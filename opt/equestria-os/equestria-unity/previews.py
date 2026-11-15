"""Asynchronous thumbnails shared by the template cards."""
from hashlib import sha256
from pathlib import Path

from PyQt6.QtCore import QObject, QStandardPaths, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest


class Previews(QObject):
    ready = pyqtSignal(str, QIcon)

    def __init__(self, parent):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self.network)
        cache.setCacheDirectory(str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / "previews"))
        cache.setMaximumCacheSize(48 * 1024 * 1024)
        self.network.setCache(cache)
        self.pending = set()
        self.icons = {}

    def get(self, source):
        if isinstance(source, bytes):
            key = sha256(source).hexdigest()
            if key not in self.icons:
                self.store(key, source)
            return self.icons.get(key)
        if source in self.icons:
            return self.icons[source]
        if source in self.pending or QUrl(source).scheme() != "https":
            return None
        self.pending.add(source)
        request = QNetworkRequest(QUrl(source))
        request.setTransferTimeout(15000)
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                             QNetworkRequest.CacheLoadControl.PreferCache)
        reply = self.network.get(request)
        reply.finished.connect(lambda: self.finish(source, reply))
        return None

    def finish(self, key, reply):
        self.pending.discard(key)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            icon = self.store(key, bytes(reply.readAll()))
            if icon:
                self.ready.emit(key, icon)
        reply.deleteLater()

    def store(self, key, data):
        pix = QPixmap()
        if len(data) <= 12 * 1024 * 1024 and pix.loadFromData(data):
            pix = pix.scaled(270, 140, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
            icon = QIcon(pix.copy((pix.width()-270)//2, (pix.height()-140)//2, 270, 140))
            if len(self.icons) >= 128:
                self.icons.pop(next(iter(self.icons)))
            self.icons[key] = icon
            return icon
        return None
