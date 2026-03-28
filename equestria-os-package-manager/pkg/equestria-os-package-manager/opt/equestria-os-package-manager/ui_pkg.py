from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QComboBox, QScrollArea, QFrame)
from PyQt6.QtCore import Qt

class PackageRow(QFrame):
    def __init__(self, pkg_data, delete_text, on_delete_callback):
        super().__init__()
        self.pkg_data = pkg_data
        self.setObjectName("PackageRow")
        self.setFixedHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)

        info_layout = QVBoxLayout()
        self.lbl_name = QLabel(pkg_data.name)
        self.lbl_name.setStyleSheet("color: white; font-weight: bold; font-size: 15px; background: transparent;")

        self.lbl_info = QLabel(f"{pkg_data.category} ({pkg_data.source})")
        self.lbl_info.setStyleSheet("color: rgb(180, 170, 200); font-size: 12px; background: transparent;")

        info_layout.addWidget(self.lbl_name)
        info_layout.addWidget(self.lbl_info)

        self.btn_delete = QPushButton(delete_text)
        self.btn_delete.setObjectName("ListDeleteBtn") # ФИКС: Жесткая привязка по ID
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setFixedWidth(110)
        self.btn_delete.clicked.connect(lambda checked=False, p=self.pkg_data: on_delete_callback(p))

        layout.addLayout(info_layout)
        layout.addStretch()
        layout.addWidget(self.btn_delete)

class Ui_PackageManager:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1000, 750)

        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        self.main_layout = QVBoxLayout(self.root)
        self.main_layout.setContentsMargins(25, 25, 25, 25)

        self.title_label = QLabel("✨ Equestria OS Packages")
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
        self.search_field.setPlaceholderText("Search...")

        self.category_dropdown = QComboBox()
        self.category_dropdown.setObjectName("CategoryDropdown")
        self.category_dropdown.setFixedWidth(200)

        filter_box.addWidget(self.search_field, 1)
        filter_box.addWidget(self.category_dropdown)
        self.main_layout.addLayout(filter_box)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("PackageList")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSpacing(2)
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)

        # ФИКС: QFrame позволяет задать фон (черное перекрытие) через QSS!
        self.modal_overlay = QFrame(self.root)
        self.modal_overlay.setObjectName("ModalOverlay")
        self.modal_overlay.hide()

        v_modal = QVBoxLayout(self.modal_overlay)
        self.modal_box = QFrame()
        self.modal_box.setObjectName("ModalBox")
        self.modal_box.setFixedSize(420, 240)

        m_layout = QVBoxLayout(self.modal_box)
        m_layout.setContentsMargins(30, 30, 30, 30)

        self.modal_title = QLabel("✨ Confirmation")
        self.modal_title.setStyleSheet("color: white; font-size: 22px; font-weight: bold; background: transparent;")
        self.modal_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.modal_text = QLabel("Confirm?")
        self.modal_text.setStyleSheet("color: rgb(210, 200, 230); font-size: 15px; background: transparent;")
        self.modal_text.setWordWrap(True)
        self.modal_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)

        self.btn_confirm_cancel = QPushButton("Cancel")
        self.btn_confirm_cancel.setObjectName("ModalCancelBtn") # ФИКС: ID
        self.btn_confirm_cancel.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_confirm_delete = QPushButton("Delete")
        self.btn_confirm_delete.setObjectName("ModalDeleteBtn") # ФИКС: ID
        self.btn_confirm_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_delete.setMinimumHeight(45)

        btn_row.addWidget(self.btn_confirm_cancel)
        btn_row.addWidget(self.btn_confirm_delete)

        m_layout.addWidget(self.modal_title)
        m_layout.addStretch()
        m_layout.addWidget(self.modal_text)
        m_layout.addStretch()
        m_layout.addLayout(btn_row)
        v_modal.addWidget(self.modal_box, 0, Qt.AlignmentFlag.AlignCenter)
