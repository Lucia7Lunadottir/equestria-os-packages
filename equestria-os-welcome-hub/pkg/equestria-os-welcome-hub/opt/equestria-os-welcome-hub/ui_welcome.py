from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QFrame, QSpacerItem, QSizePolicy)
from PyQt6.QtCore import Qt

class Ui_WelcomeHub:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1000, 700)

        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        main_layout = QHBoxLayout(self.root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- SIDEBAR ---
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(15, 20, 15, 15)

        self.sidebar_title = QLabel("Equestria OS")
        self.sidebar_title.setObjectName("SidebarTitle")

        self.lang_container = QVBoxLayout()
        self.lang_row1 = QHBoxLayout()
        self.lang_row2 = QHBoxLayout()
        self.lang_container.addLayout(self.lang_row1)
        self.lang_container.addLayout(self.lang_row2)

        self.nav_container = QVBoxLayout()
        self.nav_container.setSpacing(4)

        # ФИКС: Кастомный чекбокс (Кнопка + Текст)
        self.autostart_container = QHBoxLayout()
        self.autostart_container.setSpacing(10)

        self.autostart_checkbox = QPushButton("✔")
        self.autostart_checkbox.setObjectName("AutostartToggle")
        self.autostart_checkbox.setCheckable(True)
        self.autostart_checkbox.setFixedSize(24, 24)
        self.autostart_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)

        self.autostart_label = QLabel("Launch on startup")
        self.autostart_label.setStyleSheet("color: rgb(166, 173, 200); font-size: 13px; font-family: sans-serif;")
        self.autostart_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.autostart_label.mousePressEvent = lambda e: self.autostart_checkbox.toggle() # Клик по тексту переключает галочку

        self.autostart_container.addWidget(self.autostart_checkbox)
        self.autostart_container.addWidget(self.autostart_label)
        self.autostart_container.addStretch()

        sidebar_layout.addWidget(self.sidebar_title)
        sidebar_layout.addLayout(self.lang_container)
        sidebar_layout.addSpacing(20)
        sidebar_layout.addLayout(self.nav_container)
        sidebar_layout.addStretch()
        sidebar_layout.addLayout(self.autostart_container)

        # --- MAIN VIEW ---
        self.main_view = QWidget()
        view_layout = QVBoxLayout(self.main_view)
        view_layout.setContentsMargins(35, 30, 35, 30)

        self.cat_title = QLabel("Category")
        self.cat_title.setObjectName("CategoryTitle")

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("content_widget")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.content_widget)

        view_layout.addWidget(self.cat_title)
        view_layout.addWidget(self.scroll_area)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.main_view)
