"""Linux Editor release browser backed by Unity's paginated release archive."""
from PyQt6.QtCore import Qt, QSize, QTimer, QUrl, QUrlQuery
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                             QSizePolicy, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)
import json
import re

from kit import tr
from versions import version_key

ENDPOINT = "https://services.api.unity.com/unity/editor/release/v1/releases"


class ReleaseAction(QPushButton):
    def __init__(self, text, name, parent):
        super().__init__(text, parent)
        self.setObjectName(name)
        self.setAutoDefault(False)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        self.ensurePolished()
        text = self.fontMetrics().size(Qt.TextFlag.TextSingleLine, self.text())
        return super().sizeHint().expandedTo(text + QSize(28, 10))


class ReleaseRow(QTreeWidgetItem):
    def __lt__(self, other):
        if self.treeWidget().sortColumn() == 0:
            return version_key(self.data(0, Qt.ItemDataRole.UserRole)) < version_key(other.data(0, Qt.ItemDataRole.UserRole))
        return super().__lt__(other)


class ReleaseBrowser(QDialog):
    def __init__(self, installed, parent):
        super().__init__(parent)
        self.installed = set(installed)
        self.selected = ""
        self.selected_release = {}
        self.network = QNetworkAccessManager(self)
        self.reply = None
        self.setWindowTitle(tr("editor.install_title"))
        self.resize(880, 560)
        layout = QVBoxLayout(self)
        self.tabs = QTabBar()
        self.tabs.setObjectName("releaseTabs")
        self.tabs.setExpanding(False)
        for key in ("official", "preview", "archive"):
            self.tabs.addTab(tr("release." + key))
        layout.addWidget(self.tabs)
        self.filters = QHBoxLayout()
        self.family = QComboBox()
        self.family.addItem(tr("release.all"), "")
        for n in (7000, 6000, *range(2023, 2016, -1), 5):
            self.family.addItem("Unity " + str(n // 1000 if n >= 6000 else n), str(n) + ".")
        self.stream = QComboBox()
        self.stream.addItem(tr("release.all_channels"), "")
        for channel in ("SUPPORTED", "LTS", "TECH", "BETA", "ALPHA"):
            self.stream.addItem(channel, channel)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("editor.version"))
        for widget in (self.family, self.stream, self.search):
            self.filters.addWidget(widget)
        layout.addLayout(self.filters)
        self.rows = QTreeWidget()
        self.rows.setObjectName("releaseTable")
        self.rows.setSortingEnabled(True)
        self.rows.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self.rows.setRootIsDecorated(False)
        self.rows.setHeaderLabels([tr("editor.version"), tr("release.channel"), tr("release.date"),
                                   "", tr("release.actions")])
        header = self.rows.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.rows, 1)
        bottom = QHBoxLayout()
        self.status = QLabel()
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.more = QPushButton()
        self.more.clicked.connect(self.fetch)
        bottom.addWidget(self.more)
        close = QPushButton(tr("jobs.cancel_short"))
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fetch)
        self.tabs.currentChanged.connect(self.reset)
        self.family.currentIndexChanged.connect(self.reset)
        self.stream.currentIndexChanged.connect(self.reset)
        self.search.textChanged.connect(self.reset)
        self.reset()

    def reset(self, *_):
        if self.reply:
            reply, self.reply = self.reply, None
            reply.abort()
        self.rows.clear()
        self.seen = set()
        self.offset = 0
        self.more.hide()
        archive = self.tabs.currentIndex() == 2
        for widget in (self.search, self.family, self.stream):
            widget.setVisible(archive)
        self.status.setText(tr("release.loading"))
        self.timer.start(200)

    def fetch(self):
        if self.reply:
            return
        url = QUrl(ENDPOINT)
        query = QUrlQuery()
        for key, value in (("platform", "LINUX"), ("limit", "25"), ("offset", str(self.offset))):
            query.addQueryItem(key, value)
        if self.tabs.currentIndex() == 2:
            prefix = self.search.text().strip() or self.family.currentData()
            if prefix:
                query.addQueryItem("version", prefix)
            if self.stream.currentData():
                query.addQueryItem("stream", self.stream.currentData())
        url.setQuery(query)
        request = QNetworkRequest(url)
        request.setTransferTimeout(20000)
        self.more.hide()
        self.status.setText(tr("release.loading"))
        reply = self.network.get(request)
        self.reply = reply
        reply.finished.connect(lambda: self.received(reply))

    def received(self, reply):
        reply.deleteLater()
        if reply is not self.reply:
            return
        self.reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(reply.errorString())
            payload = json.loads(bytes(reply.readAll()))
            records = payload["results"]
            total = int(payload["total"])
            if not isinstance(records, list):
                raise ValueError("results")
        except (KeyError, ValueError, TypeError) as error:
            self.status.setText(str(tr("release.error", error)))
            self.more.setText(tr("release.retry"))
            self.more.show()
            return
        for entry in records:
            self.add_release(entry)
        self.offset += len(records)
        self.status.setText("" if self.rows.topLevelItemCount() else tr("projects.nothing"))
        self.more.setText(tr("release.more"))
        self.more.setVisible(bool(records) and self.offset < total)

    def add_release(self, entry):
        if not isinstance(entry, dict):
            return
        version = entry.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+[abfp]\d+(?:c\d+)?", version):
            return
        channel = str(entry.get("stream", ""))
        tab = self.tabs.currentIndex()
        preview = channel in ("ALPHA", "BETA")
        if tab < 2 and preview != (tab == 1):
            return
        if tab == 2 and not version.startswith(self.family.currentData()):
            return
        key = version if tab == 2 else (tuple(version.split(".")[:2]), channel)
        if key in self.seen:
            return
        self.seen.add(key)
        if entry.get("recommended"):
            channel += " · " + str(tr("release.recommended"))
        major, minor = version.split(".")[:2]
        label = f"Unity {int(major) // 1000}.{minor}  ({version})" if int(major) >= 6000 else version
        row = ReleaseRow([label, channel, str(entry.get("releaseDate", ""))[:10]])
        row.setData(0, Qt.ItemDataRole.UserRole, version)
        self.rows.addTopLevelItem(row)
        row.setSizeHint(0, QSize(self.rows.fontMetrics().horizontalAdvance(label) + 16, 36))
        cell = QWidget(self.rows.viewport())
        actions = QHBoxLayout(cell)
        actions.setContentsMargins(8, 4, 8, 4)
        actions.setSpacing(8)
        section = "alpha" if "a" in version else "beta" if "b" in version else "whats-new"
        link = QUrl(f"https://unity.com/releases/editor/{section}/{version}")
        notes_button = ReleaseAction(tr("release.notes"), "releaseNotes", cell)
        notes_button.setCursor(Qt.CursorShape.PointingHandCursor)
        notes_button.setToolTip(link.toString())
        notes_button.clicked.connect(lambda: self.open_notes(link))
        actions.addWidget(notes_button)
        installed = version in self.installed
        choose = ReleaseAction(tr("release.installed" if installed else "install.select"), "primary", cell)
        choose.setEnabled(not installed)
        choose.clicked.connect(lambda: self.choose(version, entry))
        actions.addWidget(choose)
        actions.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.rows.setItemWidget(row, 4, cell)
        cell.ensurePolished()
        row.setSizeHint(4, actions.sizeHint())

    def open_notes(self, link):
        if not QDesktopServices.openUrl(link):
            self.status.setText(tr("release.open_failed", link.toString()))

    def choose(self, version, entry=None):
        self.selected_release = entry or {}
        self.selected = version
        self.accept()
