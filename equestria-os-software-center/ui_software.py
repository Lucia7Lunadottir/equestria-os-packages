from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QFrame, QListWidget,
                             QStackedWidget, QLineEdit, QComboBox, QProgressBar,
                             QGridLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

class EssentialAppRow(QFrame):
    def __init__(self, app_data, on_toggle):
        super().__init__()
        self.app_data = app_data
        self.setObjectName("AppRow")
        self.setMinimumHeight(75)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)

        self.checkbox = QPushButton("✔")
        self.checkbox.setObjectName("AppToggle")
        self.checkbox.setCheckable(True)
        self.checkbox.setFixedSize(24, 24)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.toggled.connect(lambda checked: on_toggle(self.app_data, checked))

        text_layout = QVBoxLayout()
        self.lbl_name = QLabel(app_data.display_name)
        self.lbl_name.setStyleSheet("color: white; font-weight: bold; font-size: 16px; background: transparent;")

        # Используем переведенное описание, если оно передано
        desc_text = getattr(app_data, 'display_desc', app_data.desc_key)
        self.lbl_desc = QLabel(desc_text)
        self.lbl_desc.setStyleSheet("color: rgb(170, 160, 200); font-size: 13px; background: transparent;")

        text_layout.addWidget(self.lbl_name)
        text_layout.addWidget(self.lbl_desc)

        layout.addWidget(self.checkbox)
        layout.addLayout(text_layout)
        layout.addStretch()

class StoreAppRow(QFrame):
    def __init__(self, pkg_data, action_text, on_action):
        super().__init__()
        self.pkg_data = pkg_data
        self.setObjectName("PackageRow")
        self.setMinimumHeight(75)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 40)
        icon = QIcon.fromTheme(pkg_data.name, QIcon.fromTheme("application-x-executable"))
        self.icon_label.setPixmap(icon.pixmap(40, 40))
        layout.addWidget(self.icon_label)

        info_layout = QVBoxLayout()
        self.lbl_name = QLabel(f"{pkg_data.name} <span style='color:gray; font-size:12px;'>v{pkg_data.version}</span>")
        self.lbl_name.setStyleSheet("color: white; font-weight: bold; font-size: 15px; background: transparent;")
        self.lbl_desc = QLabel(pkg_data.desc[:80] + "..." if len(pkg_data.desc) > 80 else pkg_data.desc)
        self.lbl_desc.setStyleSheet("color: rgb(180, 170, 200); font-size: 12px; background: transparent;")
        info_layout.addWidget(self.lbl_name)
        info_layout.addWidget(self.lbl_desc)
        layout.addLayout(info_layout, 1)

        self.btn_action = QPushButton(action_text)
        self.btn_action.setObjectName("ListInstallBtn")
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.clicked.connect(lambda: on_action(self.pkg_data))
        layout.addWidget(self.btn_action)

class Ui_SoftwareCenter:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1050, 700)
        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        main_layout = QHBoxLayout(self.root)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- ЛЕВАЯ ПАНЕЛЬ (НАВИГАЦИЯ) ---
        self.left_panel = QFrame()
        self.left_panel.setObjectName("LeftPanel")
        self.left_panel.setFixedWidth(280) # УВЕЛИЧЕНО до 280, чтобы языки не плющило
        left_layout = QVBoxLayout(self.left_panel)

        self.title_label = QLabel("Equestria Software Center")
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.title_label)

        # Контейнер для языков (СЕТКА)
        self.lang_container = QWidget()
        self.lang_layout = QGridLayout(self.lang_container)
        self.lang_layout.setSpacing(4)
        self.lang_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.lang_container)

        # Категории Essentials
        self.cat_header = QLabel("🌟 Essentials")
        self.cat_header.setObjectName("CategoryHeader")
        left_layout.addWidget(self.cat_header)

        self.cat_list = QListWidget()
        self.cat_list.setObjectName("CategoryList")
        self.cat_list.setMinimumHeight(80)
        left_layout.addWidget(self.cat_list, 1)

        # Переход в полный магазин
        self.store_header = QLabel("📦 App Store")
        self.store_header.setObjectName("CategoryHeader")
        left_layout.addWidget(self.store_header)

        self.btn_switch_store = QPushButton("🔍 Search All Apps")
        self.btn_switch_store.setObjectName("NavBtn")
        self.btn_switch_store.setCursor(Qt.CursorShape.PointingHandCursor)
        left_layout.addWidget(self.btn_switch_store)

        left_layout.addStretch()

        self.btn_update_sys = QPushButton("Update System")
        self.btn_update_sys.setObjectName("UpdateAllBtn")
        self.btn_update_sys.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update_sys.setMinimumHeight(45)
        left_layout.addWidget(self.btn_update_sys)

        main_layout.addWidget(self.left_panel)

        # --- ПРАВАЯ ПАНЕЛЬ (QStackedWidget) ---
        self.right_panel = QFrame()
        self.right_panel.setObjectName("RightPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0,0,0,0)

        self.stacked_widget = QStackedWidget()
        right_layout.addWidget(self.stacked_widget)

        # СТРАНИЦА 0: ESSENTIALS
        self.page_essentials = QWidget()
        page0_layout = QVBoxLayout(self.page_essentials)

        self.scroll_essentials = QScrollArea()
        self.scroll_essentials.setWidgetResizable(True)
        self.scroll_essentials.setObjectName("AppScrollArea")
        self.content_essentials = QWidget()
        self.content_essentials.setObjectName("AppScrollContent")
        self.layout_essentials = QVBoxLayout(self.content_essentials)
        self.layout_essentials.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_essentials.setWidget(self.content_essentials)

        self.btn_install_essentials = QPushButton("Install Selected")
        self.btn_install_essentials.setObjectName("InstallSelectedBtn")
        self.btn_install_essentials.setMinimumHeight(45)
        self.btn_install_essentials.setCursor(Qt.CursorShape.PointingHandCursor)

        page0_layout.addWidget(self.scroll_essentials)
        page0_layout.addWidget(self.btn_install_essentials)
        self.stacked_widget.addWidget(self.page_essentials)

        # СТРАНИЦА 1: APP STORE
        self.page_store = QWidget()
        page1_layout = QVBoxLayout(self.page_store)

        # Верхняя панель поиска
        store_top_bar = QHBoxLayout()
        self.search_store = QLineEdit()
        self.search_store.setObjectName("SearchField")
        self.search_store.setPlaceholderText("Search in pacman & AUR...")
        self.combo_store = QComboBox()
        self.combo_store.setObjectName("CategoryDropdown")
        self.combo_store.addItems(["All", "Software", "Games", "Internet", "Media", "Graphics", "Drivers"])

        store_top_bar.addWidget(self.search_store, 3)
        store_top_bar.addWidget(self.combo_store, 1)
        page1_layout.addLayout(store_top_bar)

        # Область прокрутки пакетов
        self.scroll_store = QScrollArea()
        self.scroll_store.setWidgetResizable(True)
        self.scroll_store.setObjectName("PackageList")
        self.content_store = QWidget()
        self.content_store.setObjectName("ScrollContent")
        self.layout_store = QVBoxLayout(self.content_store)
        self.layout_store.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_store.setWidget(self.content_store)

        self.store_loading_lbl = QLabel("Loading package database... Please wait.")
        self.store_loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.store_loading_lbl.setStyleSheet("color: #a6adc8; font-size: 16px;")
        self.layout_store.addWidget(self.store_loading_lbl)

        page1_layout.addWidget(self.scroll_store)

        # --- НОВОЕ: ПАНЕЛЬ ПАГИНАЦИИ ---
        self.pagination_layout = QHBoxLayout()

        self.btn_prev_page = QPushButton("⬅ Previous")
        self.btn_prev_page.setObjectName("PaginationBtn")
        self.btn_prev_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev_page.setFixedWidth(120)

        self.lbl_page_info = QLabel("Page 1 / 1")
        self.lbl_page_info.setStyleSheet("color: rgb(180, 170, 200); font-weight: bold;")
        self.lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_next_page = QPushButton("Next ➡")
        self.btn_next_page.setObjectName("PaginationBtn")
        self.btn_next_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next_page.setFixedWidth(120)

        self.pagination_layout.addWidget(self.btn_prev_page)
        self.pagination_layout.addWidget(self.lbl_page_info, 1)
        self.pagination_layout.addWidget(self.btn_next_page)

        page1_layout.addLayout(self.pagination_layout)
        # ---------------------------------

        self.stacked_widget.addWidget(self.page_store)

        main_layout.addWidget(self.right_panel)
