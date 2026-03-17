from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QListWidget,
                             QListWidgetItem)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from core.locale import tr

ITEM_STYLE = ("QListWidget{background:#1e1e2e;border:none;color:#cdd6f4;}"
              "QListWidget::item{padding:4px 8px;}"
              "QListWidget::item:selected{background:#313244;color:#cba6f7;}"
              "QListWidget::item:hover{background:#282838;}")
LABEL_STYLE = "color:#a6adc8;font-size:11px;"


class HistoryPanel(QWidget):
    """
    Shows undo/redo history from the canvas's HistoryManager.

    Layout (top → bottom in the list):
      oldest undo state
      ...
      newest undo state
      ★ Current  (bold, accent color, non-selectable sentinel)
      newest redo state  (greyed out)
      ...
      oldest redo state  (greyed out)

    Signal jump_requested(int):
      positive N → undo N times
      negative N → redo N times (i.e. abs(N) redo steps)
    """

    jump_requested = pyqtSignal(int)

    # sentinel row role value to identify the "current" item
    _ROLE_KIND = Qt.ItemDataRole.UserRole          # "undo" | "current" | "redo"
    _ROLE_IDX  = Qt.ItemDataRole.UserRole + 1      # index within its stack

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._title = QLabel(tr("panel.history", **{}) if tr("panel.history") != "panel.history"
                             else "History")
        self._title.setObjectName("panelTitle")
        layout.addWidget(self._title)

        self._list = QListWidget()
        self._list.setStyleSheet(ITEM_STYLE)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list, 1)

        self._canvas = None
        self._current_row = 0   # row index of the "★ Current" sentinel

    # ----------------------------------------------------------------- public

    def refresh(self, canvas):
        """Rebuild list from canvas.history."""
        self._canvas = canvas
        self._list.blockSignals(True)
        self._list.clear()

        history = canvas.history
        undo_stack = history._undo_stack   # oldest … newest
        redo_stack = history._redo_stack   # newest … oldest (redo pops from end)

        # undo states — oldest first (index 0 … n-1)
        for idx, state in enumerate(undo_stack):
            item = QListWidgetItem(state.description)
            item.setData(self._ROLE_KIND, "undo")
            item.setData(self._ROLE_IDX, idx)
            item.setForeground(QColor("#cdd6f4"))
            self._list.addItem(item)

        # ★ Current sentinel
        current_label = self._current_text()
        cur_item = QListWidgetItem(current_label)
        cur_item.setData(self._ROLE_KIND, "current")
        cur_item.setData(self._ROLE_IDX, -1)
        font = QFont()
        font.setBold(True)
        cur_item.setFont(font)
        cur_item.setForeground(QColor("#cba6f7"))
        # Make it non-interactive as a selection target by setting flags
        cur_item.setFlags(cur_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self._list.addItem(cur_item)
        self._current_row = self._list.count() - 1

        # redo states — newest first (redo_stack[-1] is "next redo" action)
        # display newest redo at top (just below current), oldest at bottom
        for idx in range(len(redo_stack) - 1, -1, -1):
            state = redo_stack[idx]
            item = QListWidgetItem(state.description)
            item.setData(self._ROLE_KIND, "redo")
            item.setData(self._ROLE_IDX, idx)
            item.setForeground(QColor("#585b70"))
            self._list.addItem(item)

        # scroll so current item is visible
        self._list.scrollToItem(self._list.item(self._current_row),
                                QListWidget.ScrollHint.PositionAtCenter)
        self._list.blockSignals(False)

    def retranslate(self):
        """Update translatable strings."""
        # Update title
        title_text = tr("panel.history")
        self._title.setText(title_text if title_text != "panel.history" else "History")

        # Update "★ Current" item text if it exists
        if self._list.count() > self._current_row:
            item = self._list.item(self._current_row)
            if item and item.data(self._ROLE_KIND) == "current":
                item.setText(self._current_text())

    # ----------------------------------------------------------------- private

    def _current_text(self) -> str:
        key = "panel.history.current"
        val = tr(key)
        return val if val != key else "★ Current"

    def _on_item_clicked(self, item: QListWidgetItem):
        kind = item.data(self._ROLE_KIND)
        if kind == "current":
            return

        current_undo_idx = self._current_row  # row of the sentinel

        clicked_row = self._list.row(item)

        if kind == "undo":
            # clicked_row is within undo area (0 … current_undo_idx-1)
            # number of undo steps = (current_undo_idx - 1) - clicked_row + 1
            #   = current_undo_idx - clicked_row
            # That is: we want to end up AT clicked_row, so undo
            # (current_undo_idx - clicked_row) times.
            # Alternatively: each undo state at row r means we need to undo
            # back to BEFORE that state, i.e. undo (current_undo_idx - clicked_row) times
            steps = current_undo_idx - clicked_row
            if steps > 0:
                self.jump_requested.emit(steps)

        elif kind == "redo":
            # redo states start at current_undo_idx + 1
            # step 1 = row current_undo_idx+1 (newest redo at top)
            steps = clicked_row - current_undo_idx
            if steps > 0:
                # negative = redo N times
                self.jump_requested.emit(-steps)
