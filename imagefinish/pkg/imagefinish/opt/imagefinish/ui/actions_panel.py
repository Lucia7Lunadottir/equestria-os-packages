from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from core.locale import tr

BTN_STYLE = ("QPushButton{background:#313244;color:#cdd6f4;border:none;padding:4px 10px;border-radius:4px;}"
             "QPushButton:hover{background:#45475a;}"
             "QPushButton:pressed{background:#585b70;}")
HEADER_STYLE = "color:#7f849c;font-size:10px;font-weight:bold;letter-spacing:1px;background:transparent;padding:8px 10px 4px 10px;"

_BUILTIN_ACTIONS = [
    "Invert",
    "Desaturate",
    "Sharpen",
    "Flatten Image",
    "Auto Levels",
    "Grayscale Mode",
]


class ActionsPanel(QWidget):
    action_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Section header
        self._title_lbl = QLabel("ACTIONS")
        self._title_lbl.setObjectName("panelTitle")
        self._title_lbl.setStyleSheet(HEADER_STYLE)
        layout.addWidget(self._title_lbl)

        # Action list
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{background:#1e1e2e;border:none;color:#cdd6f4;}"
            "QListWidget::item{padding:4px 8px;}"
            "QListWidget::item:selected{background:#313244;color:#cba6f7;}"
            "QListWidget::item:hover{background:#282838;}"
        )
        layout.addWidget(self._list, 1)

        # Button bar
        btn_bar = QWidget()
        btn_lo = QHBoxLayout(btn_bar)
        btn_lo.setContentsMargins(8, 6, 8, 8)
        btn_lo.setSpacing(6)

        self._play_btn = QPushButton("\u25b6 Play")
        self._play_btn.setStyleSheet(BTN_STYLE)
        self._play_btn.clicked.connect(self._on_play)
        btn_lo.addWidget(self._play_btn)
        btn_lo.addStretch()

        layout.addWidget(btn_bar)

        self._populate_list()

    def _populate_list(self):
        self._list.clear()

        # Group header
        group_item = QListWidgetItem(tr("actions.group.default") if tr("actions.group.default") != "actions.group.default" else "Default Actions")
        group_item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        group_item.setFont(font)
        group_item.setForeground(Qt.GlobalColor.gray)
        self._list.addItem(group_item)

        for action_name in _BUILTIN_ACTIONS:
            item = QListWidgetItem("  " + action_name)
            item.setData(Qt.ItemDataRole.UserRole, action_name)
            self._list.addItem(item)

        if self._list.count() > 1:
            self._list.setCurrentRow(1)

    def _on_play(self):
        item = self._list.currentItem()
        if item is None:
            return
        action_name = item.data(Qt.ItemDataRole.UserRole)
        if action_name:
            self.action_requested.emit(action_name)

    def retranslate(self):
        self._title_lbl.setText(
            tr("actions.title") if tr("actions.title") != "actions.title" else "ACTIONS"
        )
        self._play_btn.setText(
            tr("actions.play") if tr("actions.play") != "actions.play" else "\u25b6 Play"
        )
        self._populate_list()
