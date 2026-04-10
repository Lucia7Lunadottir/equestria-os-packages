from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QScrollArea, QFrame, QCheckBox)
from PyQt6.QtCore import Qt

class CountryRow(QFrame):
    def __init__(self, country_data, on_toggle_callback):
        super().__init__()
        self.country_data = country_data
        self.setObjectName("CountryRow")
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)

        # ФИКС: Используем кнопку как чекбокс с текстовой галочкой
        self.checkbox = QPushButton("✔")
        self.checkbox.setObjectName("CountryToggle")
        self.checkbox.setCheckable(True)
        self.checkbox.setFixedSize(22, 22)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.toggled.connect(lambda checked: on_toggle_callback(self.country_data["code"], checked))

        # Клик по всей строке переключает чекбокс
        self.mousePressEvent = lambda e: self.checkbox.toggle()

        self.lbl_name = QLabel(country_data["name"])
        self.lbl_name.setObjectName("CountryName")

        self.lbl_code = QLabel(country_data["code"])
        self.lbl_code.setObjectName("CountryCode")
        self.lbl_code.setFixedWidth(40)
        self.lbl_code.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_mirrors = QLabel(f"{country_data['mirrors']} mirrors")
        self.lbl_mirrors.setObjectName("CountryMirrors")
        self.lbl_mirrors.setFixedWidth(80)
        self.lbl_mirrors.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self.checkbox)
        layout.addSpacing(10)
        layout.addWidget(self.lbl_name, 1) # 1 = растягивается
        layout.addWidget(self.lbl_code)
        layout.addWidget(self.lbl_mirrors)

class Ui_RankMirrors:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(800, 600)

        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        main_layout = QVBoxLayout(self.root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- HEADER ---
        self.header = QFrame()
        self.header.setObjectName("Header")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(16, 12, 16, 12)
        self.title_label = QLabel("🐴  Equestria OS — Selecting Mirrors")
        self.title_label.setObjectName("TitleLabel")
        h_layout.addWidget(self.title_label)
        h_layout.addStretch()

        # --- CONTENT ---
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)

        # Left Panel
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 16, 0)

        lbl_select = QLabel("Select countries to search mirrors:")
        lbl_select.setObjectName("SectionTitle")

        self.search_field = QLineEdit()
        self.search_field.setObjectName("SearchField")
        self.search_field.setPlaceholderText("🔍 Searching for a country...")

        self.scroll_countries = QScrollArea()
        self.scroll_countries.setObjectName("CountryList")
        self.scroll_countries.setWidgetResizable(True)
        self.countries_content = QWidget()
        self.countries_content.setObjectName("ScrollContent")
        self.countries_layout = QVBoxLayout(self.countries_content)
        self.countries_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.countries_layout.setSpacing(0)
        self.scroll_countries.setWidget(self.countries_content)

        self.lbl_selected_count = QLabel("Selected countries: 0")
        self.lbl_selected_count.setObjectName("SelectedCount")

        left_layout.addWidget(lbl_select)
        left_layout.addWidget(self.search_field)
        left_layout.addWidget(self.scroll_countries, 1)
        left_layout.addWidget(self.lbl_selected_count)

        # Right Panel
        right_panel = QWidget()
        right_panel.setFixedWidth(280)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        lbl_current = QLabel("Current mirrors:")
        lbl_current.setObjectName("SectionTitle")

        self.scroll_mirrors = QScrollArea()
        self.scroll_mirrors.setObjectName("MirrorsScroll")
        self.scroll_mirrors.setWidgetResizable(True)
        mirrors_content = QWidget()
        mirrors_content.setObjectName("ScrollContent")
        m_layout = QVBoxLayout(mirrors_content)
        m_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.lbl_current_mirrors = QLabel("Loading...")
        self.lbl_current_mirrors.setObjectName("CurrentMirrors")
        self.lbl_current_mirrors.setWordWrap(True)
        self.lbl_current_mirrors.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        m_layout.addWidget(self.lbl_current_mirrors)

        self.scroll_mirrors.setWidget(mirrors_content)
        right_layout.addWidget(lbl_current)
        right_layout.addWidget(self.scroll_mirrors, 1)

        content_layout.addWidget(left_panel, 2)
        content_layout.addWidget(right_panel, 1)

        # --- FOOTER & STATUS ---
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("StatusLabel")

        self.footer = QFrame()
        self.footer.setObjectName("Footer")
        f_layout = QHBoxLayout(self.footer)
        f_layout.setContentsMargins(16, 12, 16, 12)

        self.chk_auto = QCheckBox("Auto-update mirrors (weekly)")
        self.chk_auto.setObjectName("AutoCheckbox")

        self.btn_restore = QPushButton("Restore backup")
        self.btn_restore.setObjectName("SecondaryBtn")
        self.btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_apply = QPushButton("✓ Apply")
        self.btn_apply.setObjectName("PrimaryBtn")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)

        f_layout.addWidget(self.chk_auto)
        f_layout.addStretch()
        f_layout.addWidget(self.btn_restore)
        f_layout.addWidget(self.btn_apply)

        # Assemble Main
        main_layout.addWidget(self.header)
        main_layout.addWidget(content_widget, 1)
        main_layout.addWidget(self.lbl_status)
        main_layout.addWidget(self.footer)

        # --- OVERLAY ---
        self.loading_overlay = QFrame(self.root)
        self.loading_overlay.setObjectName("LoadingOverlay")
        self.loading_overlay.hide()
        olayout = QVBoxLayout(self.loading_overlay)
        olayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_loading = QLabel("⏳ Please wait...")
        self.lbl_loading.setObjectName("LoadingText")
        olayout.addWidget(self.lbl_loading)
