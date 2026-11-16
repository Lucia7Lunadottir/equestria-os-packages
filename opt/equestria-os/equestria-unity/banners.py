"""Dismissible hints at the top of the page. Each hint is a Banner subclass; BannerBar shows the ones that apply."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from kit import call, tr
from versions import version_key


class Banner:
    """A hint about the launcher's real state. A subclass answers four questions and does one thing."""

    def __init__(self, window):
        self.window = window

    def key(self):
        """Identity for “dismissed”. When the situation changes (other versions missing) the key changes too."""
        raise NotImplementedError

    def applies(self):
        raise NotImplementedError

    def text(self):
        raise NotImplementedError

    def action_text(self):
        raise NotImplementedError

    def act(self):
        raise NotImplementedError


class CliMissingBanner(Banner):
    def key(self):
        return "cli"

    def applies(self):
        return not self.window.cli.executable()

    def text(self):
        return tr("banner.cli")

    def action_text(self):
        return tr("cli.download")

    def act(self):
        self.window.show_cli_settings()


class NoFoldersBanner(Banner):
    def key(self):
        return "folders"

    def applies(self):
        catalog = self.window.catalog
        return not catalog.scan_dirs() and not catalog.items

    def text(self):
        return tr("banner.folders")

    def action_text(self):
        return tr("projects.add_folder")

    def act(self):
        self.window.projects.add()


class MissingEditorsBanner(Banner):
    def missing(self):
        """Versions projects need that are not installed, newest first."""
        editors = self.window.editors
        return sorted((v for v in self.window.catalog.versions() if v not in editors), key=version_key, reverse=True)

    def key(self):
        return "editors:" + ",".join(self.missing())

    def applies(self):
        return bool(self.missing())

    def text(self):
        missing = self.missing()
        return tr("banner.editors", len(missing), ", ".join(missing[:3]))

    def action_text(self):
        return tr("editor.install_button")

    def act(self):
        missing = self.missing()
        if not missing:
            return
        version = missing[0]
        if len(missing) > 1:
            version, ok = QInputDialog.getItem(self.window, self.window.windowTitle(), str(tr("editor.pick_missing")),
                                               missing, editable=False)
            if not ok:
                return
        self.window.go("editors")
        self.window.installs.request_install(version)


class SecurityBanner(Banner):
    """Unity marked an installed Editor with a security alert: games built with it are vulnerable."""

    def affected(self):
        info = self.window.release_info
        return [v for v in self.window.editors.versions() if (info.label(v) or None) and info.label(v).kind == "security"]

    def key(self):
        return "security:" + ",".join(self.affected())

    def applies(self):
        return bool(self.affected())

    def text(self):
        affected = self.affected()
        return tr("banner.security", ", ".join(affected[:3]))

    def action_text(self):
        return tr("nav.editors")

    def act(self):
        self.window.go("editors")


BANNERS = (SecurityBanner, CliMissingBanner, NoFoldersBanner, MissingEditorsBanner)


class BannerBar(QWidget):
    def __init__(self, window, config):
        super().__init__()
        self.config = config
        self.banners = [kind(window) for kind in BANNERS]
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(16, 14, 16, 0)
        self.box.setSpacing(8)
        config.changed.connect(lambda key: key in ("banners_enabled", "dismissed_banners") and self.update_banners())
        window.catalog.changed.connect(self.update_banners)
        window.editors.changed.connect(self.update_banners)
        window.release_info.updated.connect(self.update_banners)

    def update_banners(self):
        while self.box.count():
            widget = self.box.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        shown = []
        if self.config.get("banners_enabled"):
            dismissed = set(self.config.get("dismissed_banners"))
            shown = [banner for banner in self.banners if banner.applies() and banner.key() not in dismissed]
        for banner in shown:
            self.box.addWidget(self.frame(banner))
        self.setVisible(bool(shown))

    def frame(self, banner):
        frame = QFrame()
        frame.setObjectName("banner")
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 8, 8, 8)
        row.setSpacing(10)
        label = call(QLabel, banner.text())
        label.setWordWrap(True)
        row.addWidget(label, 1)
        button = call(QPushButton, banner.action_text())
        button.setObjectName("small")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda: banner.act())
        row.addWidget(button)
        close = QPushButton("✕")
        close.setObjectName("flat")
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        key = banner.key()
        close.clicked.connect(lambda: self.config.update("dismissed_banners", lambda items: [*items, key]))
        row.addWidget(close)
        return frame
