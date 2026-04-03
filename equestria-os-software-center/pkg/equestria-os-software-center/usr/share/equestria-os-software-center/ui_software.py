import os
import subprocess
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QFrame, QListWidget,
                             QStackedWidget, QLineEdit, QComboBox, QProgressBar,
                             QGridLayout, QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap


class ClickableImageLabel(QLabel):
    """Screenshot label that opens the image with xdg-open on click."""
    def __init__(self):
        super().__init__()
        self._local_path = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_local_path(self, path):
        self._local_path = path

    def mousePressEvent(self, event):
        if self._local_path and os.path.exists(self._local_path):
            subprocess.Popen(["xdg-open", self._local_path])
        super().mousePressEvent(event)


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
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 40)
        icon_set = False
        if getattr(pkg_data, 'icon_url', None) and os.path.exists(pkg_data.icon_url):
            pix = QPixmap(pkg_data.icon_url)
            if not pix.isNull():
                self.icon_label.setPixmap(
                    pix.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
                icon_set = True
        if not icon_set:
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
        num_votes = getattr(pkg_data, 'num_votes', 0)
        if num_votes and getattr(pkg_data, 'source_type', '') == 'aur':
            lbl_votes = QLabel(f"⬆ {num_votes} votes")
            lbl_votes.setStyleSheet("color: #f9e2af; font-size: 11px; background: transparent;")
            info_layout.addWidget(lbl_votes)
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

    # Screenshot dimensions
    _SS_W = 360
    _SS_H = 250

    _CSS_BTN_INSTALL = (
        "QPushButton { background-color: rgb(203,166,247); color: rgb(17,17,27); "
        "border-radius: 8px; padding: 8px 16px; font-weight: bold; font-size: 14px; border: none; }"
        "QPushButton:hover { background-color: rgb(190,140,240); }"
        "QPushButton:disabled { background-color: rgb(69,71,90); color: rgb(108,112,134); }"
    )
    _CSS_BTN_REMOVE = (
        "QPushButton { background-color: rgb(243,139,168); color: rgb(17,17,27); "
        "border-radius: 8px; padding: 8px 16px; font-weight: bold; font-size: 14px; border: none; }"
        "QPushButton:hover { background-color: rgb(220,100,130); }"
    )
    _CSS_BTN_UPDATE = (
        "QPushButton { background-color: rgb(249,226,175); color: rgb(17,17,27); "
        "border-radius: 8px; padding: 8px 16px; font-weight: bold; font-size: 14px; border: none; }"
        "QPushButton:hover { background-color: rgb(230,200,140); }"
    )
    _CSS_COMBO = (
        "QComboBox { background-color: rgb(17,17,27); border: 1px solid rgb(49,50,68); "
        "border-radius: 8px; padding: 6px 12px; color: white; }"
        "QComboBox::drop-down { border: none; }"
        "QComboBox QAbstractItemView { background-color: rgb(17,17,27); color: white; "
        "selection-background-color: rgb(49,50,68); border: 1px solid rgb(49,50,68); }"
    )

    def _setup_ui(self):
        # Direct layout — no outer QScrollArea (it breaks QSS cascade in Qt6)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 12, 20, 15)
        main_layout.setSpacing(8)

        # Back button
        self.btn_back = QPushButton("← Back")
        self.btn_back.setObjectName("DetailBackBtn")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setFixedWidth(110)
        self.btn_back.setStyleSheet(
            "QPushButton { background-color: transparent; color: rgb(137,180,250); "
            "border: 1px solid rgb(137,180,250); border-radius: 6px; padding: 6px 10px; font-weight: bold; }"
            "QPushButton:hover { background-color: rgba(137,180,250,0.15); }"
        )
        self.btn_back.clicked.connect(self._on_back)
        main_layout.addWidget(self.btn_back)

        # Header: icon + info + action
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
        self.lbl_votes = QLabel()
        self.lbl_votes.setStyleSheet("color: #f9e2af; font-size: 13px; background: transparent;")
        self.lbl_votes.hide()
        info_layout.addWidget(self.lbl_app_name)
        info_layout.addWidget(self.lbl_version)
        info_layout.addWidget(self.lbl_source)
        info_layout.addWidget(self.lbl_votes)
        header_layout.addLayout(info_layout, 1)

        action_col = QVBoxLayout()
        action_col.setSpacing(6)
        action_col.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_action = QPushButton("Install")
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setFixedWidth(160)
        self.btn_action.setMinimumHeight(40)
        self.btn_action.setStyleSheet(self._CSS_BTN_INSTALL)

        # Version selector — inline styled to guarantee visibility
        self.combo_version = QComboBox()
        self.combo_version.setFixedWidth(160)
        self.combo_version.setStyleSheet(self._CSS_COMBO)
        self.combo_version.hide()


        # Source selector (Выбор источника)
        self.combo_source_selector = QComboBox()
        self.combo_source_selector.setFixedWidth(160)
        self.combo_source_selector.setStyleSheet(self._CSS_COMBO)
        self.combo_source_selector.hide()

        action_col.addWidget(self.btn_action)
        action_col.addWidget(self.combo_source_selector)
        action_col.addWidget(self.combo_version)
        header_layout.addLayout(action_col)
        main_layout.addLayout(header_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: rgba(49,50,68,0.8); max-height: 1px; border: none;")
        main_layout.addWidget(sep)

        # AUR warning
        self.lbl_aur_warning = QLabel()
        self.lbl_aur_warning.setStyleSheet(
            "color: #f9e2af; background: rgba(249,226,175,0.1); border-radius: 6px; "
            "padding: 8px; font-size: 13px; border: 1px solid rgba(249,226,175,0.3);"
        )
        self.lbl_aur_warning.setWordWrap(True)
        self.lbl_aur_warning.hide()
        main_layout.addWidget(self.lbl_aur_warning)

        # Description (word-wrapped, limited to 3 lines to save space)
        self.lbl_desc = QLabel()
        self.lbl_desc.setStyleSheet("color: #bac2de; font-size: 14px; background: transparent;")
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_desc.setMaximumHeight(80)
        main_layout.addWidget(self.lbl_desc)

        # Screenshots separator + header
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background: rgba(49,50,68,0.8); max-height: 1px; border: none;")
        main_layout.addWidget(sep2)

        self.lbl_screenshots_header = QLabel("Screenshots")
        self.lbl_screenshots_header.setStyleSheet(
            "color: #89b4fa; font-weight: bold; font-size: 11px; "
            "text-transform: uppercase; background: transparent; padding-left: 2px;"
        )
        main_layout.addWidget(self.lbl_screenshots_header)

        # Horizontal screenshot scroll
        # Height = image + margins(10) + thin scrollbar(10)
        _sa_h = self._SS_H + 20
        self.scroll_screenshots = QScrollArea()
        self.scroll_screenshots.setObjectName("ScreenshotScroll")
        self.scroll_screenshots.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_screenshots.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_screenshots.setFixedHeight(_sa_h)
        self.scroll_screenshots.setWidgetResizable(False)
        # Must set style on both the scroll area and its viewport
        self.scroll_screenshots.setStyleSheet(
            "QScrollArea#ScreenshotScroll { background: transparent; border: none; }"
        )

        self.screenshots_container = QWidget()
        self.screenshots_container.setStyleSheet("background: transparent;")
        self.screenshots_container.setFixedHeight(self._SS_H + 10)
        self.screenshots_layout = QHBoxLayout(self.screenshots_container)
        self.screenshots_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.screenshots_layout.setContentsMargins(2, 2, 2, 2)
        self.screenshots_layout.setSpacing(10)
        self.scroll_screenshots.setWidget(self.screenshots_container)
        # Set viewport background AFTER setWidget (it recreates the viewport)
        self.scroll_screenshots.viewport().setStyleSheet("background: transparent;")

        main_layout.addWidget(self.scroll_screenshots)
        main_layout.addStretch()

    def load_package_group(self, alts_dict, default_source, t_func, installed_set, flatpak_installed_set, upgradable_set, on_install, on_remove, on_source_changed):
        self.alts_dict = alts_dict
        self.t_func = t_func
        self.installed_set = installed_set
        self.flatpak_installed_set = flatpak_installed_set
        self.upgradable_set = upgradable_set
        self.on_install = on_install
        self.on_remove = on_remove
        self.on_source_changed = on_source_changed

        # Настраиваем комбобокс источников
        self.combo_source_selector.blockSignals(True)
        self.combo_source_selector.clear()

        # Задаем приоритет и красивые названия
        source_labels = {"pacman": "Pacman (System)", "flatpak": "Flatpak (Flathub)", "aur": "AUR (Community)"}

        for src in ["pacman", "flatpak", "aur"]:
            if src in alts_dict:
                self.combo_source_selector.addItem(source_labels[src], src)
                if src == default_source:
                    self.combo_source_selector.setCurrentIndex(self.combo_source_selector.count() - 1)

        self.combo_source_selector.blockSignals(False)
        self.combo_source_selector.show() if len(alts_dict) > 1 else self.combo_source_selector.hide()

        try:
            self.combo_source_selector.currentIndexChanged.disconnect()
        except TypeError:
            pass
        self.combo_source_selector.currentIndexChanged.connect(self._switch_source)

        # Загружаем выбранный по умолчанию
        self._switch_source()

    def _switch_source(self):
        source_key = self.combo_source_selector.currentData()
        pkg_data = self.alts_dict[source_key]
        t_func = self.t_func

        self.btn_back.setText("← " + t_func("ui.detail_back"))
        self.lbl_app_name.setText(pkg_data.name)
        self.lbl_version.setText(f"v{pkg_data.version}" if pkg_data.version else "")
        self.lbl_source.setText(t_func("ui.detail_source") + ": " + pkg_data.source)
        self.lbl_desc.setText(pkg_data.desc)
        self.lbl_screenshots_header.setText(t_func("ui.detail_screenshots"))

        # Version selector
        all_versions = getattr(pkg_data, 'all_versions', [])
        if len(all_versions) > 1:
            self.combo_version.blockSignals(True)
            self.combo_version.clear()
            for v in all_versions:
                self.combo_version.addItem(f"v{v}", v)
            self.combo_version.setCurrentIndex(0)
            self.combo_version.blockSignals(False)
            self.combo_version.show()
        else:
            self.combo_version.hide()

        # Icon
        icon_set = False
        if getattr(pkg_data, 'icon_url', None) and os.path.exists(pkg_data.icon_url):
            pix = QPixmap(pkg_data.icon_url)
            if not pix.isNull():
                self.lbl_icon.setPixmap(pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                icon_set = True
        if not icon_set:
            theme_icon = QIcon.fromTheme(pkg_data.name, QIcon.fromTheme("application-x-executable"))
            self.lbl_icon.setPixmap(theme_icon.pixmap(80, 80))

        # NumVotes (AUR)
        num_votes = getattr(pkg_data, 'num_votes', 0)
        if pkg_data.source_type == "aur" and num_votes:
            self.lbl_votes.setText(f"⬆ {num_votes} votes")
            self.lbl_votes.show()
        else:
            self.lbl_votes.hide()

        self.lbl_aur_warning.setText(t_func("ui.aur_warning"))
        self.lbl_aur_warning.show() if pkg_data.source_type == "aur" else self.lbl_aur_warning.hide()

        # Action button logic
        try:
            self.btn_action.clicked.disconnect()
        except TypeError:
            pass

        if pkg_data.source_type == "flatpak":
            is_installed = bool(pkg_data.app_id and pkg_data.app_id in self.flatpak_installed_set)
            is_upgradable = False
        else:
            is_upgradable = pkg_data.name in self.upgradable_set
            is_installed = pkg_data.name in self.installed_set

        if is_upgradable:
            self.btn_action.setText(t_func("ui.update"))
            self.btn_action.setEnabled(True)
            self.btn_action.setStyleSheet(self._CSS_BTN_UPDATE)
            if self.on_install: self.btn_action.clicked.connect(lambda: self.on_install(pkg_data))
        elif is_installed:
            self.btn_action.setText(t_func("ui.remove"))
            self.btn_action.setEnabled(True)
            self.btn_action.setStyleSheet(self._CSS_BTN_REMOVE)
            if self.on_remove: self.btn_action.clicked.connect(lambda: self.on_remove(pkg_data))
        else:
            self.btn_action.setText(t_func("ui.install"))
            self.btn_action.setEnabled(True)
            self.btn_action.setStyleSheet(self._CSS_BTN_INSTALL)
            if self.on_install: self.btn_action.clicked.connect(lambda: self.on_install(pkg_data))

        # Оповещаем main.py, что источник сменился (чтобы подгрузить нужные скриншоты)
        self.on_source_changed(pkg_data)

    def clear_screenshots(self):
        while self.screenshots_layout.count():
            item = self.screenshots_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.screenshots_container.setMinimumWidth(0)

    def add_screenshot_placeholder(self):
        lbl = ClickableImageLabel()
        lbl.setFixedSize(self._SS_W, self._SS_H)
        lbl.setStyleSheet(
            "background: rgba(49,50,68,0.5); border-radius: 8px; "
            "border: 1px solid rgba(69,71,90,0.5); color: #6c7086;"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setText("...")
        self.screenshots_layout.addWidget(lbl)
        count = self.screenshots_layout.count()
        self.screenshots_container.setMinimumWidth(count * (self._SS_W + 10) + 10)
        return lbl

    def set_screenshot_image(self, lbl, local_path):
        pix = QPixmap(local_path)
        if not pix.isNull():
            scaled = pix.scaled(self._SS_W, self._SS_H,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(scaled)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.set_local_path(local_path)
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

        self.btn_integrity_check = QPushButton("Check System Files")
        self.btn_integrity_check.setObjectName("IntegrityBtn")
        self.btn_integrity_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_integrity_check.setMinimumHeight(45)
        left_layout.addWidget(self.btn_integrity_check)

        self.btn_cache_clean = QPushButton("Clean Package Cache")
        self.btn_cache_clean.setObjectName("CacheCleanBtn")
        self.btn_cache_clean.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cache_clean.setMinimumHeight(45)
        left_layout.addWidget(self.btn_cache_clean)

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
        self.combo_source.addItems(["All", "Pacman", "AUR", "Flatpak", "Updates"])

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
