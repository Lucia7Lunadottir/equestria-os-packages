import sys, os, threading, json, shlex
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, pyqtSignal
from backend import (SnapshotData, detect_backend,
                     TimeshiftBackend, ResticBackend, BtrfsBackend,
                     RESTIC_REPO)
from ui_pkg import Ui_SavePoint, SnapshotRow, SettingsDialog, ProgressDialog
from screenshot import init_screenshots, take_screenshot, find_screenshot
from hooks import check_hooks_installed, build_hook_apply_script
from utils import launch_terminal

SUPPORTED_LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
CONFIG_DIR      = os.path.expanduser("~/.config/equestria-save-point")
CONFIG_FILE     = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_KEEP_LAST = 10


class main_app(QMainWindow, Ui_SavePoint):
    load_finished   = pyqtSignal(list, str)
    size_fetched    = pyqtSignal(str)
    snap_size_ready = pyqtSignal(str, str)  # (snapshot_id, size_str)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.selected_snapshot = None
        self.all_snapshots     = []
        self._modal_mode       = "confirm"
        self._status_key       = ""
        self._status_args      = ()
        self._status_suffix    = ""

        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.title_label.setFont(QFont(families[0], 28, QFont.Weight.Bold))
                self.modal_title.setFont(QFont(families[0], 20, QFont.Weight.Bold))

        q_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(q_path):
            # {{BASE_PATH}} lets QSS reference bundled icon files by absolute path
            qss = open(q_path).read().replace(
                "{{BASE_PATH}}", self.base_path.replace("\\", "/"))
            self.setStyleSheet(qss)

        icon_path = os.path.join(self.base_path, "equestria-os-save-point.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        QApplication.setDesktopFileName("equestria-os-save-point")
        init_screenshots()

        self.langs = self._load_locales()
        self.current_lang = "en"
        for _var in ("LANGUAGE", "LANG", "LC_ALL", "LC_MESSAGES"):
            _val = (os.getenv(_var) or "")[:2]
            if _val in self.langs:
                self.current_lang = _val
                break

        # Config
        cfg = self._load_config()
        self.spin_keep_last.setValue(cfg.get("keep_last", DEFAULT_KEEP_LAST))
        self._repo_path = cfg.get("repo_path", RESTIC_REPO)

        # Backend
        backend_type = detect_backend()
        if backend_type == "btrfs":
            self.backend = BtrfsBackend()
        elif backend_type == "restic":
            self.backend = ResticBackend(repo=self._repo_path)
        elif backend_type == "timeshift":
            self.backend = TimeshiftBackend()
        else:
            self.backend = None

        self._snap_rows: dict[str, SnapshotRow] = {}
        self.load_finished.connect(self.on_load_finished)
        self.size_fetched.connect(self.on_size_fetched)
        self.snap_size_ready.connect(self.on_snap_size_ready)
        self.setup_logic()
        self.apply_localization()
        self.load_snapshots()

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_config(self, repo_path=None):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {
            "keep_last": self.spin_keep_last.value(),
            "repo_path": repo_path or getattr(self, "_repo_path", RESTIC_REPO),
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ── Locale ────────────────────────────────────────────────────────────────

    def _load_locales(self):
        langs = {}
        locales_dir = os.path.join(self.base_path, "locales")
        for code in SUPPORTED_LANGS:
            path = os.path.join(locales_dir, f"{code}.json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    langs[code] = json.load(f)
        return langs

    def t(self, key):
        return (self.langs.get(self.current_lang, {}).get(key)
                or self.langs.get("en", {}).get(key, key))

    # ── Setup ─────────────────────────────────────────────────────────────────

    def setup_logic(self):
        self.btn_create.clicked.connect(self.create_snapshot)
        self.btn_restore.clicked.connect(self.restore_snapshot)
        self.btn_delete.clicked.connect(self.delete_snapshot)
        self.btn_refresh.clicked.connect(self.load_snapshots)
        self.btn_confirm_cancel.clicked.connect(self.modal_overlay.hide)
        self.btn_confirm_ok.clicked.connect(self._on_modal_ok)
        self.btn_settings.clicked.connect(self.open_settings_dialog)

        self.spin_keep_last.valueChanged.connect(lambda _: self._save_config())

        for code in SUPPORTED_LANGS:
            btn = QPushButton(code.upper())
            btn.setObjectName("LangBtn")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda chk, c=code: self.change_lang(c))
            self.lang_layout.addWidget(btn)

    def resizeEvent(self, event):
        self.modal_overlay.resize(event.size())
        super().resizeEvent(event)

    def change_lang(self, lang):
        self.current_lang = lang
        for i in range(self.lang_layout.count()):
            btn = self.lang_layout.itemAt(i).widget()
            if btn and isinstance(btn, QPushButton):
                btn.setProperty("active", "true" if btn.text().lower() == lang else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self.apply_localization()

    def apply_localization(self):
        title = self.t("ui.title")
        self.title_label.setText(title)
        self.setWindowTitle(title)
        self.btn_create.setText(self.t("btn.create"))
        self.btn_restore.setText(self.t("btn.restore"))
        self.btn_refresh.setText(self.t("btn.refresh"))
        self.btn_confirm_cancel.setText(self.t("btn.cancel"))
        self.lbl_keep_last.setText(self.t("ui.keep_last"))
        self.lbl_snapshots_unit.setText(self.t("ui.snapshots_unit"))
        self.btn_delete.setText(self.t("btn.delete"))
        self._rerender_rows()

        if self.modal_overlay.isVisible() and self._modal_mode == "setup":
            self.modal_title.setText(self.t("setup.title"))
            self.modal_text.setText(self.t("setup.desc"))
            self.btn_confirm_ok.setText(self.t("setup.btn"))
            self.set_status_key("setup.status")
        else:
            self.modal_title.setText(self.t("modal.title"))
            self._refresh_status()

    # ── Modal ─────────────────────────────────────────────────────────────────

    def _on_modal_ok(self):
        if self._modal_mode == "setup":
            self.modal_overlay.hide()
            self._run_restic_init()
        else:
            self.execute_restore()

    def _show_modal(self, mode, title, text, ok_label, show_cancel=True):
        self._modal_mode = mode
        self.modal_title.setText(title)
        self.modal_text.setText(text)
        self.btn_confirm_ok.setText(ok_label)
        self.btn_confirm_cancel.setVisible(show_cancel)
        self.modal_overlay.show()
        self.modal_overlay.raise_()

    # ── Snapshot loading ───────────────────────────────────────────────────────

    def load_snapshots(self):
        self.set_status_key("status.loading")
        self.lbl_repo_size.setText("")
        self.btn_refresh.setEnabled(False)
        self.btn_create.setEnabled(False)

        def _fetch():
            if self.backend is None:
                self.load_finished.emit([], "__NO_BACKEND__")
                return
            if isinstance(self.backend, ResticBackend) and not self.backend.is_initialized():
                self.load_finished.emit([], "__RESTIC_SETUP__")
                return
            snapshots, error = self.backend.list_snapshots()
            self.load_finished.emit(snapshots, error)

        threading.Thread(target=_fetch, daemon=True).start()

    def on_load_finished(self, snapshots, error):
        self.btn_refresh.setEnabled(True)
        self.btn_create.setEnabled(True)
        self.selected_snapshot = None
        self.all_snapshots     = snapshots
        self.btn_restore.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self._snap_rows = {}

        if error == "__RESTIC_SETUP__":
            self._show_modal(
                "setup",
                self.t("setup.title"),
                self.t("setup.desc"),
                self.t("setup.btn"),
                show_cancel=False,
            )
            self.set_status_key("setup.status")
            return

        if error == "__NO_BACKEND__":
            self.set_status_key("err.no_backend")
            return

        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if error and not snapshots:
            self.set_status_key(error)
            return

        for snap in snapshots:
            tag_info   = self._tag_info(snap.tags)
            screenshot = find_screenshot(snap)
            row = SnapshotRow(snap, tag_info, screenshot, self.on_select)
            self._snap_rows[snap.snapshot_id] = row
            self.list_layout.addWidget(row)

        if snapshots and self.backend and hasattr(self.backend, "get_snapshot_size"):
            snaps_copy = list(snapshots)
            backend    = self.backend
            signal     = self.snap_size_ready
            def _load_sizes():
                for s in snaps_copy:
                    try:
                        sz = backend.get_snapshot_size(s.snapshot_id)
                        if sz:
                            signal.emit(s.snapshot_id, sz)
                    except Exception:
                        pass
            threading.Thread(target=_load_sizes, daemon=True).start()

        if not snapshots:
            self.set_status_key("status.empty")
        else:
            label = self.backend.fstype_label() if hasattr(self.backend, "fstype_label") else ""
            suffix = f"  ·  {label}" if label else ""
            self.set_status_key("status.loaded", len(snapshots), suffix=suffix)

        # Fetch repo size in background (non-blocking)
        self._fetch_repo_size()

    def _fetch_repo_size(self):
        def _run():
            size = self.backend.get_repo_size() if self.backend else ""
            self.size_fetched.emit(size)
        threading.Thread(target=_run, daemon=True).start()

    def on_size_fetched(self, size: str):
        if size:
            self.lbl_repo_size.setText(self.t("ui.repo_size").format(size))

    def _tag_info(self, tag_code: str) -> tuple:
        mapping = {
            "D": ("tag.daily",    "#3a6fcc"),
            "W": ("tag.weekly",   "#7a42c0"),
            "M": ("tag.monthly",  "#b89020"),
            "B": ("tag.boot",     "#c06030"),
            "O": ("tag.ondemand", "#2e8c50"),
            "R": ("tag.restic",   "#1e7a8a"),
            "S": ("tag.snapshot", "#1a6a5a"),
        }
        key, color = mapping.get(tag_code.upper(), (None, "#505070"))
        return (self.t(key) if key else tag_code), color

    # ── Selection ─────────────────────────────────────────────────────────────

    def _rerender_rows(self):
        if not self.all_snapshots:
            return
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._snap_rows = {}
        self.selected_snapshot = None
        self.btn_restore.setEnabled(False)
        self.btn_delete.setEnabled(False)
        for snap in self.all_snapshots:
            tag_info   = self._tag_info(snap.tags)
            screenshot = find_screenshot(snap)
            row = SnapshotRow(snap, tag_info, screenshot, self.on_select)
            self._snap_rows[snap.snapshot_id] = row
            self.list_layout.addWidget(row)

    def on_snap_size_ready(self, snap_id: str, size_str: str):
        row = self._snap_rows.get(snap_id)
        if row:
            row.set_size(size_str)

    def on_select(self, snap, row_widget):
        self.selected_snapshot = snap
        self.btn_restore.setEnabled(True)
        self.btn_delete.setEnabled(True)
        for i in range(self.list_layout.count()):
            w = self.list_layout.itemAt(i).widget()
            if isinstance(w, SnapshotRow):
                w.set_selected(w is row_widget)

    def set_status_key(self, key: str, *args, suffix: str = ""):
        self._status_key    = key
        self._status_args   = args
        self._status_suffix = suffix
        self._refresh_status()

    def _refresh_status(self):
        if not self._status_key:
            return
        text = self.t(self._status_key)
        if self._status_args:
            text = text.format(*self._status_args)
        self.status_label.setText(text + self._status_suffix)

    def set_status(self, text):
        self.status_label.setText(text)

    # ── Settings / hooks ──────────────────────────────────────────────────────

    def open_settings_dialog(self):
        from PyQt6.QtWidgets import QMessageBox
        hook_pacman, hook_flatpak = check_hooks_installed()
        is_btrfs = isinstance(self.backend, BtrfsBackend)
        dlg = SettingsDialog(self, self.t, hook_pacman, hook_flatpak,
                             self._repo_path,
                             show_repo_section=not is_btrfs)
        if not dlg.exec():
            return

        new_repo = dlg.edit_repo_path.text().strip() or self._repo_path

        # User clicked "Delete repository"
        if dlg._delete_repo:
            old = shlex.quote(new_repo)
            cmd = (f"pkexec rm -rf {old}"
                   "\necho\necho '--- Done. Press Enter to close ---'\nread")
            launch_terminal(cmd)
            return

        # If path changed and old repo still exists, offer to move it
        move_old = None
        if new_repo != self._repo_path and os.path.isdir(self._repo_path):
            box = QMessageBox(self)
            box.setWindowTitle(self.t("settings.repo_path"))
            box.setText(self.t("settings.move_confirm").format(
                self._repo_path, new_repo))
            btn_move = box.addButton(
                self.t("settings.btn_move"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(
                self.t("settings.btn_keep"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == btn_move:
                move_old = self._repo_path

        self._apply_hook_settings(
            dlg.check_pacman.isChecked(),
            dlg.check_flatpak.isChecked(),
            new_repo,
            move_old_repo=move_old,
        )

    def _apply_hook_settings(self, hook_pacman: bool, hook_flatpak: bool,
                              repo_path: str, move_old_repo: str = None):
        keep = self.spin_keep_last.value()
        script = build_hook_apply_script(
            hook_pacman, hook_flatpak, repo_path, move_old_repo, keep, RESTIC_REPO
        )

        # Update in-process state & user config
        self._repo_path = repo_path
        if isinstance(self.backend, ResticBackend):
            self.backend = ResticBackend(repo=repo_path)
        self._save_config(repo_path=repo_path)

        cmd = (f"pkexec bash -c {shlex.quote(script)}"
               "\necho\necho '--- Done. Press Enter to close ---'\nread")
        launch_terminal(cmd)

    # ── Actions ───────────────────────────────────────────────────────────────

    def create_snapshot(self):
        self.btn_create.setEnabled(False)
        keep_last     = self.spin_keep_last.value()
        current_snaps = list(self.all_snapshots)

        take_screenshot()

        create = self.backend.create_cmd()
        prune  = self.backend.build_prune_cmd(current_snaps, keep_last)
        pruning_label = self.t("ui.pruning")
        cmd = create
        if prune:
            cmd += f" && echo && echo '=== {pruning_label} ===' && {prune}"

        dlg = ProgressDialog(self, self.t("progress.creating"), self.t)
        dlg.run("pkexec", ["bash", "-c", cmd])
        dlg.exec()
        self.btn_create.setEnabled(True)
        self.load_snapshots()

    def restore_snapshot(self):
        if not self.selected_snapshot:
            return
        self._show_modal(
            "confirm",
            self.t("modal.title"),
            self.t("modal.confirm").format(self.selected_snapshot.date_str),
            self.t("btn.restore"),
            show_cancel=True,
        )

    def execute_restore(self):
        self.modal_overlay.hide()
        if not self.selected_snapshot:
            return
        cmd = self.backend.restore_cmd(self.selected_snapshot.snapshot_id)
        dlg = ProgressDialog(self, self.t("progress.restoring"), self.t)
        dlg.run("pkexec", ["bash", "-c", cmd])
        dlg.exec()
        self.load_snapshots()

    def delete_snapshot(self):
        if not self.selected_snapshot:
            return
        from PyQt6.QtWidgets import QMessageBox
        snap = self.selected_snapshot
        reply = QMessageBox.question(
            self,
            self.t("btn.delete"),
            self.t("modal.delete_confirm").format(snap.date_str),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cmd = self.backend.delete_cmd(snap.snapshot_id)
        dlg = ProgressDialog(self, self.t("btn.delete"), self.t)
        dlg.run("pkexec", ["bash", "-c", cmd])
        dlg.exec()
        self.load_snapshots()

    def _run_restic_init(self):
        inner = self.backend.init_cmd()
        dlg = ProgressDialog(self, self.t("setup.title"), self.t)
        dlg.run("pkexec", ["bash", "-c", inner])
        dlg.exec()
        self.load_snapshots()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = main_app()
    win.show()
    sys.exit(app.exec())
