from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QComboBox, QScrollArea, QFrame)
from PyQt6.QtCore import Qt


class ServiceRow(QFrame):
    def __init__(self, svc_data, labels, on_start_stop, on_enable_disable):
        super().__init__()
        self.svc_data = svc_data
        self.on_start_stop = on_start_stop
        self.on_enable_disable = on_enable_disable
        self.setObjectName("ServiceRow")
        self.setFixedHeight(84)
        self._build_ui()
        self.update_labels(labels)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        self.dot = QLabel("●")
        self.dot.setFixedWidth(18)
        self.dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.dot)

        info = QVBoxLayout()
        info.setSpacing(3)

        self.lbl_display = QLabel()
        self.lbl_display.setObjectName("SvcDisplayName")

        self.lbl_tech = QLabel()
        self.lbl_tech.setObjectName("SvcTechName")

        info.addWidget(self.lbl_display)
        info.addWidget(self.lbl_tech)
        layout.addLayout(info, 1)

        badge_col = QVBoxLayout()
        badge_col.setSpacing(5)

        self.badge_active = QLabel()
        self.badge_active.setObjectName("Badge")
        self.badge_active.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_active.setFixedWidth(95)

        self.badge_file = QLabel()
        self.badge_file.setObjectName("Badge")
        self.badge_file.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_file.setFixedWidth(110)

        badge_col.addWidget(self.badge_active)
        badge_col.addWidget(self.badge_file)
        layout.addLayout(badge_col)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(5)

        self.btn_active = QPushButton()
        self.btn_active.setObjectName("BtnAction")
        self.btn_active.setFixedWidth(115)
        self.btn_active.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_active.clicked.connect(lambda: self.on_start_stop(self.svc_data))

        self.btn_file = QPushButton()
        self.btn_file.setObjectName("BtnAction")
        self.btn_file.setFixedWidth(145)
        self.btn_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_file.clicked.connect(lambda: self.on_enable_disable(self.svc_data))

        btn_col.addWidget(self.btn_active)
        btn_col.addWidget(self.btn_file)
        layout.addLayout(btn_col)

    def _set_badge(self, label, state, text):
        label.setText(text)
        label.setProperty("badgeState", state)
        label.style().unpolish(label)
        label.style().polish(label)

    def _set_btn(self, btn, state, text, enabled=True):
        btn.setText(text)
        btn.setEnabled(enabled)
        btn.setProperty("btnAction", state)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def update_labels(self, labels):
        svc = self.svc_data

        self.lbl_display.setText(svc.display_name)
        self.lbl_tech.setText(svc.name)

        # Dot state
        if svc.active_state == "failed":
            dot_state = "failed"
        elif svc.active_state == "active":
            dot_state = "active"
        else:
            dot_state = "inactive"
        self.dot.setProperty("dotState", dot_state)
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)

        # Active badge + tooltip
        if svc.active_state == "active":
            self._set_badge(self.badge_active, "running", labels["running"])
            self.badge_active.setToolTip(labels.get("tip.running", ""))
        elif svc.active_state == "failed":
            self._set_badge(self.badge_active, "failed", labels["failed"])
            self.badge_active.setToolTip(labels.get("tip.failed", ""))
        elif svc.active_state in ("activating", "deactivating"):
            self._set_badge(self.badge_active, "activating", labels["activating"])
            self.badge_active.setToolTip("")
        else:
            self._set_badge(self.badge_active, "stopped", labels["stopped"])
            self.badge_active.setToolTip(labels.get("tip.stopped", ""))

        # File state badge + tooltip
        if svc.unit_file_state in ("enabled", "enabled-runtime"):
            self._set_badge(self.badge_file, "enabled", labels["enabled"])
            self.badge_file.setToolTip(labels.get("tip.autostart_on", ""))
        elif svc.unit_file_state == "masked":
            self._set_badge(self.badge_file, "masked", labels["masked"])
            self.badge_file.setToolTip(labels.get("tip.masked", ""))
        elif svc.unit_file_state == "static":
            self._set_badge(self.badge_file, "static", labels["static"])
            self.badge_file.setToolTip(labels.get("tip.static", ""))
        elif svc.unit_file_state == "generated":
            self._set_badge(self.badge_file, "static", labels["generated"])
            self.badge_file.setToolTip(labels.get("tip.static", ""))
        else:
            self._set_badge(self.badge_file, "disabled", labels["disabled"])
            self.badge_file.setToolTip(labels.get("tip.autostart_off", ""))

        # Start/Stop button + tooltip
        if svc.active_state == "active":
            self._set_btn(self.btn_active, "stop", labels["stop"])
            self.btn_active.setToolTip(labels.get("tip.stop_btn", ""))
        else:
            self._set_btn(self.btn_active, "start", labels["start"])
            self.btn_active.setToolTip(labels.get("tip.start_btn", ""))

        # Enable/Disable button + tooltip
        if svc.unit_file_state in ("static", "masked", "generated", "indirect"):
            self._set_btn(self.btn_file, "na", labels["n_a"], enabled=False)
            self.btn_file.setToolTip(labels.get("tip.static", ""))
        elif svc.unit_file_state in ("enabled", "enabled-runtime"):
            self._set_btn(self.btn_file, "disable", labels["disable"])
            self.btn_file.setToolTip(labels.get("tip.disable_btn", ""))
        else:
            self._set_btn(self.btn_file, "enable", labels["enable"])
            self.btn_file.setToolTip(labels.get("tip.enable_btn", ""))

    def refresh(self, labels):
        self.update_labels(labels)


class Ui_ServicesManager:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1060, 780)

        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        self.main_layout = QVBoxLayout(self.root)
        self.main_layout.setContentsMargins(25, 25, 25, 25)
        self.main_layout.setSpacing(10)

        self.title_label = QLabel("Equestria OS Services")
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.lang_layout = QHBoxLayout()
        self.lang_layout.setSpacing(5)
        self.lang_layout.addStretch()
        self.main_layout.addLayout(self.lang_layout)

        filter_box = QHBoxLayout()
        self.search_field = QLineEdit()
        self.search_field.setObjectName("SearchField")
        self.search_field.setPlaceholderText("Search services...")

        self.category_dropdown = QComboBox()
        self.category_dropdown.setObjectName("CategoryDropdown")
        self.category_dropdown.setFixedWidth(190)

        filter_box.addWidget(self.search_field, 1)
        filter_box.addWidget(self.category_dropdown)
        self.main_layout.addLayout(filter_box)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("ServiceList")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSpacing(1)
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)

        # Modal overlay
        self.modal_overlay = QFrame(self.root)
        self.modal_overlay.setObjectName("ModalOverlay")
        self.modal_overlay.hide()

        v_modal = QVBoxLayout(self.modal_overlay)

        self.modal_box = QFrame()
        self.modal_box.setObjectName("ModalBox")
        self.modal_box.setFixedSize(460, 220)

        m_layout = QVBoxLayout(self.modal_box)
        m_layout.setContentsMargins(32, 28, 32, 28)

        self.modal_title = QLabel("Confirmation")
        self.modal_title.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        self.modal_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.modal_text = QLabel("")
        self.modal_text.setStyleSheet("color: rgb(210, 200, 230); font-size: 14px; background: transparent;")
        self.modal_text.setWordWrap(True)
        self.modal_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        self.btn_confirm_cancel = QPushButton("Cancel")
        self.btn_confirm_cancel.setObjectName("ModalCancelBtn")
        self.btn_confirm_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_cancel.setMinimumHeight(40)

        self.btn_confirm_ok = QPushButton("Confirm")
        self.btn_confirm_ok.setObjectName("ModalConfirmBtn")
        self.btn_confirm_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_ok.setMinimumHeight(40)

        btn_row.addWidget(self.btn_confirm_cancel)
        btn_row.addWidget(self.btn_confirm_ok)

        m_layout.addWidget(self.modal_title)
        m_layout.addStretch()
        m_layout.addWidget(self.modal_text)
        m_layout.addStretch()
        m_layout.addLayout(btn_row)

        v_modal.addWidget(self.modal_box, 0, Qt.AlignmentFlag.AlignCenter)
