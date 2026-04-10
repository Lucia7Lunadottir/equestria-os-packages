import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QFrame, QSpinBox,
                             QDialog, QCheckBox, QLineEdit,
                             QFileDialog, QMessageBox,
                             QPlainTextEdit, QProgressBar)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QProcess

THUMB_W = 128
THUMB_H = 72      # 16:9 at 128px wide
ROW_H   = 96


class SnapshotRow(QFrame):
    """
    Layout (96px tall):
    ┌────────────────────────────────────────────────────────────────┐
    │ ┌──────────────┐  2024-01-15 10:30:00    ╔═══════════╗   #0  │
    │ │  screenshot  │  User Point (курсив)    ║ Ручной    ║       │
    │ │  thumbnail   │                         ╚═══════════╝       │
    │ └──────────────┘                                              │
    └────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, snap_data, tag_info: tuple, screenshot_path: str | None,
                 on_select_callback):
        super().__init__()
        self.snap_data = snap_data
        self.setObjectName("SnapshotRow")
        self.setFixedHeight(ROW_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 18, 12)
        root.setSpacing(14)

        # ── Thumbnail ─────────────────────────────────────────────────────────
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setObjectName("SnapThumb")
        self.lbl_thumb.setFixedSize(THUMB_W, THUMB_H)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if screenshot_path and os.path.exists(screenshot_path):
            pix = QPixmap(screenshot_path)
            if not pix.isNull():
                pix = pix.scaled(THUMB_W, THUMB_H,
                                 Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
                if pix.width() > THUMB_W or pix.height() > THUMB_H:
                    x = (pix.width()  - THUMB_W) // 2
                    y = (pix.height() - THUMB_H) // 2
                    pix = pix.copy(x, y, THUMB_W, THUMB_H)
                self.lbl_thumb.setPixmap(pix)
            else:
                self._set_placeholder()
        else:
            self._set_placeholder()

        root.addWidget(self.lbl_thumb)

        # ── Info (date + comment) ─────────────────────────────────────────────
        info = QVBoxLayout()
        info.setSpacing(5)

        lbl_date = QLabel(snap_data.date_str)
        lbl_date.setStyleSheet(
            "color: white; font-weight: bold; font-size: 15px; background: transparent;")

        lbl_comment = QLabel(snap_data.comment if snap_data.comment else "")
        lbl_comment.setStyleSheet(
            "color: rgb(155, 145, 185); font-size: 12px;"
            " font-style: italic; background: transparent;")

        info.addWidget(lbl_date)
        info.addWidget(lbl_comment)
        info.addStretch()

        root.addLayout(info, 1)

        # ── Tag badge + number ────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        tag_label_text, tag_color = tag_info
        if snap_data.tags:
            lbl_tag = QLabel(tag_label_text)
            lbl_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_tag.setStyleSheet(
                f"background-color: {tag_color}; color: white; font-size: 11px;"
                f" font-weight: bold; border-radius: 4px; padding: 2px 8px;")
            right.addWidget(lbl_tag, 0, Qt.AlignmentFlag.AlignRight)

        lbl_num = QLabel(f"#{snap_data.num}")
        lbl_num.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_num.setStyleSheet(
            "color: rgb(120, 110, 160); font-size: 12px; background: transparent;")
        right.addWidget(lbl_num, 0, Qt.AlignmentFlag.AlignRight)

        self.lbl_size = QLabel("")
        self.lbl_size.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_size.setStyleSheet(
            "color: rgb(100, 90, 140); font-size: 11px; background: transparent;")
        right.addWidget(self.lbl_size, 0, Qt.AlignmentFlag.AlignRight)
        right.addStretch()

        root.addLayout(right)

        self.mousePressEvent = lambda e: on_select_callback(snap_data, self)

    def _set_placeholder(self):
        self.lbl_thumb.setText("📷")
        self.lbl_thumb.setStyleSheet(
            "background-color: rgb(35, 32, 52); border-radius: 6px;"
            " color: rgb(80, 70, 100); font-size: 22px; border: 1px solid rgb(55, 50, 75);")

    def set_size(self, size_str: str):
        self.lbl_size.setText(size_str)

    def set_selected(self, selected: bool):
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class SettingsDialog(QDialog):
    """
    Settings dialog — hook configuration.
    Opened via the ⚙ button in the main window.
    """

    def __init__(self, parent, t, hook_pacman: bool, hook_flatpak: bool,
                 repo_path: str = "", title_font: QFont | None = None,
                 show_repo_section: bool = True):
        super().__init__(parent)
        self._t = t
        self._delete_repo = False
        self.setWindowTitle(t("settings.title"))
        self.setMinimumWidth(560)
        self.setObjectName("SettingsDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # Title
        lbl_title = QLabel(t("settings.title"))
        lbl_title.setObjectName("SettingsDialogTitle")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("SettingsSep")
        layout.addWidget(line)

        # ── Repository path ───────────────────────────────────────────────────
        repo_box = QFrame()
        repo_box.setObjectName("HookBox")
        repo_layout = QVBoxLayout(repo_box)
        repo_layout.setContentsMargins(14, 12, 14, 12)
        repo_layout.setSpacing(8)

        lbl_repo = QLabel(t("settings.repo_path"))
        lbl_repo.setObjectName("HookCheck")
        repo_layout.addWidget(lbl_repo)

        path_edit_layout = QHBoxLayout()
        path_edit_layout.setSpacing(8)

        self.edit_repo_path = QLineEdit(repo_path)
        self.edit_repo_path.setObjectName("RepoEdit")
        self.edit_repo_path.setMinimumHeight(32)
        path_edit_layout.addWidget(self.edit_repo_path)

        btn_browse = QPushButton(t("settings.browse"))
        btn_browse.setObjectName("ModalCancelBtn") # Стиль нейтральной кнопки
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setMinimumHeight(32)
        btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._on_browse_repo)
        path_edit_layout.addWidget(btn_browse)

        repo_layout.addLayout(path_edit_layout)

        repo_btn_row = QHBoxLayout()
        repo_btn_row.addStretch()

        btn_delete_repo = QPushButton(t("settings.delete_repo"))
        btn_delete_repo.setObjectName("DeleteRepoBtn")
        btn_delete_repo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete_repo.setFixedHeight(30)
        btn_delete_repo.clicked.connect(self._on_delete_repo)
        repo_btn_row.addWidget(btn_delete_repo)

        repo_layout.addLayout(repo_btn_row)

        lbl_repo_note = QLabel(t("settings.repo_note"))
        lbl_repo_note.setObjectName("HookNote")
        lbl_repo_note.setWordWrap(True)
        repo_layout.addWidget(lbl_repo_note)

        repo_box.setVisible(show_repo_section)
        layout.addWidget(repo_box)

        # ── Pacman hook ───────────────────────────────────────────────────────
        pacman_box = QFrame()
        pacman_box.setObjectName("HookBox")
        p_layout = QVBoxLayout(pacman_box)
        p_layout.setContentsMargins(14, 12, 14, 12)
        p_layout.setSpacing(4)

        self.check_pacman = QCheckBox(t("settings.hook_pacman"))
        self.check_pacman.setObjectName("HookCheck")
        self.check_pacman.setChecked(hook_pacman)

        lbl_pacman_note = QLabel(t("settings.hook_pacman_note"))
        lbl_pacman_note.setObjectName("HookNote")
        lbl_pacman_note.setWordWrap(True)

        p_layout.addWidget(self.check_pacman)
        p_layout.addWidget(lbl_pacman_note)
        layout.addWidget(pacman_box)

        # ── Flatpak hook ──────────────────────────────────────────────────────
        flatpak_box = QFrame()
        flatpak_box.setObjectName("HookBox")
        f_layout = QVBoxLayout(flatpak_box)
        f_layout.setContentsMargins(14, 12, 14, 12)
        f_layout.setSpacing(4)

        self.check_flatpak = QCheckBox(t("settings.hook_flatpak"))
        self.check_flatpak.setObjectName("HookCheck")
        self.check_flatpak.setChecked(hook_flatpak)

        lbl_flatpak_note = QLabel(t("settings.hook_flatpak_note"))
        lbl_flatpak_note.setObjectName("HookNote")
        lbl_flatpak_note.setWordWrap(True)

        f_layout.addWidget(self.check_flatpak)
        f_layout.addWidget(lbl_flatpak_note)
        layout.addWidget(flatpak_box)

        layout.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_cancel = QPushButton(t("btn.cancel"))
        self.btn_cancel.setObjectName("ModalCancelBtn")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setMinimumHeight(38)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_apply = QPushButton(t("settings.apply"))
        self.btn_apply.setObjectName("ModalOkBtn")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.setMinimumHeight(38)
        self.btn_apply.clicked.connect(self.accept)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_apply)
        layout.addLayout(btn_row)

    def _on_browse_repo(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            self._t("settings.repo_path"),
            self.edit_repo_path.text() or os.path.expanduser("~")
        )
        if directory:
            self.edit_repo_path.setText(directory)

    def _on_delete_repo(self):
        path = self.edit_repo_path.text().strip()
        if not path:
            return
        msg = self._t("settings.delete_confirm").format(path)
        reply = QMessageBox.question(
            self,
            self._t("settings.delete_repo"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._delete_repo = True
            self.accept()


class ProgressDialog(QDialog):
    def __init__(self, parent, title: str, t):
        super().__init__(parent)
        self._t = t
        self.setWindowTitle(title)
        self.setMinimumSize(640, 440)
        self.setObjectName("ProgressDialog")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        lbl = QLabel(title)
        lbl.setObjectName("ProgressTitle")
        layout.addWidget(lbl)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setObjectName("ProgressOutput")
        layout.addWidget(self.output, 1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setObjectName("ProgressBar")
        layout.addWidget(self.bar)

        self.btn_close = QPushButton(t("btn.close"))
        self.btn_close.setObjectName("ModalOkBtn")
        self.btn_close.setEnabled(False)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setMinimumHeight(38)
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close, 0, Qt.AlignmentFlag.AlignRight)

        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)

    def run(self, program: str, args: list):
        self._proc.start(program, args)

    def _on_output(self):
        raw = bytes(self._proc.readAllStandardOutput()).decode('utf-8', errors='replace')
        for line in raw.splitlines():
            if line.strip():
                self.output.appendPlainText(line)

    def _on_finished(self, code, _status):
        self.bar.setRange(0, 1)
        self.bar.setValue(1 if code == 0 else 0)
        marker = '✓' if code == 0 else '✗'
        key = 'progress.done' if code == 0 else 'progress.failed'
        self.output.appendPlainText(f"\n{marker} {self._t(key)}")
        self.btn_close.setEnabled(True)

    def closeEvent(self, event):
        if self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
        event.accept()


class Ui_SavePoint:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(920, 660)

        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        self.main_layout = QVBoxLayout(self.root)
        self.main_layout.setContentsMargins(25, 25, 25, 20)
        self.main_layout.setSpacing(12)

        self.title_label = QLabel("✨ Equestria Save Point")
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.lang_layout = QHBoxLayout()
        self.lang_layout.setSpacing(5)
        self.lang_layout.addStretch()
        self.main_layout.addLayout(self.lang_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("SnapshotList")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSpacing(2)
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.status_label)

        # ── Settings row (keep-last + repo size) ──────────────────────────────
        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)

        self.lbl_keep_last = QLabel("Keep last:")
        self.lbl_keep_last.setObjectName("SettingsLabel")

        self.spin_keep_last = QSpinBox()
        self.spin_keep_last.setObjectName("KeepLastSpin")
        self.spin_keep_last.setRange(1, 50)
        self.spin_keep_last.setValue(10)
        self.spin_keep_last.setFixedWidth(62)
        self.spin_keep_last.setFixedHeight(32)

        self.lbl_snapshots_unit = QLabel("snapshots")
        self.lbl_snapshots_unit.setObjectName("SettingsLabel")

        self.lbl_repo_size = QLabel("")
        self.lbl_repo_size.setObjectName("RepoSizeLabel")
        self.lbl_repo_size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        settings_row.addWidget(self.lbl_keep_last)
        settings_row.addWidget(self.spin_keep_last)
        settings_row.addWidget(self.lbl_snapshots_unit)
        settings_row.addStretch()
        settings_row.addWidget(self.lbl_repo_size)
        self.main_layout.addLayout(settings_row)

        # ── Bottom buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setObjectName("RefreshBtn")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setFixedHeight(42)

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("SettingsBtn")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setFixedSize(42, 42)
        self.btn_settings.setToolTip("Settings")

        self.btn_create = QPushButton("+ Create")
        self.btn_create.setObjectName("CreateBtn")
        self.btn_create.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create.setFixedHeight(42)

        self.btn_restore = QPushButton("↩ Restore")
        self.btn_restore.setObjectName("RestoreBtn")
        self.btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore.setFixedHeight(42)
        self.btn_restore.setEnabled(False)

        self.btn_delete = QPushButton("✕ Delete")
        self.btn_delete.setObjectName("DeleteBtn")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setFixedHeight(42)
        self.btn_delete.setEnabled(False)

        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_settings)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_create)
        btn_row.addWidget(self.btn_restore)
        btn_row.addWidget(self.btn_delete)
        self.main_layout.addLayout(btn_row)

        # ── Modal overlay (confirm / first-run setup) ─────────────────────────
        self.modal_overlay = QFrame(self.root)
        self.modal_overlay.setObjectName("ModalOverlay")
        self.modal_overlay.hide()

        v_modal = QVBoxLayout(self.modal_overlay)
        self.modal_box = QFrame()
        self.modal_box.setObjectName("ModalBox")
        self.modal_box.setFixedSize(480, 270)

        m_layout = QVBoxLayout(self.modal_box)
        m_layout.setContentsMargins(30, 25, 30, 25)
        m_layout.setSpacing(10)

        self.modal_title = QLabel("✨ Confirm Restore")
        self.modal_title.setStyleSheet(
            "color: white; font-size: 20px; font-weight: bold; background: transparent;")
        self.modal_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.modal_text = QLabel("")
        self.modal_text.setStyleSheet(
            "color: rgb(210, 200, 230); font-size: 14px; background: transparent;")
        self.modal_text.setWordWrap(True)
        self.modal_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        modal_btn_row = QHBoxLayout()
        modal_btn_row.setSpacing(15)

        self.btn_confirm_cancel = QPushButton("Cancel")
        self.btn_confirm_cancel.setObjectName("ModalCancelBtn")
        self.btn_confirm_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_cancel.setMinimumHeight(40)

        self.btn_confirm_ok = QPushButton("OK")
        self.btn_confirm_ok.setObjectName("ModalOkBtn")
        self.btn_confirm_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_ok.setMinimumHeight(40)

        modal_btn_row.addWidget(self.btn_confirm_cancel)
        modal_btn_row.addWidget(self.btn_confirm_ok)

        m_layout.addWidget(self.modal_title)
        m_layout.addWidget(self.modal_text)
        m_layout.addStretch()
        m_layout.addLayout(modal_btn_row)

        v_modal.addWidget(self.modal_box, 0, Qt.AlignmentFlag.AlignCenter)
