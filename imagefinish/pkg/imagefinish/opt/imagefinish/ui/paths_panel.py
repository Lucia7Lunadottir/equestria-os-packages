from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal

from core.locale import tr

ITEM_STYLE = ("QListWidget{background:#1e1e2e;border:none;color:#cdd6f4;}"
              "QListWidget::item{padding:4px 8px;}"
              "QListWidget::item:selected{background:#313244;color:#cba6f7;}"
              "QListWidget::item:hover{background:#282838;}")
BTN_STYLE = ("QPushButton{background:#313244;color:#cdd6f4;border:none;"
             "padding:4px 10px;border-radius:4px;}"
             "QPushButton:hover{background:#45475a;}"
             "QPushButton:pressed{background:#585b70;}")
LABEL_STYLE = "color:#a6adc8;font-size:11px;"

_NO_PATHS_PLACEHOLDER = "(no paths)"


class PathsPanel(QWidget):
    """
    Displays the document's work path (and any future saved paths).

    Signals allow the main window to carry out the actual path operations.
    """

    make_selection_requested = pyqtSignal()
    fill_path_requested      = pyqtSignal()
    stroke_path_requested    = pyqtSignal()
    delete_path_requested    = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        self._title = QLabel(self._title_text())
        self._title.setObjectName("panelTitle")
        layout.addWidget(self._title)

        # Path list
        self._list = QListWidget()
        self._list.setStyleSheet(ITEM_STYLE)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self._list, 1)

        # Button row
        btn_bar = QWidget()
        btn_lo = QHBoxLayout(btn_bar)
        btn_lo.setContentsMargins(0, 4, 0, 0)
        btn_lo.setSpacing(4)

        self._btn_sel    = QPushButton()
        self._btn_fill   = QPushButton()
        self._btn_stroke = QPushButton()
        self._btn_delete = QPushButton()

        for btn in (self._btn_sel, self._btn_fill, self._btn_stroke, self._btn_delete):
            btn.setStyleSheet(BTN_STYLE)
            btn.setFixedHeight(26)
            btn_lo.addWidget(btn)

        self._btn_sel.clicked.connect(self._on_make_selection)
        self._btn_fill.clicked.connect(self._on_fill)
        self._btn_stroke.clicked.connect(self._on_stroke)
        self._btn_delete.clicked.connect(self._on_delete)

        layout.addWidget(btn_bar)

        self._canvas = None
        self._has_work_path = False

        self.retranslate()

    # ----------------------------------------------------------------- public

    def refresh(self, canvas):
        """Rebuild the path list from canvas.document.work_path."""
        self._canvas = canvas
        self._list.clear()
        self._has_work_path = False

        try:
            work_path = canvas.document.work_path
        except Exception:
            work_path = None

        nodes = []
        if isinstance(work_path, dict):
            nodes = work_path.get("nodes", [])

        if nodes:
            self._has_work_path = True
            item = QListWidgetItem(tr("paths.work_path")
                                   if tr("paths.work_path") != "paths.work_path"
                                   else "Work Path")
            item.setData(Qt.ItemDataRole.UserRole, "work")
            self._list.addItem(item)
            self._list.setCurrentRow(0)
        else:
            placeholder_text = (tr("paths.no_paths")
                                 if tr("paths.no_paths") != "paths.no_paths"
                                 else _NO_PATHS_PLACEHOLDER)
            item = QListWidgetItem(placeholder_text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(Qt.GlobalColor.darkGray)
            self._list.addItem(item)

        self._update_btn_state()

    def retranslate(self):
        """Update button labels and title via tr()."""
        self._title.setText(self._title_text())

        sel_key = tr("paths.make_selection")
        self._btn_sel.setText(sel_key if sel_key != "paths.make_selection"
                               else "Make Selection")

        fill_key = tr("paths.fill")
        self._btn_fill.setText(fill_key if fill_key != "paths.fill"
                                else "Fill Path")

        stroke_key = tr("paths.stroke")
        self._btn_stroke.setText(stroke_key if stroke_key != "paths.stroke"
                                  else "Stroke Path")

        del_key = tr("paths.delete")
        self._btn_delete.setText(del_key if del_key != "paths.delete"
                                  else "Delete Path")

    # ----------------------------------------------------------------- private

    def _title_text(self) -> str:
        val = tr("panel.paths")
        return val if val != "panel.paths" else "Paths"

    def _selected_is_work_path(self) -> bool:
        item = self._list.currentItem()
        if item is None:
            return False
        return item.data(Qt.ItemDataRole.UserRole) == "work"

    def _update_btn_state(self):
        enabled = self._has_work_path and self._selected_is_work_path()
        for btn in (self._btn_sel, self._btn_fill, self._btn_stroke, self._btn_delete):
            btn.setEnabled(enabled)

    def _on_make_selection(self):
        if self._selected_is_work_path():
            self.make_selection_requested.emit()

    def _on_fill(self):
        if self._selected_is_work_path():
            self.fill_path_requested.emit()

    def _on_stroke(self):
        if self._selected_is_work_path():
            self.stroke_path_requested.emit()

    def _on_delete(self):
        if self._selected_is_work_path():
            self.delete_path_requested.emit()
            # Optimistically clear the list
            self._has_work_path = False
            self._list.clear()
            placeholder_text = (tr("paths.no_paths")
                                 if tr("paths.no_paths") != "paths.no_paths"
                                 else _NO_PATHS_PLACEHOLDER)
            item = QListWidgetItem(placeholder_text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(Qt.GlobalColor.darkGray)
            self._list.addItem(item)
            self._update_btn_state()
