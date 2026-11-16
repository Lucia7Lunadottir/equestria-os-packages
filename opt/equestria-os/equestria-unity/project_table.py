"""The project table: a model with one row per project and a delegate that draws its cells.
No widgets per cell, so hundreds of projects stay fast to filter and redraw."""
from dataclasses import dataclass

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QHeaderView, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
                             QTreeView)

from formatting import short, when
from kit import qt, tr
from nav_icons import pixmap

STAR, NAME, GIT, VERSION, MODIFIED, MORE = range(6)
HEADERS = ("", "projects.col_name", "git.column", "projects.col_version", "projects.col_modified", "")
WIDTHS = {STAR: 48, GIT: 210, VERSION: 190, MODIFIED: 150, MORE: 60}
CLICKABLE = (STAR, NAME, GIT, VERSION, MORE)
ROW = Qt.ItemDataRole.UserRole
ROW_HEIGHT = 58


@dataclass
class ProjectRow:
    project: object
    starred: bool
    installed: bool      # its Editor version is installed
    last: float          # last opened or modified, whichever is later

    @property
    def missing(self):
        return bool(self.project.version) and not self.installed


def git_marks(status):
    """Small marks after the branch: ●3 changed files, ↑2 commits to send, ↓1 commits to receive."""
    if status is None:
        return []
    marks = []
    if status.changes:
        marks.append((f"●{len(status.changes)}", "yellow"))
    if status.ahead:
        marks.append((f"↑{status.ahead}", "accent"))
    if status.behind:
        marks.append((f"↓{status.behind}", "green"))
    return marks


class ProjectTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        column = index.column()
        if role == ROW:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            git = row.project.git
            return {NAME: row.project.name, GIT: git.branch if git else "", VERSION: row.project.version or "—",
                    MODIFIED: str(when(row.last))}.get(column, "")
        if role == Qt.ItemDataRole.ToolTipRole and column == NAME:
            return str(row.project.path)
        if role == Qt.ItemDataRole.ToolTipRole and column == GIT and row.project.git:
            git = row.project.git
            place = git.web or git.remote or str(git.root)
            status = git.status
            if status is None:
                return place
            lines = [place, str(tr("git.state_changed", len(status.changes)) if status.changes
                                else tr("git.state_clean"))]
            if status.ahead:
                lines.append(str(tr("git.state_ahead", status.ahead)))
            if status.behind:
                lines.append(str(tr("git.state_behind", status.behind)))
            return "\n".join(lines)
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(10, ROW_HEIGHT)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            key = HEADERS[section]
            return str(tr(key)) if key else ""
        return None


class ProjectDelegate(QStyledItemDelegate):
    """The row background comes from the style sheet (hover, selection, divider); the cells are drawn here."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index):
        return QSize(10, ROW_HEIGHT)

    def paint(self, painter, option, index):
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.text = ""
        widget = option.widget
        (widget.style() if widget else QApplication.style()).drawControl(
            QStyle.ControlElement.CE_ItemViewItem, background, painter, widget)
        row = index.data(ROW)
        if row is None:
            return
        hovered = self.view.hovered == (index.row(), index.column())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        column = index.column()
        if column == STAR:
            self.text(painter, rect, "★" if row.starred else "☆", 18, False,
                      "accent" if row.starred or hovered else "surface2", Qt.AlignmentFlag.AlignCenter)
        elif column == NAME:
            top = QRect(rect.left() + 8, rect.top() + 9, rect.width() - 16, 22)
            if row.missing:
                warn = self.text(painter, top, "⚠", 14, True, "yellow", Qt.AlignmentFlag.AlignLeft)
                top.setLeft(top.left() + warn + 8)
            self.text(painter, top, row.project.name, 14, True, "text", Qt.AlignmentFlag.AlignLeft)
            bottom = QRect(rect.left() + 8, rect.top() + 31, rect.width() - 16, 20)
            self.text(painter, bottom, short(row.project.path), 13, False, "subtext", Qt.AlignmentFlag.AlignLeft)
        elif column == GIT:
            git = row.project.git
            cell = QRect(rect.left() + 2, rect.center().y() - 15, rect.width() - 10, 30)
            if hovered:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qt.theme_color("surface1"))
                painter.drawRoundedRect(cell, 7, 7)
            if git:
                icon = pixmap("branch", qt.theme_color("accent" if hovered else "subtext").name(), 16)
                painter.drawPixmap(cell.left() + 8, cell.center().y() - 8, icon)
                right = cell.right() - 6
                for text, role in reversed(git_marks(git.status)):   # drawn from the right edge
                    width = self.width(text, 12, True) + 4   # symbols like ● may come from a wider fallback font
                    self.text(painter, QRect(right - width, cell.top(), width, cell.height()), text, 12, True, role,
                              Qt.AlignmentFlag.AlignLeft)
                    right -= width + 6
                self.text(painter, QRect(cell.left() + 30, cell.top(), right - cell.left() - 30, cell.height()),
                          git.branch, 13, False, "text", Qt.AlignmentFlag.AlignLeft)
            else:
                self.text(painter, cell.adjusted(9, 0, -6, 0), "—", 13, False, "surface2", Qt.AlignmentFlag.AlignLeft)
        elif column == VERSION:
            label = ("⚠ " if row.missing else "") + (row.project.version or "—") + "   ⇅"
            pill = QRect(rect.left() + 2, rect.center().y() - 15, min(rect.width() - 8, self.width(label, 14) + 40), 30)
            if hovered:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qt.theme_color("surface1"))
                painter.drawRoundedRect(pill, 7, 7)
            self.text(painter, pill.adjusted(9, 0, -9, 0), label, 14, False, "yellow" if row.missing else "text",
                      Qt.AlignmentFlag.AlignLeft)
        elif column == MODIFIED:
            self.text(painter, rect.adjusted(4, 0, -4, 0), str(when(row.last)), 13, False, "subtext",
                      Qt.AlignmentFlag.AlignLeft)
        elif column == MORE:
            button = QRect(rect.center().x() - 18, rect.center().y() - 15, 36, 30)
            if hovered:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qt.theme_color("surface0"))
                painter.drawRoundedRect(button, 8, 8)
            self.text(painter, button, "⋯", 16, True, "text" if hovered else "subtext", Qt.AlignmentFlag.AlignCenter)
        painter.restore()

    def font(self, size, bold):
        font = QFont(self.view.font())
        font.setPixelSize(size)
        font.setBold(bold)
        return font

    def width(self, text, size, bold=False):
        return QFontMetrics(self.font(size, bold)).horizontalAdvance(text)

    def text(self, painter, rect, text, size, bold, role, align):
        """Draw one line, elided to the rectangle. Returns the width it took."""
        font = self.font(size, bold)
        painter.setFont(font)
        painter.setPen(qt.theme_color(role))
        metrics = painter.fontMetrics()
        shown = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, rect.width())
        painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, shown)
        return metrics.horizontalAdvance(shown)


class ProjectTable(QTreeView):
    """Clicks are turned into requests for the page: the star, the name, the version and the ⋯ cell act like buttons."""
    star_clicked = pyqtSignal(object)            # project
    open_requested = pyqtSignal(object)          # project
    git_requested = pyqtSignal(object, object)   # project, global point under the cell
    version_requested = pyqtSignal(object, object)   # project, global point under the cell
    menu_requested = pyqtSignal(object, object)      # project, global point

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("table")
        self.hovered = None
        self.setModel(ProjectTableModel(self))
        self.setItemDelegate(ProjectDelegate(self))
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.context)
        self.clicked.connect(self.cell_clicked)
        self.doubleClicked.connect(self.cell_double_clicked)
        self.model().modelReset.connect(self.setup_header)
        self.header().setSectionsClickable(True)
        self.setup_header()

    def setup_header(self):
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        for column, width in WIDTHS.items():
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(column, width)

    def rows(self):
        return self.model().rows

    def show_rows(self, rows, keep=None):
        """Replace the rows; the project at path `keep` stays selected."""
        self.model().set_rows(rows)
        for number, row in enumerate(rows):
            if keep is not None and row.project.path == keep:
                self.setCurrentIndex(self.model().index(number, NAME))
                break

    def project_at(self, index):
        row = index.data(ROW) if index.isValid() else None
        return row.project if row else None

    def current_project(self):
        return self.project_at(self.currentIndex())

    def cell_point(self, index):
        rect = self.visualRect(index)
        return self.viewport().mapToGlobal(rect.bottomLeft())

    def cell_clicked(self, index):
        project = self.project_at(index)
        if project is None:
            return
        column = index.column()
        if column == STAR:
            self.star_clicked.emit(project)
        elif column == NAME:
            self.open_requested.emit(project)
        elif column == GIT:
            self.git_requested.emit(project, self.cell_point(index))
        elif column == VERSION:
            self.version_requested.emit(project, self.cell_point(index))
        elif column == MORE:
            self.menu_requested.emit(project, self.cell_point(index))

    def cell_double_clicked(self, index):
        if index.column() not in CLICKABLE:  # those already acted on the first click
            project = self.project_at(index)
            if project is not None:
                self.open_requested.emit(project)

    def context(self, position):
        index = self.indexAt(position)
        project = self.project_at(index)
        if project is not None:
            self.setCurrentIndex(index)
            self.menu_requested.emit(project, self.viewport().mapToGlobal(position))

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        hovered = (index.row(), index.column()) if index.isValid() else None
        if hovered != self.hovered:
            self.hovered = hovered
            self.viewport().update()
        clickable = index.isValid() and index.column() in CLICKABLE
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered = None
        self.viewport().update()
        super().leaveEvent(event)
