"""What Unity's release catalog says about installed Editors, asked once per session:
- per release line (6000.6): its channel and newest patch for Linux;
- per version: the badge Unity Hub shows on it — a security alert or a warning, with Unity's text and link.
Without a network the cards simply show less."""
import json
import re

from PyQt6.QtCore import QObject, QUrl, QUrlQuery, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from versions import RELEASE, version_key

ENDPOINT = "https://services.api.unity.com/unity/editor/release/v1/releases"

LINK = re.compile(r'href="([^"]+)"')
TAG = re.compile(r"<[^>]+>")


def line_of(version):
    """6000.6.9f1 -> 6000.6"""
    return ".".join(version.split(".")[:2])


class ReleaseLabel:
    """Unity's badge on a release: kind is "security" (its builds are vulnerable) or "warning"."""

    def __init__(self, data):
        description = str(data.get("description") or "")
        title = str(data.get("labelText") or "")
        self.kind = "security" if "security" in title.casefold() or data.get("color") == "ERROR" else "warning"
        self.text = " ".join(TAG.sub("", description).split())
        found = LINK.search(description)
        self.link = found.group(1) if found and found.group(1).startswith("https://") else ""

    @classmethod
    def of(cls, release):
        data = release.get("label") if isinstance(release, dict) else None
        return cls(data) if isinstance(data, dict) and (data.get("description") or data.get("labelText")) else None


class ReleaseInfo(QObject):
    updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.lines = {}        # line -> {"stream": "LTS", "latest": "6000.6.10f1"}
        self.labels = {}       # version -> ReleaseLabel or None (known to have none)
        self.pending = set()

    def get(self, version):
        """Known facts about the version's line, or {} (and a request is sent once)."""
        line = line_of(version)
        if line not in self.lines:
            self.request(("line", line), line + ".", 25)
        return self.lines.get(line, {})

    def label(self, version):
        """The badge on this exact version, or None (also while it is being asked)."""
        if version not in self.labels:
            self.request(("version", version), version, 5)
        return self.labels.get(version)

    def request(self, key, prefix, limit):
        if key in self.pending:
            return
        self.pending.add(key)
        url = QUrl(ENDPOINT)
        query = QUrlQuery()
        for name, value in (("platform", "LINUX"), ("limit", str(limit)), ("version", prefix)):
            query.addQueryItem(name, value)
        url.setQuery(query)
        request = QNetworkRequest(url)
        request.setTransferTimeout(15000)
        reply = self.network.get(request)
        reply.finished.connect(lambda: self.received(key, reply))

    def received(self, key, reply):
        reply.deleteLater()
        self.pending.discard(key)
        if reply.error() != QNetworkReply.NetworkError.NoError:
            return  # asked again next session; nothing to show now
        try:
            records = json.loads(bytes(reply.readAll()))["results"]
        except (ValueError, KeyError, TypeError):
            return
        records = [r for r in records if isinstance(r, dict) and isinstance(r.get("version"), str)
                   and RELEASE.fullmatch(r["version"])]
        kind, value = key
        if kind == "version":
            exact = next((r for r in records if r["version"] == value), None)
            self.labels[value] = ReleaseLabel.of(exact)
        else:
            stable = [r for r in records if line_of(r["version"]) == value]
            if not stable:
                return
            newest = max(stable, key=lambda r: version_key(r["version"]))
            self.lines[value] = {"stream": str(newest.get("stream") or ""), "latest": newest["version"]}
        self.updated.emit()
