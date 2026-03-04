from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QFrame, QListWidget)
from PyQt6.QtCore import Qt

class AppRow(QFrame):
    def __init__(self, app_data, on_toggle_callback):
        super().__init__()
        self.app_data = app_data
        self.setObjectName("AppRow")
        self.setMinimumHeight(85)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)

        # ФИКС ГАЛОЧКИ: Используем кнопку как чекбокс с текстовой галочкой
        self.checkbox = QPushButton("✔")
        self.checkbox.setObjectName("AppToggle")
        self.checkbox.setCheckable(True)
        self.checkbox.setFixedSize(24, 24)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.toggled.connect(lambda checked: on_toggle_callback(self.app_data, checked))

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.lbl_name = QLabel(app_data.display_name)
        self.lbl_name.setStyleSheet("color: white; font-weight: bold; font-size: 16px; background: transparent;")

        self.lbl_desc = QLabel(app_data.desc_key)
        self.lbl_desc.setStyleSheet("color: rgb(170, 160, 200); font-size: 13px; background: transparent;")
        self.lbl_desc.setWordWrap(True)

        text_layout.addWidget(self.lbl_name)
        text_layout.addWidget(self.lbl_desc)
        text_layout.addStretch()

        self.lbl_status = QLabel("")
        self.lbl_status.hide()

        layout.addWidget(self.checkbox)
        layout.addSpacing(15)
        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addWidget(self.lbl_status)

class Ui_AppStore:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1100, 750)

        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        main_layout = QHBoxLayout(self.root)
        main_layout.setContentsMargins(15, 15, 15, 15)

        self.left_panel = QFrame()
        self.left_panel.setObjectName("LeftPanel")
        self.left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)

        self.categories_lbl = QLabel("Categories")
        self.categories_lbl.setObjectName("CategoryHeader")

        self.lang_container = QWidget()
        lang_main_layout = QVBoxLayout(self.lang_container)
        lang_main_layout.setContentsMargins(0, 0, 0, 0)
        lang_main_layout.setSpacing(4)

        self.lang_layout_top = QHBoxLayout()
        self.lang_layout_bottom = QHBoxLayout()
        self.lang_layout_top.setSpacing(4)
        self.lang_layout_bottom.setSpacing(4)

        lang_main_layout.addLayout(self.lang_layout_top)
        lang_main_layout.addLayout(self.lang_layout_bottom)

        self.category_list = QListWidget()
        self.category_list.setObjectName("CategoryList")
        self.category_list.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_update_all = QPushButton("Update System")
        self.btn_update_all.setObjectName("UpdateAllBtn")
        self.btn_update_all.setCursor(Qt.CursorShape.PointingHandCursor)

        left_layout.addWidget(self.categories_lbl)
        left_layout.addWidget(self.lang_container)
        left_layout.addSpacing(10)
        left_layout.addWidget(self.category_list)
        left_layout.addWidget(self.btn_update_all)

        self.right_panel = QFrame()
        self.right_panel.setObjectName("RightPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("AppScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("AppScrollContent")
        self.app_list_layout = QVBoxLayout(self.scroll_content)
        self.app_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.app_list_layout.setSpacing(0)
        self.scroll_area.setWidget(self.scroll_content)

        self.btn_install = QPushButton("Select Apps to Install")
        self.btn_install.setObjectName("InstallBtn")
        self.btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_install.setEnabled(False)

        right_layout.addWidget(self.scroll_area)
        right_layout.addWidget(self.btn_install)

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.right_panel)

        self.modal_overlay = QFrame(self.root)
        self.modal_overlay.setObjectName("ModalOverlay")
        self.modal_overlay.hide()

        v_modal = QVBoxLayout(self.modal_overlay)
        self.modal_box = QFrame()
        self.modal_box.setObjectName("ModalBox")
        self.modal_box.setFixedSize(400, 200)

        m_layout = QVBoxLayout(self.modal_box)
        m_layout.setContentsMargins(30, 30, 30, 30)

        self.modal_title = QLabel("System Update")
        self.modal_title.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        self.modal_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.modal_text = QLabel("Update all system packages?")
        self.modal_text.setStyleSheet("color: rgb(210, 200, 230); font-size: 14px; background: transparent;")
        self.modal_text.setWordWrap(True)
        self.modal_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_row = QHBoxLayout()
        self.btn_cancel_update = QPushButton("Cancel")
        self.btn_cancel_update.setObjectName("ModalCancelBtn")
        self.btn_cancel_update.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_confirm_update = QPushButton("Update")
        self.btn_confirm_update.setObjectName("ModalConfirmBtn")
        self.btn_confirm_update.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_row.addWidget(self.btn_cancel_update)
        btn_row.addWidget(self.btn_confirm_update)

        m_layout.addWidget(self.modal_title)
        m_layout.addWidget(self.modal_text)
        m_layout.addStretch()
        m_layout.addLayout(btn_row)
        v_modal.addWidget(self.modal_box, 0, Qt.AlignmentFlag.AlignCenter)
