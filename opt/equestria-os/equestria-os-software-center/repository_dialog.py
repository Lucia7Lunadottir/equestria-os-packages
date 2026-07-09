"""
repository_dialog.py — Equestria OS Software Center
UI for managing custom Pacman repositories (add / edit / remove).

Both dialogs only talk to the RepositoryStore abstraction (see
pacman_repo.py), never to pacman.conf directly, so the UI stays decoupled
from how/where repositories are actually persisted (DIP).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QListWidget, QListWidgetItem, QLineEdit, QPlainTextEdit, QMessageBox,
)
from PyQt6.QtCore import Qt

from pacman_repo import PacmanRepository, RepositoryError, RepositoryStore

_SIGLEVEL_PRESETS = ["", "Optional TrustAll", "Required TrustAll", "Never"]


class RepositoryEditDialog(QDialog):
    """Add/edit form for a single custom repository entry."""

    def __init__(self, parent, t, repo: PacmanRepository = None):
        super().__init__(parent)
        self.t = t
        self.result_repo = None
        self._extra_lines = list(repo.extra_lines) if repo else []
        editing = repo is not None

        self.setObjectName("SettingsDialog")
        self.setWindowTitle(self.t("settings.repo_edit_title" if editing else "settings.repo_add_title"))
        self.setFixedSize(420, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 20)
        layout.setSpacing(8)

        layout.addWidget(QLabel(self.t("settings.repo_name")))
        self.edit_name = QLineEdit(repo.name if editing else "")
        self.edit_name.setObjectName("SearchField")  # reuse the dark input style from style.qss
        layout.addWidget(self.edit_name)

        layout.addWidget(QLabel(self.t("settings.repo_servers")))
        self.edit_servers = QPlainTextEdit("\n".join(repo.servers) if editing else "")
        self.edit_servers.setObjectName("SearchField")
        self.edit_servers.setPlaceholderText("https://example.com/$repo/$arch")
        layout.addWidget(self.edit_servers)

        layout.addWidget(QLabel(self.t("settings.repo_siglevel")))
        self.combo_siglevel = QComboBox(self)
        self.combo_siglevel.setObjectName("CategoryDropdown")
        self.combo_siglevel.setEditable(True)
        self.combo_siglevel.addItems(_SIGLEVEL_PRESETS)
        current_siglevel = repo.siglevel if editing else ""
        if current_siglevel and current_siglevel not in _SIGLEVEL_PRESETS:
            self.combo_siglevel.addItem(current_siglevel)
        self.combo_siglevel.setCurrentText(current_siglevel)
        layout.addWidget(self.combo_siglevel)

        layout.addStretch()

        buttons = QHBoxLayout()
        self.btn_cancel = QPushButton(self.t("ui.cancel"), self)
        self.btn_cancel.setObjectName("DetailBackBtn")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton(self.t("ui.confirm"), self)
        self.btn_save.setObjectName("DetailActionBtn")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)

        buttons.addStretch()
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_save)
        layout.addLayout(buttons)

    def _on_save(self):
        name = self.edit_name.text().strip()
        servers = [s.strip() for s in self.edit_servers.toPlainText().splitlines() if s.strip()]
        siglevel = self.combo_siglevel.currentText().strip()

        repo = PacmanRepository(name, servers, siglevel, extra_lines=self._extra_lines)
        try:
            repo.validate()
        except RepositoryError as exc:
            QMessageBox.warning(self, self.t("settings.repo_error_title"), str(exc))
            return

        self.result_repo = repo
        self.accept()


class RepositoryManagerDialog(QDialog):
    """Lists custom repositories and drives add/edit/remove through a RepositoryStore."""

    def __init__(self, parent, t, store: RepositoryStore):
        super().__init__(parent)
        self.t = t
        self.store = store

        self.setObjectName("SettingsDialog")
        self.setWindowTitle("⚙ " + self.t("settings.repo_manager_title"))
        self.setFixedSize(420, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 20)
        layout.setSpacing(10)

        hint = QLabel(self.t("settings.repo_manager_hint"), self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_repos = QListWidget(self)
        self.list_repos.setObjectName("CategoryList")
        layout.addWidget(self.list_repos)

        row_buttons = QHBoxLayout()
        self.btn_add = QPushButton(self.t("settings.repo_add"), self)
        self.btn_add.setObjectName("DetailActionBtn")
        self.btn_edit = QPushButton(self.t("settings.repo_edit"), self)
        self.btn_edit.setObjectName("DetailBackBtn")
        self.btn_remove = QPushButton(self.t("settings.repo_remove"), self)
        self.btn_remove.setObjectName("DetailBackBtn")
        for btn in (self.btn_add, self.btn_edit, self.btn_remove):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_remove.clicked.connect(self._on_remove)
        row_buttons.addWidget(self.btn_add)
        row_buttons.addWidget(self.btn_edit)
        row_buttons.addWidget(self.btn_remove)
        layout.addLayout(row_buttons)

        close_row = QHBoxLayout()
        self.btn_close = QPushButton(self.t("ui.detail_back"), self)
        self.btn_close.setObjectName("DetailBackBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        close_row.addStretch()
        close_row.addWidget(self.btn_close)
        layout.addLayout(close_row)

        self._reload()

    def _reload(self):
        self.list_repos.clear()
        try:
            repos = self.store.list_repositories()
        except RepositoryError as exc:
            QMessageBox.warning(self, self.t("settings.repo_error_title"), str(exc))
            return
        for repo in repos:
            preview = repo.servers[0] if repo.servers else ""
            item = QListWidgetItem(f"{repo.name}  —  {preview}")
            item.setData(Qt.ItemDataRole.UserRole, repo.name)
            self.list_repos.addItem(item)

    def _selected_name(self):
        item = self.list_repos.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_add(self):
        dlg = RepositoryEditDialog(self, self.t)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_repo:
            self._run_store_action(lambda: self.store.add_repository(dlg.result_repo))

    def _on_edit(self):
        name = self._selected_name()
        if not name:
            return
        current = next((r for r in self.store.list_repositories() if r.name == name), None)
        if current is None:
            return
        dlg = RepositoryEditDialog(self, self.t, repo=current)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_repo:
            self._run_store_action(lambda: self.store.update_repository(name, dlg.result_repo))

    def _on_remove(self):
        name = self._selected_name()
        if not name:
            return
        confirm = QMessageBox.question(
            self, self.t("settings.repo_remove"),
            self.t("settings.repo_remove_confirm").format(name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._run_store_action(lambda: self.store.remove_repository(name))

    def _run_store_action(self, action):
        try:
            action()
        except RepositoryError as exc:
            QMessageBox.warning(self, self.t("settings.repo_error_title"), str(exc))
        finally:
            self._reload()
