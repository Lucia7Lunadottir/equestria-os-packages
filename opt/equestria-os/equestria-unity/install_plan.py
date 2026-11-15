"""Map a Linux release manifest to the components offered in the installer."""
import json
import platform
from urllib.parse import urlencode
from urllib.request import urlopen

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QLabel,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from kit import tr
from releases import ENDPOINT


def size_text(amount):
    if not isinstance(amount, (float, int)) or amount < 0:
        return str(tr("install.unknown_size"))
    return f"{amount / 1024**3:.2f} GiB" if amount >= 1024**3 else f"{amount / 1024**2:.1f} MiB"


def linux_download(release):
    arch = "ARM64" if platform.machine().lower() in ("arm64", "aarch64") else "X86_64"
    for entry in release.get("downloads", []):
        if entry.get("platform") == "LINUX" and entry.get("architecture") == arch:
            if isinstance(entry.get("modules"), list):
                return entry
    raise ValueError(tr("install.no_manifest"))


def fetch_manifest(version):
    query = urlencode({"version": version, "platform": "LINUX", "limit": 10})
    with urlopen(f"{ENDPOINT}?{query}", timeout=15) as response:
        for release in json.load(response)["results"]:
            if release.get("version") == version:
                return linux_download(release)
    raise ValueError(tr("install.no_manifest"))


class Components(QDialog):
    def __init__(self, version, modules, chosen, accepted, parent):
        super().__init__(parent)
        self.setWindowTitle(f"Unity {version} · {tr('editor.module_list')}")
        self.resize(630, 490)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("install.choose")))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("editor.module_list"), tr("install.size")])
        self.tree.setColumnWidth(0, 420)
        layout.addWidget(self.tree)
        self.nodes = []

        def add(entries, parent_item):
            for entry in entries:
                identifier = entry["id"]
                size = entry.get("downloadSize") or {}
                item = QTreeWidgetItem(parent_item, [entry.get("name") or identifier,
                                       entry.get("download") or size_text(size.get("value"))])
                installed = bool(entry.get("isInstalled"))
                item.setCheckState(0, Qt.CheckState.Checked if installed or identifier in chosen
                                   else Qt.CheckState.Unchecked)
                if installed:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                self.nodes.append((item, identifier, installed))
                add(entry.get("subModules") or [], item)

        add(modules, self.tree.invisibleRootItem())
        self.tree.itemChanged.connect(self.dependencies)
        self.tree.expandToDepth(0)
        self.eula = QCheckBox(tr("editor.eula"))
        self.eula.setChecked(accepted)
        layout.addWidget(self.eula)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("install.next"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def dependencies(self, item, column):
        if column != 0:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            parent = item.parent()
            if parent and parent.checkState(0) != Qt.CheckState.Checked:
                parent.setCheckState(0, Qt.CheckState.Checked)
        else:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.flags() & Qt.ItemFlag.ItemIsEnabled:
                    child.setCheckState(0, Qt.CheckState.Unchecked)

    def selection(self):
        return [identifier for item, identifier, installed in self.nodes
                if not installed and item.checkState(0) == Qt.CheckState.Checked]
