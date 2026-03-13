from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QStackedWidget, QFileDialog, QTextEdit,
    QComboBox, QCheckBox, QFrame, QLayout
)
from PyQt6.QtCore import Qt
from app_config import AppConfig
from steamcmd_wrapper import SteamCmdWrapper

STYLESHEET = """
QMainWindow { background-color: #1a1a2e; color: #e0e0e0; }
QWidget { font-size: 13px; }
#Sidebar { background-color: #16213e; border-right: 1px solid #0f3460; }
#Header { background-color: #16213e; border-bottom: 1px solid #0f3460; }
QLabel#Title { font-size: 20px; color: #00d4ff; font-weight: bold; }
QLabel#Status { font-size: 12px; color: #888888; }
QLabel#PanelTitle { font-size: 18px; color: #00d4ff; font-weight: bold; margin-bottom: 15px; }

QPushButton.NavBtn { background: transparent; color: #aaaaaa; text-align: left; padding: 10px 14px; border: none; border-radius: 6px; }
QPushButton.NavBtn:hover { background-color: #1c3059; color: white; }
QPushButton.NavBtn[active="true"] { background-color: #0f3460; color: #00d4ff; }

QLineEdit, QComboBox { background-color: #0d1b2a; border: 1px solid #2a4060; border-radius: 4px; color: #e0e0e0; padding: 6px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #00d4ff; }

QPushButton.Primary { background-color: #0f3460; border: 1px solid #00d4ff; border-radius: 6px; color: #00d4ff; padding: 8px 24px; font-weight: bold; }
QPushButton.Primary:hover { background-color: #00d4ff; color: #1a1a2e; }
QPushButton.Primary:disabled { opacity: 0.4; border-color: #555; color: #555; }

QPushButton.Secondary { background-color: transparent; border: 1px solid #445566; border-radius: 6px; color: #aaaaaa; padding: 8px 16px; }
QPushButton.Secondary:hover { border-color: #00d4ff; color: white; }

QTextEdit#LogArea { background-color: #0d1117; color: #88cc88; border: none; border-top: 1px solid #0f3460; font-family: monospace; }
QLabel#LogTitle { color: #445566; font-weight: bold; font-size: 12px; letter-spacing: 1px; padding: 4px; }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SteamPipe GUI")
        self.resize(900, 600)
        self.setStyleSheet(STYLESHEET)

        self.config = AppConfig.load()
        self.steam = SteamCmdWrapper()

        if self.config.sdk_folder:
            self.steam.try_set_sdk_folder(self.config.sdk_folder)
        elif self.config.steamcmd_path:
            self.steam.steamcmd_path = self.config.steamcmd_path

        self.steam.log_output.connect(self.append_log)
        self.steam.status_changed.connect(self.update_status)
        self.steam.login_state_changed.connect(self.update_login_ui)

        self.setup_ui()
        self.restore_fields()

        if self.steam.steamcmd_path:
            self.append_log(f"[OK] steamcmd found: {self.steam.steamcmd_path}")
        else:
            self.append_log("[WARN] steamcmd not found. Set SDK folder in Settings.")

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QFrame(); header.setObjectName("Header")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 12, 20, 12)

        title = QLabel("SteamPipe GUI"); title.setObjectName("Title")
        self.lbl_status = QLabel("Not connected"); self.lbl_status.setObjectName("Status")
        h_layout.addWidget(title); h_layout.addStretch(); h_layout.addWidget(self.lbl_status)
        main_layout.addWidget(header)

        # Body Layout
        body_layout = QHBoxLayout()
        main_layout.addLayout(body_layout, 1)

        # Sidebar
        sidebar = QFrame(); sidebar.setObjectName("Sidebar"); sidebar.setFixedWidth(180)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(8, 10, 8, 10)

        self.btn_nav_login = QPushButton("🔐 Login")
        self.btn_nav_build = QPushButton("🔨 Build")
        self.btn_nav_settings = QPushButton("⚙ Settings")

        for btn in [self.btn_nav_login, self.btn_nav_build, self.btn_nav_settings]:
            btn.setProperty("class", "NavBtn")
            side_layout.addWidget(btn)
        side_layout.addStretch()

        body_layout.addWidget(sidebar)

        # Content Area
        content_vlayout = QVBoxLayout()
        body_layout.addLayout(content_vlayout, 1)

        # ИСПРАВЛЕНИЕ: Инициализируем log_area ДО создания панелей
        self.log_area = QTextEdit()
        self.log_area.setObjectName("LogArea")
        self.log_area.setReadOnly(True)
        self.log_area.setFixedHeight(200)

        self.stack = QStackedWidget()
        content_vlayout.addWidget(self.stack, 1)

        # Panels
        self.panel_login = self.create_login_panel()
        self.panel_build = self.create_build_panel()
        self.panel_settings = self.create_settings_panel()

        self.stack.addWidget(self.panel_login)
        self.stack.addWidget(self.panel_build)
        self.stack.addWidget(self.panel_settings)

        self.btn_nav_login.clicked.connect(lambda: self.switch_panel(0, self.btn_nav_login))
        self.btn_nav_build.clicked.connect(lambda: self.switch_panel(1, self.btn_nav_build))
        self.btn_nav_settings.clicked.connect(lambda: self.switch_panel(2, self.btn_nav_settings))

        self.switch_panel(0, self.btn_nav_login)

        # Log Area Container (собираем UI логирования)
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(14, 6, 14, 8)
        log_layout.setSpacing(4)

        lbl_log = QLabel("OUTPUT"); lbl_log.setObjectName("LogTitle")

        log_layout.addWidget(lbl_log)
        log_layout.addWidget(self.log_area) # Используем уже созданный виджет
        content_vlayout.addWidget(log_container)

    # ИСПРАВЛЕНИЕ ТУТ: Умное добавление виджета или слоя
    def _field_row(self, label_text, item, layout):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(160)
        lbl.setStyleSheet("color: #aaaaaa;")
        row.addWidget(lbl)

        if isinstance(item, QWidget):
            row.addWidget(item, 1)
        elif isinstance(item, QLayout):
            row.addLayout(item, 1)

        layout.addLayout(row)

    def create_login_panel(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(24, 24, 24, 24); l.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Steam Login"); title.setObjectName("PanelTitle"); l.addWidget(title)

        self.f_user = QLineEdit()
        self.f_pass = QLineEdit(); self.f_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_guard = QLineEdit()

        self._field_row("Username", self.f_user, l)
        self._field_row("Password", self.f_pass, l)
        self._field_row("Steam Guard (if required)", self.f_guard, l)

        btn_row = QHBoxLayout(); btn_row.setContentsMargins(0, 16, 0, 0)
        self.btn_login = QPushButton("Login"); self.btn_login.setProperty("class", "Primary")
        self.btn_logout = QPushButton("Logout"); self.btn_logout.setProperty("class", "Secondary")
        self.btn_logout.hide()

        self.btn_login.clicked.connect(self.do_login)
        self.btn_logout.clicked.connect(self.steam.logout)

        btn_row.addWidget(self.btn_login); btn_row.addWidget(self.btn_logout); btn_row.addStretch()
        l.addLayout(btn_row)
        return w

    def create_build_panel(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(24, 24, 24, 24); l.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Build & Upload"); title.setObjectName("PanelTitle"); l.addWidget(title)

        self.f_appid = QLineEdit()
        self.f_desc = QLineEdit()
        self.f_content = QLineEdit()
        self.btn_browse_content = QPushButton("Browse..."); self.btn_browse_content.setProperty("class", "Secondary")
        self.btn_browse_content.clicked.connect(lambda: self.browse_folder(self.f_content))

        c_row = QHBoxLayout()
        c_row.addWidget(self.f_content, 1); c_row.addWidget(self.btn_browse_content)

        self.cb_branch = QComboBox()
        self.cb_branch.addItems(["default", "beta", "staging", "preview", "public"])

        self.chk_live = QCheckBox("Set live after upload")
        self.chk_live.setStyleSheet("color: #aaa; margin-top: 10px;")

        self._field_row("App ID", self.f_appid, l)
        self._field_row("Build description", self.f_desc, l)
        self._field_row("Content folder", c_row, l)
        self._field_row("Branch", self.cb_branch, l)

        l.addWidget(self.chk_live)

        self.btn_build = QPushButton("Start build"); self.btn_build.setProperty("class", "Primary")
        self.btn_build.clicked.connect(self.do_build)

        btn_row = QHBoxLayout(); btn_row.setContentsMargins(0, 16, 0, 0)
        btn_row.addWidget(self.btn_build); btn_row.addStretch()
        l.addLayout(btn_row)
        return w

    def create_settings_panel(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(24, 24, 24, 24); l.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Settings"); title.setObjectName("PanelTitle"); l.addWidget(title)

        self.f_sdk = QLineEdit()
        self.btn_browse_sdk = QPushButton("Browse..."); self.btn_browse_sdk.setProperty("class", "Secondary")
        self.btn_browse_sdk.clicked.connect(lambda: self.browse_folder(self.f_sdk))
        row1 = QHBoxLayout(); row1.addWidget(self.f_sdk, 1); row1.addWidget(self.btn_browse_sdk)

        self.f_steamcmd = QLineEdit()
        self.btn_browse_cmd = QPushButton("Browse..."); self.btn_browse_cmd.setProperty("class", "Secondary")
        self.btn_browse_cmd.clicked.connect(lambda: self.browse_file(self.f_steamcmd))
        row2 = QHBoxLayout(); row2.addWidget(self.f_steamcmd, 1); row2.addWidget(self.btn_browse_cmd)

        self.f_loglines = QLineEdit("500")

        self._field_row("Steamworks SDK", row1, l)
        self._field_row("OR steamcmd.sh path", row2, l)
        self._field_row("Max log lines", self.f_loglines, l)

        self.btn_save = QPushButton("Save"); self.btn_save.setProperty("class", "Primary")
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_clear = QPushButton("Clear log"); self.btn_clear.setProperty("class", "Secondary")
        self.btn_clear.clicked.connect(self.log_area.clear)

        btn_row = QHBoxLayout(); btn_row.setContentsMargins(0, 16, 0, 0)
        btn_row.addWidget(self.btn_save); btn_row.addWidget(self.btn_clear); btn_row.addStretch()
        l.addLayout(btn_row)
        return w

    def switch_panel(self, index, active_btn):
        self.stack.setCurrentIndex(index)
        for btn in [self.btn_nav_login, self.btn_nav_build, self.btn_nav_settings]:
            btn.setProperty("active", "true" if btn == active_btn else "false")
            btn.style().unpolish(btn); btn.style().polish(btn)

    def browse_folder(self, target_lineedit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", target_lineedit.text())
        if folder: target_lineedit.setText(folder)

    def browse_file(self, target_lineedit):
        file, _ = QFileDialog.getOpenFileName(self, "Select steamcmd.sh", target_lineedit.text())
        if file: target_lineedit.setText(file)

    def do_login(self):
        user = self.f_user.text().strip()
        if not user:
            self.append_log("[ERROR] Enter a username.")
            return
        self.btn_login.setEnabled(False)
        self.steam.login(user, self.f_pass.text(), self.f_guard.text().strip())
        self.btn_login.setEnabled(True)

    def do_build(self):
        if not self.f_appid.text().strip() or not self.f_content.text().strip():
            self.append_log("[ERROR] App ID and Content folder are required.")
            return
        self.btn_build.setEnabled(False)
        self.steam.build(
            self.f_appid.text().strip(),
            self.f_desc.text().strip(),
            self.f_content.text().strip(),
            self.cb_branch.currentText(),
            self.chk_live.isChecked()
        )
        self.btn_build.setEnabled(True)

    def update_status(self, text):
        self.lbl_status.setText(text)

    def update_login_ui(self, is_logged_in):
        self.btn_login.setVisible(not is_logged_in)
        self.btn_logout.setVisible(is_logged_in)
        self.f_pass.clear()
        self.f_guard.clear()

    def append_log(self, text):
        self.log_area.append(text)
        try:
            limit = int(self.f_loglines.text())
        except ValueError:
            limit = 500
        doc = self.log_area.document()
        if doc.blockCount() > limit:
            cursor = self.log_area.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor, doc.blockCount() - limit)
            cursor.removeSelectedText()

        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def restore_fields(self):
        self.f_user.setText(self.config.last_username)
        self.f_appid.setText(self.config.last_appid)
        self.f_content.setText(self.config.default_content_path)
        self.cb_branch.setCurrentText(self.config.last_branch)
        self.chk_live.setChecked(self.config.set_live_after_upload)
        self.f_sdk.setText(self.config.sdk_folder)
        self.f_steamcmd.setText(self.config.steamcmd_path)
        self.f_loglines.setText(str(self.config.log_max_lines))

    def save_settings(self):
        self.config.sdk_folder = self.f_sdk.text().strip()
        self.config.steamcmd_path = self.f_steamcmd.text().strip()
        try:
            self.config.log_max_lines = int(self.f_loglines.text())
        except ValueError:
            pass

        if self.config.sdk_folder:
            self.steam.try_set_sdk_folder(self.config.sdk_folder)
        elif self.config.steamcmd_path:
            self.steam.steamcmd_path = self.config.steamcmd_path

        self.config.save()
        self.append_log("[OK] Settings saved.")

    def closeEvent(self, event):
        self.config.last_username = self.f_user.text()
        self.config.last_appid = self.f_appid.text()
        self.config.default_content_path = self.f_content.text()
        self.config.last_branch = self.cb_branch.currentText()
        self.config.set_live_after_upload = self.chk_live.isChecked()
        self.config.save()
        event.accept()
