"""The Git panel of one project: what has changed in plain words, and the everyday steps — receive, commit, send,
switch branch — as clear buttons. Anything beyond that opens in a real Git client."""
from PyQt6 import sip
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout)

from formatting import bad_name, short
from git_info import read_branches, read_git_with_status
from git_tools import git_client
from kit import call, tr

KIND_KEYS = {"modified": "git.kind_modified", "added": "git.kind_added", "deleted": "git.kind_deleted",
             "renamed": "git.kind_renamed", "untracked": "git.kind_untracked", "conflict": "git.kind_conflict"}
CHANGE = Qt.ItemDataRole.UserRole


class GitPanel(QDialog):
    def __init__(self, actions, project, parent):
        super().__init__(parent)
        self.git = actions              # GitActions: runs git through the launcher's operations
        self.page = actions.page
        self.project = project
        self.info = project.git
        self.branches = []
        call(self.setWindowTitle, tr("git.panel_title", project.name))
        self.resize(720, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(12)

        head = QHBoxLayout()
        self.title = QLabel(project.name)
        self.title.setObjectName("title")
        head.addWidget(self.title)
        head.addStretch()
        self.where = QLabel()
        self.where.setObjectName("hint")
        self.where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        head.addWidget(self.where)
        layout.addLayout(head)

        branch = QHBoxLayout()
        branch.addWidget(call(QLabel, tr("git.branch_label")))
        self.branch = QComboBox()
        self.branch.setMinimumWidth(220)
        self.branch.activated.connect(self.switch_branch)
        branch.addWidget(self.branch)
        self.new_branch_button = self.small(branch, tr("git.new_branch"), self.new_branch)
        branch.addStretch()
        self.check_button = self.small(branch, tr("git.fetch"), self.fetch)
        layout.addLayout(branch)

        summary = QFrame()
        summary.setObjectName("card")
        box = QVBoxLayout(summary)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(4)
        self.local_state = QLabel()
        self.local_state.setObjectName("rowname")
        self.server_state = QLabel()
        self.server_state.setWordWrap(True)
        box.addWidget(self.local_state)
        box.addWidget(self.server_state)
        layout.addWidget(summary)

        sync = QHBoxLayout()
        self.pull_button = self.primary(sync, tr("git.pull"), self.pull)
        self.push_button = self.primary(sync, tr("git.push"), self.push)
        sync.addStretch()
        layout.addLayout(sync)
        self.sync_hint = QLabel()
        self.sync_hint.setObjectName("hint")
        self.sync_hint.setWordWrap(True)
        layout.addWidget(self.sync_hint)

        self.changes_title = call(QLabel, tr("git.changes_title"))
        self.changes_title.setObjectName("rowname")
        layout.addWidget(self.changes_title)
        self.changes = QListWidget()
        self.changes.setObjectName("folders")
        self.changes.itemChanged.connect(lambda _: self.update_buttons())
        layout.addWidget(self.changes, 1)
        commit = QHBoxLayout()
        self.message = QLineEdit()
        call(self.message.setPlaceholderText, tr("git.message"))
        self.message.textChanged.connect(lambda _: self.update_buttons())
        self.message.returnPressed.connect(self.commit)
        commit.addWidget(self.message, 1)
        self.commit_button = self.primary(commit, tr("git.commit"), self.commit)
        layout.addLayout(commit)

        bottom = QHBoxLayout()
        client = git_client()
        self.client_button = self.small(bottom, tr("git.open_client"), lambda: self.git.open_client(
            git_client(), self.info.root))
        self.client_button.setEnabled(client is not None)
        if client is None:
            call(self.client_button.setToolTip, tr("git.no_client"))
        self.web_button = self.small(bottom, tr("git.web"), lambda: QDesktopServices.openUrl(QUrl(self.info.web)))
        self.reviews_button = self.small(bottom, tr("git.reviews"),
                                         lambda: QDesktopServices.openUrl(QUrl(self.info.reviews)))
        self.copy_button = self.small(bottom, tr("git.copy_url"),
                                      lambda: QGuiApplication.clipboard().setText(self.info.remote))
        bottom.addStretch()
        self.small(bottom, tr("folders.done"), self.accept)
        layout.addLayout(bottom)
        self.busy = False
        self.show_state()
        self.reload()

    @staticmethod
    def small(layout, text, callback):
        button = call(QPushButton, text)
        button.setObjectName("small")
        button.setAutoDefault(False)
        button.clicked.connect(lambda: callback())
        layout.addWidget(button)
        return button

    def primary(self, layout, text, callback):
        button = self.small(layout, text, callback)
        button.setObjectName("primary")
        return button

    # ---- reading ------------------------------------------------------------------------------------

    def alive(self):
        return not sip.isdeleted(self)

    def reload(self):
        """Read the repository again (after every step and when the panel opens), off the interface thread."""
        path = self.project.path

        def read():
            info = read_git_with_status(path)
            return info, read_branches(info.root) if info else []

        def done(result):
            if not self.alive() or isinstance(result, Exception):
                return
            self.info, self.branches = result
            self.busy = False
            self.show_state()
            self.page.window.catalog.refresh()   # the table's Git column shows the same state
        self.page.background(read, done)

    def show_state(self):
        info = self.info
        status = info.status if info else None
        self.where.setText(info.web.removeprefix("https://") if info and info.web else short(info.root) if info else "")
        self.branch.blockSignals(True)
        self.branch.clear()
        for name in self.branches or ([info.branch] if info else []):
            self.branch.addItem(name, name)
        if info:
            self.branch.setCurrentIndex(max(0, self.branch.findData(info.branch)))
        self.branch.blockSignals(False)
        changes = status.changes if status else []
        if changes:
            call(self.local_state.setText, tr("git.state_changed", len(changes)))
        else:
            call(self.local_state.setText, tr("git.state_clean"))
        if status is None:
            text = tr("git.state_unknown")
        elif not info.remote:
            text = tr("git.state_no_remote")
        elif not status.upstream:
            text = tr("git.state_not_on_server", info.branch)
        elif status.ahead and status.behind:
            text = tr("git.state_both", status.ahead, status.behind)
        elif status.ahead:
            text = tr("git.state_ahead", status.ahead)
        elif status.behind:
            text = tr("git.state_behind", status.behind)
        else:
            text = tr("git.state_synced")
        call(self.server_state.setText, text)
        self.changes.blockSignals(True)
        self.changes.clear()
        for change in changes:
            item = QListWidgetItem(f"{tr(KIND_KEYS[change.kind])} · {change.path}", self.changes)
            item.setData(CHANGE, change)
            item.setCheckState(Qt.CheckState.Checked)
        self.changes.blockSignals(False)
        for widget in (self.changes_title, self.changes, self.message, self.commit_button):
            widget.setVisible(bool(changes))
        self.web_button.setVisible(bool(info and info.web))
        self.reviews_button.setVisible(bool(info and info.reviews))
        self.copy_button.setVisible(bool(info and info.remote))
        self.update_buttons()

    def chosen(self):
        paths = []
        for row in range(self.changes.count()):
            item = self.changes.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                paths.extend(item.data(CHANGE).paths())
        return paths

    def update_buttons(self):
        info = self.info
        status = info.status if info else None
        ready = info is not None and not self.busy
        has_remote = bool(info and info.remote)
        self.pull_button.setEnabled(ready and has_remote and bool(status and status.upstream))
        self.push_button.setEnabled(ready and has_remote and bool(status) and (status.ahead > 0 or not status.upstream))
        self.check_button.setEnabled(ready and has_remote)
        self.commit_button.setEnabled(ready and bool(self.chosen()) and bool(self.message.text().strip()))
        self.branch.setEnabled(ready)
        self.new_branch_button.setEnabled(ready)
        conflicts = bool(status and any(c.kind == "conflict" for c in status.changes))
        call(self.sync_hint.setText, tr("git.hint_conflict") if conflicts else tr("git.hint_sync"))

    # ---- steps ------------------------------------------------------------------------------------

    def step(self):
        """Each step is one launcher operation (shown in the top bar and the log); whatever happened, the state
        is read again afterwards. Returns (done, failed) for GitActions."""
        self.busy = True
        self.update_buttons()
        after = lambda _: self.alive() and self.reload()
        return after, after

    def fetch(self):
        self.git.fetch(self.info.root, *self.step())

    def pull(self):
        self.git.pull(self.info.root, *self.step())

    def push(self):
        status = self.info.status
        if not self.page.confirm("git.confirm_push", self.info.branch, self.info.web or self.info.remote):
            return
        self.git.push(self.info.root, self.info.branch, status.upstream if status else "", *self.step())

    def commit(self):
        paths = self.chosen()
        message = self.message.text().strip()
        if not paths or not message:
            return
        self.git.commit(self.info.root, paths, message, *self.step())
        self.message.clear()

    def switch_branch(self, index):
        name = self.branch.itemData(index)
        if name and name != self.info.branch:
            self.git.switch(self.info.root, name, *self.step())

    def new_branch(self):
        name, ok = QInputDialog.getText(self, self.windowTitle(), str(tr("git.new_branch_name")))
        name = name.strip()
        if ok and name:
            if name.startswith("-") or bad_name(name.replace("/", "_")):
                self.page.warning(tr("git.bad_branch"))
                return
            self.git.new_branch(self.info.root, name, *self.step())
