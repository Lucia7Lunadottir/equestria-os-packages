from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton
from PyQt6.QtCore import pyqtSignal, Qt
from core.locale import tr

class ChannelsPanel(QWidget):
    channel_changed = pyqtSignal(str)
    save_requested = pyqtSignal()
    load_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self._list)

        self._base_channels = [
            ("RGB", "ch.rgb"),
            ("R", "ch.red"),
            ("G", "ch.green"),
            ("B", "ch.blue"),
            ("C", "ch.cyan"),
            ("M", "ch.magenta"),
            ("Y", "ch.yellow"),
            ("K", "ch.black")
        ]

        btn_bar = QWidget()
        btn_lo = QHBoxLayout(btn_bar)
        btn_lo.setContentsMargins(6, 4, 6, 6)
        btn_lo.setSpacing(4)
        
        self._btn_load = QPushButton("⭕")
        self._btn_load.setObjectName("smallBtn")
        self._btn_load.setFixedSize(32, 28)
        self._btn_load.clicked.connect(self._on_load_clicked)
        
        self._btn_save = QPushButton("💾")
        self._btn_save.setObjectName("smallBtn")
        self._btn_save.setFixedSize(32, 28)
        self._btn_save.clicked.connect(self.save_requested.emit)
        
        self._btn_del = QPushButton("🗑")
        self._btn_del.setObjectName("dangerBtn")
        self._btn_del.setFixedSize(32, 28)
        self._btn_del.clicked.connect(self._on_delete_clicked)
        
        btn_lo.addWidget(self._btn_load)
        btn_lo.addWidget(self._btn_save)
        btn_lo.addStretch()
        btn_lo.addWidget(self._btn_del)
        layout.addWidget(btn_bar)

        self._document = None
        self.retranslate()
        self._list.currentRowChanged.connect(self._on_row_changed)

    def _on_row_changed(self, row: int):
        if 0 <= row < self._list.count():
            code = self._list.item(row).data(Qt.ItemDataRole.UserRole)
            self.channel_changed.emit(code)
            
    def _on_load_clicked(self):
        row = self._list.currentRow()
        if row >= 0:
            code = self._list.item(row).data(Qt.ItemDataRole.UserRole)
            if code.startswith("alpha_"):
                self.load_requested.emit(int(code.split("_")[1]))

    def _on_delete_clicked(self):
        row = self._list.currentRow()
        if row >= 0:
            code = self._list.item(row).data(Qt.ItemDataRole.UserRole)
            if code.startswith("alpha_"):
                self.delete_requested.emit(int(code.split("_")[1]))

    def refresh(self, doc):
        self._document = doc
        current_code = "RGB"
        if self._list.currentItem():
            current_code = self._list.currentItem().data(Qt.ItemDataRole.UserRole)
            
        self._list.clear()
        for code, loc_key in self._base_channels:
            item = QListWidgetItem(tr(loc_key))
            item.setData(Qt.ItemDataRole.UserRole, code)
            self._list.addItem(item)
            
        if doc and hasattr(doc, "alpha_channels"):
            for i, alpha in enumerate(doc.alpha_channels):
                item = QListWidgetItem(alpha["name"])
                item.setData(Qt.ItemDataRole.UserRole, f"alpha_{i}")
                self._list.addItem(item)
                
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) == current_code:
                self._list.blockSignals(True)
                self._list.setCurrentRow(i)
                self._list.blockSignals(False)
                break

    def retranslate(self):
        self._btn_save.setToolTip(tr("ch.save_sel"))
        self._btn_load.setToolTip(tr("ch.load_sel"))
        self._btn_del.setToolTip(tr("ch.delete"))
        if not self._document:
            self._list.clear()
            for code, loc_key in self._base_channels:
                item = QListWidgetItem(tr(loc_key))
                item.setData(Qt.ItemDataRole.UserRole, code)
                self._list.addItem(item)
            self._list.setCurrentRow(0)
        else:
            self.refresh(self._document)