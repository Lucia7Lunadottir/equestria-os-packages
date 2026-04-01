import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QFrame, QListWidget,
                             QStackedWidget, QLineEdit, QComboBox, QProgressBar,
                             QGridLayout, QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap


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

        desc_text = getattr(app_data, 'display_desc', app_data.desc_key)
        self.lbl_desc = QLabel(desc_text)
        self.lbl_desc.setStyleSheet("color: rgb(170, 160, 200); font-size: 13px; background: transparent;")

        text_layout.addWidget(self.lbl_name)
        text_layout.addWidget(self.lbl_desc)

        layout.addWidget(self.checkbox)
        layout.addLayout(text_layout)
        layout.addStretch()


class StoreAppRow(QFrame):
    def __init__(self, pkg_data, action_text, on_action, on_row_click=None):
        super().__init__()
        self.pkg_data = pkg_data
        self._on_row_click = on_row_click
        self.setObjectName("PackageRow")
        self.setMinimumHeight(75)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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

    def mousePressEvent(self, event):
        if self._on_row_click:
            self._on_row_click(self.pkg_data)
        super().mousePressEvent(event)


class AppDetailWidget(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self._on_back = on_back
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 15, 20, 15)
        main_layout.setSpacing(10)

        # Back button
        self.btn_back = QPushButton("← Back")
        self.btn_back.setObjectName("DetailBackBtn")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setFixedWidth(110)
        self.btn_back.clicked.connect(self._on_back)
        main_layout.addWidget(self.btn_back)

        # Header: icon + name/version/source + action button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(80, 80)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setStyleSheet(
            "background: rgba(49,50,68,0.5); border-radius: 10px; border: 1px solid rgba(69,71,90,0.5);"
        )
        header_layout.addWidget(self.lbl_icon)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        self.lbl_app_name = QLabel()
        self.lbl_app_name.setStyleSheet(
            "color: white; font-size: 22px; font-weight: bold; background: transparent;"
        )
        self.lbl_version = QLabel()
        self.lbl_version.setStyleSheet("color: #6c7086; font-size: 14px; background: transparent;")
        self.lbl_source = QLabel()
        self.lbl_source.setStyleSheet("color: #89b4fa; font-size: 14px; background: transparent;")
        info_layout.addWidget(self.lbl_app_name)
        info_layout.addWidget(self.lbl_version)
        info_layout.addWidget(self.lbl_source)
        header_layout.addLayout(info_layout, 1)

        self.btn_action = QPushButton("Install")
        self.btn_action.setObjectName("DetailActionBtn")
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setFixedWidth(150)
        self.btn_action.setMinimumHeight(40)
        header_layout.addWidget(self.btn_action)

        main_layout.addLayout(header_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(49,50,68,0.8); margin: 5px 0;")
        main_layout.addWidget(sep)

        # AUR warning banner
        self.lbl_aur_warning = QLabel()
        self.lbl_aur_warning.setStyleSheet(
            "color: #f9e2af; background: rgba(249,226,175,0.1); border-radius: 6px; "
            "padding: 8px; font-size: 13px; border: 1px solid rgba(249,226,175,0.3);"
        )
        self.lbl_aur_warning.setWordWrap(True)
        self.lbl_aur_warning.hide()
        main_layout.addWidget(self.lbl_aur_warning)

        # Description (scrollable, max height)
        self.scroll_desc = QScrollArea()
        self.scroll_desc.setWidgetResizable(True)
        self.scroll_desc.setMaximumHeight(110)
        self.scroll_desc.setStyleSheet("background: transparent; border: none;")
        desc_container = QWidget()
        desc_container.setStyleSheet("background: transparent;")
        desc_inner = QVBoxLayout(desc_container)
        desc_inner.setContentsMargins(0, 0, 0, 0)
        self.lbl_desc = QLabel()
        self.lbl_desc.setStyleSheet("color: #bac2de; font-size: 14px; background: transparent;")
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        desc_inner.addWidget(self.lbl_desc)
        desc_inner.addStretch()
        self.scroll_desc.setWidget(desc_container)
        main_layout.addWidget(self.scroll_desc)

        # Screenshots section
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: rgba(49,50,68,0.8); margin: 5px 0;")
        main_layout.addWidget(sep2)

        self.lbl_screenshots_header = QLabel("Screenshots")
        self.lbl_screenshots_header.setStyleSheet(
            "color: #89b4fa; font-weight: bold; font-size: 11px; "
            "text-transform: uppercase; background: transparent; padding-left: 2px;"
        )
        main_layout.addWidget(self.lbl_screenshots_header)

        self.scroll_screenshots = QScrollArea()
        self.scroll_screenshots.setObjectName("ScreenshotScroll")
        self.scroll_screenshots.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_screenshots.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_screenshots.setFixedHeight(220)
        self.scroll_screenshots.setWidgetResizable(False)

        self.screenshots_container = QWidget()
        self.screenshots_container.setStyleSheet("background: transparent;")
        self.screenshots_layout = QHBoxLayout(self.screenshots_container)
        self.screenshots_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.screenshots_layout.setContentsMargins(5, 5, 5, 5)
        self.screenshots_layout.setSpacing(10)
        self.scroll_screenshots.setWidget(self.screenshots_container)

        main_layout.addWidget(self.scroll_screenshots)

    def load_package(self, pkg_data, t_func, installed_set, flatpak_installed_set,
                     upgradable_set, on_install=None, on_remove=None):
        self.btn_back.setText("← " + t_func("ui.detail_back"))
        self.lbl_app_name.setText(pkg_data.name)
        self.lbl_version.setText(f"v{pkg_data.version}" if pkg_data.version else "")
        self.lbl_source.setText(t_func("ui.detail_source") + ": " + pkg_data.source)
        self.lbl_desc.setText(pkg_data.desc)
        self.lbl_screenshots_header.setText(t_func("ui.detail_screenshots"))

        # Icon
        icon_set = False
        if pkg_data.icon_url and os.path.exists(pkg_data.icon_url):
            pix = QPixmap(pkg_data.icon_url)
            if not pix.isNull():
                self.lbl_icon.setPixmap(
                    pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
                icon_set = True
        if not icon_set:
            theme_icon = QIcon.fromTheme(pkg_data.name, QIcon.fromTheme("application-x-executable"))
            self.lbl_icon.setPixmap(theme_icon.pixmap(80, 80))

        # AUR warning
        if pkg_data.source_type == "aur":
            self.lbl_aur_warning.setText(t_func("ui.aur_warning"))
            self.lbl_aur_warning.show()
        else:
            self.lbl_aur_warning.hide()

        # Action button — disconnect old signal first
        try:
            self.btn_action.clicked.disconnect()
        except TypeError:
            pass

        if pkg_data.source_type == "flatpak":
            is_installed = bool(pkg_data.app_id and pkg_data.app_id in flatpak_installed_set)
            is_upgradable = False
        else:
            is_upgradable = pkg_data.name in upgradable_set
            is_installed = pkg_data.name in installed_set

        if is_upgradable:
            self.btn_action.setText(t_func("ui.update"))
            self.btn_action.setEnabled(True)
            self.btn_action.setStyleSheet("")
            if on_install:
                self.btn_action.clicked.connect(lambda: on_install(pkg_data))
        elif is_installed:
            self.btn_action.setText(t_func("ui.remove"))
            self.btn_action.setEnabled(True)
            self.btn_action.setStyleSheet("background-color: #f38ba8; color: #11111b;")
            if on_remove:
                self.btn_action.clicked.connect(lambda: on_remove(pkg_data))
        else:
            self.btn_action.setText(t_func("ui.install"))
            self.btn_action.setEnabled(True)
            self.btn_action.setStyleSheet("")
            if on_install:
                self.btn_action.clicked.connect(lambda: on_install(pkg_data))

    def clear_screenshots(self):
        while self.screenshots_layout.count():
            item = self.screenshots_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.screenshots_container.setMinimumWidth(0)

    def add_screenshot_placeholder(self):
        lbl = QLabel()
        lbl.setFixedSize(300, 200)
        lbl.setStyleSheet(
            "background: rgba(49,50,68,0.5); border-radius: 8px; "
            "border: 1px solid rgba(69,71,90,0.5); color: #6c7086;"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setText("...")
        self.screenshots_layout.addWidget(lbl)
        count = self.screenshots_layout.count()
        self.screenshots_container.setMinimumWidth(count * 310 + 10)
        return lbl

    def set_screenshot_image(self, lbl, local_path):
        pix = QPixmap(local_path)
        if not pix.isNull():
            lbl.setPixmap(
                pix.scaled(300, 200, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setText("")

    def show_no_screenshots(self, t_func):
        self.clear_screenshots()
        lbl = QLabel(t_func("ui.no_screenshots"))
        lbl.setStyleSheet("color: #6c7086; font-size: 13px; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshots_layout.addWidget(lbl)


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

        # --- LEFT PANEL (NAVIGATION) ---
        self.left_panel = QFrame()
        self.left_panel.setObjectName("LeftPanel")
        self.left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(self.left_panel)

        self.title_label = QLabel("Equestria Software Center")
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.title_label)

        # Language grid
        self.lang_container = QWidget()
        self.lang_layout = QGridLayout(self.lang_container)
        self.lang_layout.setSpacing(4)
        self.lang_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.lang_container)

        # Essentials categories
        self.cat_header = QLabel("🌟 Essentials")
        self.cat_header.setObjectName("CategoryHeader")
        left_layout.addWidget(self.cat_header)

        self.cat_list = QListWidget()
        self.cat_list.setObjectName("CategoryList")
        self.cat_list.setMinimumHeight(80)
        left_layout.addWidget(self.cat_list, 1)

        # App store nav
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

        # --- RIGHT PANEL (QStackedWidget) ---
        self.right_panel = QFrame()
        self.right_panel.setObjectName("RightPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.stacked_widget = QStackedWidget()
        right_layout.addWidget(self.stacked_widget)

        # PAGE 0: ESSENTIALS
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

        # PAGE 1: APP STORE
        self.page_store = QWidget()
        page1_layout = QVBoxLayout(self.page_store)

        # Top bar: search + category filter + source filter
        store_top_bar = QHBoxLayout()
        self.search_store = QLineEdit()
        self.search_store.setObjectName("SearchField")
        self.search_store.setPlaceholderText("Search...")
        self.combo_store = QComboBox()
        self.combo_store.setObjectName("CategoryDropdown")
        self.combo_store.addItems(["All", "Software", "Games", "Internet", "Media", "Graphics", "Drivers"])
        self.combo_source = QComboBox()
        self.combo_source.setObjectName("CategoryDropdown")
        self.combo_source.addItems(["All", "Pacman", "AUR", "Flatpak"])

        store_top_bar.addWidget(self.search_store, 3)
        store_top_bar.addWidget(self.combo_store, 1)
        store_top_bar.addWidget(self.combo_source, 1)
        page1_layout.addLayout(store_top_bar)

        # Package scroll area
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

        # Pagination
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

        self.stacked_widget.addWidget(self.page_store)

        main_layout.addWidget(self.right_panel)
