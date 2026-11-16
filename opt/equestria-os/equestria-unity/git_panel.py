"""The Git panel of one project: what has changed in plain words, and the everyday steps — receive, commit, send,
switch and merge branches, resolve conflicts — as clear buttons. History and anything rarer opens in a Git client.

Merging is careful: it starts only from a clean working tree and after a confirmation; while it is unfinished,
nothing else can be done but resolving it or cancelling it (which restores the state before the merge)."""
from PyQt6 import sip
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout)

import git_merge
from formatting import bad_name, short
from git_info import read_branches, read_git_with_status
from git_tools import explain_git, git_client
from kit import call, tr

KIND_KEYS = {"modified": "git.kind_modified", "added": "git.kind_added", "deleted": "git.kind_deleted",
             "renamed": "git.kind_renamed", "untracked": "git.kind_untracked", "conflict": "git.kind_conflict"}
CONFLICT_KEYS = {"UU": "git.conflict_both", "AA": "git.conflict_added_both", "UD": "git.conflict_deleted_theirs",
                 "DU": "git.conflict_deleted_ours", "DD": "git.conflict_deleted_both"}
CHANGE = Qt.ItemDataRole.UserRole


class GitPanel(QDialog):
    def __init__(self, actions, project, parent):
        super().__init__(parent)
        self.git = actions              # GitActions: runs git through the launcher's operations
        self.page = actions.page
        self.project = project
        self.info = project.git
        self.branches = []
        self.busy = False
        self.smart_after_merge = False  # a merge started here: try Unity's merge on scenes once it stops
        call(self.setWindowTitle, tr("git.panel_title", project.name))
        self.resize(760, 700)
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
        self.merge_branch_button = self.small(branch, tr("git.merge_branch_button"), self.merge_branch)
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
        self.merge_remote_button = self.primary(sync, tr("git.merge_remote"), self.merge_remote)
        self.push_button = self.primary(sync, tr("git.push"), self.push)
        sync.addStretch()
        layout.addLayout(sync)
        self.sync_hint = QLabel()
        self.sync_hint.setObjectName("hint")
        self.sync_hint.setWordWrap(True)
        layout.addWidget(self.sync_hint)

        # ---- an unfinished merge: only resolving or cancelling it is possible
        self.merge_box = QFrame()
        self.merge_box.setObjectName("card")
        merge = QVBoxLayout(self.merge_box)
        merge.setContentsMargins(16, 12, 16, 12)
        merge.setSpacing(8)
        self.merge_state = QLabel()
        self.merge_state.setObjectName("rowname")
        merge.addWidget(self.merge_state)
        hint = call(QLabel, tr("git.merge_hint"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        merge.addWidget(hint)
        self.conflicts = QListWidget()
        self.conflicts.setObjectName("folders")
        self.conflicts.itemSelectionChanged.connect(self.update_buttons)
        merge.addWidget(self.conflicts, 1)
        row = QHBoxLayout()
        self.ours_button = self.small(row, tr("git.take_ours"), lambda: self.take("ours"))
        self.theirs_button = self.small(row, tr("git.take_theirs"), lambda: self.take("theirs"))
        self.smart_button = self.small(row, tr("git.smart_merge"), self.smart_one)
        self.open_button = self.small(row, tr("git.open_file"), self.open_file)
        self.resolved_button = self.small(row, tr("git.mark_resolved"), self.mark_resolved)
        row.addStretch()
        merge.addLayout(row)
        row = QHBoxLayout()
        self.finish_button = self.primary(row, tr("git.finish_merge"), self.finish_merge)
        self.abort_button = self.small(row, tr("git.abort_merge"), self.abort_merge)
        self.abort_button.setObjectName("danger")
        row.addStretch()
        merge.addLayout(row)
        layout.addWidget(self.merge_box, 1)
        self.operation_note = QLabel()
        self.operation_note.setObjectName("err")
        self.operation_note.setWordWrap(True)
        layout.addWidget(self.operation_note)

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

    def status(self):
        return self.info.status if self.info else None

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
            if self.smart_after_merge:
                self.smart_after_merge = False
                self.smart_all()
        self.page.background(read, done)

    def show_state(self):
        info = self.info
        status = self.status()
        place = info.web.removeprefix("https://") if info and info.web else short(info.root) if info else ""
        self.where.setToolTip(place)
        self.where.setText(self.where.fontMetrics().elidedText(place, Qt.TextElideMode.ElideMiddle, 380))
        self.branch.blockSignals(True)
        self.branch.clear()
        for name in self.branches or ([info.branch] if info else []):
            self.branch.addItem(name, name)
        if info:
            self.branch.setCurrentIndex(max(0, self.branch.findData(info.branch)))
        self.branch.blockSignals(False)
        operation = status.operation if status else ""
        merging = operation == "merge"
        changes = [c for c in status.changes if c.kind != "conflict"] if status else []
        conflicts = status.conflicts() if status else []
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
            text = tr("git.state_diverged", status.ahead, status.behind)
        elif status.ahead:
            text = tr("git.state_ahead", status.ahead)
        elif status.behind:
            text = tr("git.state_behind", status.behind)
        else:
            text = tr("git.state_synced")
        call(self.server_state.setText, text)

        self.merge_box.setVisible(merging)
        call(self.merge_state.setText, tr("git.merge_conflicts", len(conflicts)) if conflicts else tr("git.merge_ready"))
        self.conflicts.clear()
        for change in conflicts:
            label = tr(CONFLICT_KEYS.get(change.code, "git.kind_conflict"))
            item = QListWidgetItem(f"{label} · {change.path}", self.conflicts)
            item.setData(CHANGE, change)
        if conflicts:
            self.conflicts.setCurrentRow(0)
        self.operation_note.setVisible(bool(operation) and not merging)
        call(self.operation_note.setText, tr("git.operation_elsewhere", operation))

        self.changes.blockSignals(True)
        self.changes.clear()
        for change in changes:
            item = QListWidgetItem(f"{tr(KIND_KEYS[change.kind])} · {change.path}", self.changes)
            item.setData(CHANGE, change)
            item.setCheckState(Qt.CheckState.Checked)
        self.changes.blockSignals(False)
        for widget in (self.changes_title, self.changes, self.message, self.commit_button):
            widget.setVisible(bool(changes) and not operation)
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

    def selected_conflict(self):
        item = self.conflicts.currentItem()
        return item.data(CHANGE) if item else None

    def update_buttons(self):
        info = self.info
        status = self.status()
        ready = info is not None and status is not None and not self.busy
        free = ready and not status.operation           # no unfinished merge or rebase
        clean = ready and not status.local_changes()    # nothing a merge could mix with
        has_remote = bool(info and info.remote)
        upstream = bool(status and status.upstream)
        diverged = bool(status and status.ahead and status.behind)
        self.pull_button.setVisible(not diverged)
        self.merge_remote_button.setVisible(diverged)
        self.pull_button.setEnabled(free and has_remote and upstream)
        self.merge_remote_button.setEnabled(free and clean and has_remote and upstream)
        # Sending while the server has newer commits would only be refused: receive (or merge) first.
        self.push_button.setEnabled(free and has_remote and not (status.behind if status else 0)
                                    and bool(status) and (status.ahead > 0 or not upstream))
        self.check_button.setEnabled(free and has_remote)
        self.commit_button.setEnabled(free and bool(self.chosen()) and bool(self.message.text().strip()))
        self.branch.setEnabled(free)
        self.new_branch_button.setEnabled(free)
        self.merge_branch_button.setEnabled(free and clean and len(self.branches) > 1)
        if diverged and not clean:
            call(self.sync_hint.setText, tr("git.hint_commit_first"))
        else:
            call(self.sync_hint.setText, tr("git.hint_sync"))

        conflict = self.selected_conflict()
        merging = bool(status and status.operation == "merge")
        for button in (self.ours_button, self.theirs_button, self.open_button, self.resolved_button):
            button.setEnabled(ready and merging and conflict is not None)
        unity = conflict is not None and conflict.code == "UU" and git_merge.is_unity_yaml(conflict.path)
        self.smart_button.setVisible(unity)
        self.smart_button.setEnabled(ready and unity and self.merge_tool() is not None)
        if unity and self.merge_tool() is None:
            call(self.smart_button.setToolTip, tr("git.smart_no_tool"))
        self.finish_button.setEnabled(ready and merging and not status.conflicts())
        self.abort_button.setEnabled(ready and merging)

    def merge_tool(self):
        """UnityYAMLMerge of the project's Editor, or of any installed Editor."""
        editors = self.page.window.editors
        candidates = [editors.get(self.project.version)] + [editors.get(v) for v in editors.versions()]
        for editor in candidates:
            if editor is not None and git_merge.unity_merge_tool(editor):
                return git_merge.unity_merge_tool(editor)
        return None

    # ---- steps through the launcher's operations (shown in the top bar and the log) ----------------

    def step(self):
        """Whatever happened, the state is read again afterwards. Returns (done, failed) for GitActions."""
        self.busy = True
        self.update_buttons()
        after = lambda _: self.alive() and self.reload()
        return after, after

    def fetch(self):
        self.git.fetch(self.info.root, *self.step())

    def pull(self):
        self.git.pull(self.info.root, *self.step())

    def push(self):
        status = self.status()
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

    def merge_remote(self):
        if self.page.confirm("git.confirm_merge_remote"):
            self.smart_after_merge = True
            self.git.merge_remote(self.info.root, *self.step())

    def merge_branch(self):
        others = [name for name in self.branches if name != self.info.branch]
        if not others:
            return
        name, ok = QInputDialog.getItem(self, self.windowTitle(), str(tr("git.pick_branch", self.info.branch)),
                                        others, editable=False)
        if ok and name and self.page.confirm("git.confirm_merge_branch", name, self.info.branch):
            self.smart_after_merge = True
            self.git.merge_branch(self.info.root, name, *self.step())

    # ---- resolving, in the background (each step is small and reads the state again) --------------

    def background(self, function, done=None):
        self.busy = True
        self.update_buttons()

        def finished(result):
            if not self.alive():
                return
            if isinstance(result, Exception):
                self.page.warning(explain_git(str(result)))
            elif done:
                done(result)
            self.reload()
        self.page.background(function, finished)

    def take(self, side):
        change = self.selected_conflict()
        if change is not None:
            root = self.info.root
            self.background(lambda: git_merge.take(root, change, side))

    def mark_resolved(self):
        change = self.selected_conflict()
        if change is None:
            return
        root = self.info.root
        if git_merge.has_markers(root, change.path) and not self.page.confirm("git.confirm_markers", change.path):
            return
        self.background(lambda: git_merge.mark_resolved(root, change))

    def open_file(self):
        change = self.selected_conflict()
        if change is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.info.root / change.path)))

    def smart_one(self):
        change, tool, root = self.selected_conflict(), self.merge_tool(), self.info.root
        if change is not None and tool is not None:
            self.background(lambda: git_merge.smart_merge(root, change, tool),
                            lambda merged: merged or self.page.warning(tr("git.smart_failed")))

    def smart_all(self):
        """Right after a merge stops on conflicts: let UnityYAMLMerge try every conflicting scene and prefab.
        Only files it merges cleanly change; the rest stay for the user."""
        status, tool, root = self.status(), self.merge_tool(), self.info.root
        if not status or status.operation != "merge" or tool is None:
            return
        scenes = [c for c in status.conflicts() if c.code == "UU" and git_merge.is_unity_yaml(c.path)]
        if not scenes:
            return
        self.background(lambda: sum(git_merge.smart_merge(root, change, tool) for change in scenes),
                        lambda merged: self.page.window.notify(tr("git.smart_done", merged, len(scenes)),
                                                               "ok" if merged else ""))

    def finish_merge(self):
        root = self.info.root
        self.background(lambda: git_merge.finish_merge(root),
                        lambda _: self.page.window.notify(tr("git.merge_finished"), "ok"))

    def abort_merge(self):
        if self.page.confirm("git.confirm_abort"):
            root = self.info.root
            self.background(lambda: git_merge.abort_merge(root))
