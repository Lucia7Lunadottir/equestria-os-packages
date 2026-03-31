from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QCheckBox, QLineEdit, QGroupBox)
from PyQt6.QtCore import Qt

class Ui_SettingsWindow:
    def setupUi(self, MainWindow):
        MainWindow.resize(450, 420)

        self.central_widget = QWidget(MainWindow)
        MainWindow.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(16, 16, 16, 16)

        # Контейнер для кнопок языков
        self.lang_layout = QHBoxLayout()
        self.lang_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addLayout(self.lang_layout)

        # Шапка
        self.lbl_title = QLabel()
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        layout.addWidget(self.lbl_title)

        self.lbl_path = QLabel()
        self.lbl_path.setStyleSheet("color: rgb(140, 130, 160); font-size: 11px;")
        self.lbl_path.setWordWrap(True)
        layout.addWidget(self.lbl_path)

        # Группа: Графика и система
        self.group_graphics = QGroupBox()
        glayout = QVBoxLayout(self.group_graphics)

        self.chk_fps = QCheckBox()
        glayout.addWidget(self.chk_fps)

        self.chk_desktop = QCheckBox()
        glayout.addWidget(self.chk_desktop)

        self.chk_fsr = QCheckBox()
        glayout.addWidget(self.chk_fsr)
        layout.addWidget(self.group_graphics)

        # Группа: Параметры запуска
        self.group_args = QGroupBox()
        alayout = QVBoxLayout(self.group_args)
        self.txt_args = QLineEdit()
        alayout.addWidget(self.txt_args)
        layout.addWidget(self.group_args)

        # Группа: Опасная зона
        self.group_danger = QGroupBox()
        dlayout = QHBoxLayout(self.group_danger)
        self.lbl_danger = QLabel()
        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("btnDanger")
        dlayout.addWidget(self.lbl_danger)
        dlayout.addStretch()
        dlayout.addWidget(self.btn_clear)
        layout.addWidget(self.group_danger)

        layout.addStretch()

        # Кнопки снизу
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton()
        self.btn_save = QPushButton()
        self.btn_save.setObjectName("btnSave")
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)
