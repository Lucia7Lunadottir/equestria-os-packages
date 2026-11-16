"""Linux Editor release list backed by Unity's paginated release archive. The first step of the install wizard."""
from PyQt6.QtCore import Qt, QSize, QTimer, QUrl, QUrlQuery, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                             QSizePolicy, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)
import json

from kit import call, tr
from release_info import ENDPOINT, ReleaseLabel  # noqa: F401  (ENDPOINT is also read from here)
from versions import RELEASE, release_title, version_key



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


ARCHIVE = 2  # tab index: every release, with filters


class ReleaseList(QWidget):
    """Releases for Linux in three tabs. `chosen(version, release)` is emitted when one is selected."""
    chosen = pyqtSignal(str, object)

    def __init__(self, installed, parent=None, *, tab=0, search=""):
        super().__init__(parent)
        self.installed = set(installed)
        self.selected = ""
        self.selected_release = {}
        self.network = QNetworkAccessManager(self)
        self.reply = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabBar()
        self.tabs.setObjectName("releaseTabs")
        self.tabs.setExpanding(False)
        for key in ("official", "preview", "archive"):
            self.tabs.addTab(tr("release." + key))
        layout.addWidget(self.tabs)
        self.filters = QHBoxLayout()
        self.family = QComboBox()
        call(self.family.addItem, tr("release.all"), "")
        for n in (7000, 6000, *range(2023, 2016, -1), 5):
            self.family.addItem("Unity " + str(n // 1000 if n >= 6000 else n), str(n) + ".")
        self.stream = QComboBox()
        call(self.stream.addItem, tr("release.all_channels"), "")
        for channel in ("SUPPORTED", "LTS", "TECH", "BETA", "ALPHA"):
            self.stream.addItem(channel, channel)
        self.search = QLineEdit(search)
        call(self.search.setPlaceholderText, tr("editor.version"))
        for widget in (self.family, self.stream, self.search):
            self.filters.addWidget(widget)
        layout.addLayout(self.filters)
        self.rows = QTreeWidget()
        self.rows.setObjectName("releaseTable")
        self.rows.setSortingEnabled(True)
        self.rows.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self.rows.setRootIsDecorated(False)
        call(self.rows.setHeaderLabels, [tr("editor.version"), tr("release.channel"), tr("release.date"),
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
        layout.addLayout(bottom)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fetch)
        self.tabs.currentChanged.connect(self.reset)
        self.family.currentIndexChanged.connect(self.reset)
        self.stream.currentIndexChanged.connect(self.reset)
        self.search.textChanged.connect(self.reset)
        self.tabs.setCurrentIndex(tab)
        self.reset()

    def reset(self, *_):
        if self.reply:
            reply, self.reply = self.reply, None
            reply.abort()
        self.rows.clear()
        self.seen = set()
        self.offset = 0
        self.more.hide()
        archive = self.tabs.currentIndex() == ARCHIVE
        for widget in (self.search, self.family, self.stream):
            widget.setVisible(archive)
        self.status.setText(str(tr("release.loading")))
        self.timer.start(200)

    def fetch(self):
        if self.reply:
            return
        url = QUrl(ENDPOINT)
        query = QUrlQuery()
        for key, value in (("platform", "LINUX"), ("limit", "25"), ("offset", str(self.offset))):
            query.addQueryItem(key, value)
        if self.tabs.currentIndex() == ARCHIVE:
            prefix = self.search.text().strip() or self.family.currentData()
            if prefix:
                query.addQueryItem("version", prefix)
            if self.stream.currentData():
                query.addQueryItem("stream", self.stream.currentData())
        url.setQuery(query)
        request = QNetworkRequest(url)
        request.setTransferTimeout(20000)
        self.more.hide()
        self.status.setText(str(tr("release.loading")))
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
            self.more.setText(str(tr("release.retry")))
            self.more.show()
            return
        for entry in records:
            self.add_release(entry)
        self.offset += len(records)
        self.status.setText("" if self.rows.topLevelItemCount() else str(tr("projects.nothing")))
        self.more.setText(str(tr("release.more")))
        self.more.setVisible(bool(records) and self.offset < total)

    def add_release(self, entry):
        if not isinstance(entry, dict):
            return
        version = entry.get("version")
        if not isinstance(version, str) or not RELEASE.fullmatch(version):
            return
        channel = str(entry.get("stream", ""))
        tab = self.tabs.currentIndex()
        preview = channel in ("ALPHA", "BETA")
        if tab < 2 and preview != (tab == 1):
            return
        if tab == ARCHIVE and not version.startswith(self.family.currentData()):
            return
        key = version if tab == ARCHIVE else (tuple(version.split(".")[:2]), channel)
        if key in self.seen:
            return
        self.seen.add(key)
        if entry.get("recommended"):
            channel += " · " + str(tr("release.recommended"))
        badge = ReleaseLabel.of(entry)
        if badge:
            channel += " · ⚠ " + str(tr("editor.security" if badge.kind == "security" else "editor.warning"))
        label = f"{release_title(version)}  ({version})" if int(version.split(".")[0]) >= 6000 else version
        row = ReleaseRow([label, channel, str(entry.get("releaseDate", ""))[:10]])
        row.setData(0, Qt.ItemDataRole.UserRole, version)
        if badge:
            row.setToolTip(1, badge.text)
        self.rows.addTopLevelItem(row)
        row.setSizeHint(0, QSize(self.rows.fontMetrics().horizontalAdvance(label) + 16, 36))
        cell = QWidget(self.rows.viewport())
        actions = QHBoxLayout(cell)
        actions.setContentsMargins(8, 4, 8, 4)
        actions.setSpacing(8)
        section = "alpha" if "a" in version else "beta" if "b" in version else "whats-new"
        link = QUrl(f"https://unity.com/releases/editor/{section}/{version}")
        notes_button = ReleaseAction(str(tr("release.notes")), "releaseNotes", cell)
        notes_button.setCursor(Qt.CursorShape.PointingHandCursor)
        notes_button.setToolTip(link.toString())
        notes_button.clicked.connect(lambda: self.open_notes(link))
        actions.addWidget(notes_button)
        installed = version in self.installed
        choose = ReleaseAction(str(tr("release.installed" if installed else "install.select")), "primary", cell)
        choose.setEnabled(not installed)
        choose.clicked.connect(lambda: self.choose(version, entry))
        actions.addWidget(choose)
        actions.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.rows.setItemWidget(row, 4, cell)
        cell.ensurePolished()
        row.setSizeHint(4, actions.sizeHint())

    def open_notes(self, link):
        if not QDesktopServices.openUrl(link):
            self.status.setText(str(tr("release.open_failed", link.toString())))

    def choose(self, version, entry=None):
        self.selected_release = entry or {}
        self.selected = version
        self.chosen.emit(version, self.selected_release)
