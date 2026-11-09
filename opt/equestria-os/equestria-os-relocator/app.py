import os

from PyQt6.QtWidgets import (
    QMainWindow, QHBoxLayout, QLineEdit, QPushButton,
    QFileDialog, QWidget, QComboBox
)
from PyQt6.QtGui import QFontDatabase, QFont, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ui_relocator import Ui_Relocator
import core, privilege
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit import live_i18n
from equestria_kit.widgets import font_families

# Переводы лежат в locales/<язык>.json рядом с программой (ключ -> текст)
CATALOG = live_i18n.Catalog("equestria-os-relocator", __file__)




class RelocateWorker(QThread):
    finished = pyqtSignal(list)               # list of RelocateResult
    elevated_finished = pyqtSignal(bool, str) # success, error
    progress = pyqtSignal(int, int)           # current, total

    def __init__(self, sources, destination, elevated=False, elevator=None):
        super().__init__()
        self._sources = sources
        self._destination = destination
        self._elevated = elevated
        self._elevator = elevator

    def run(self):
        if self._elevated:
            proc = privilege.start_elevated(self._elevator, self._sources, self._destination)
            total = len(self._sources)
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("PROGRESS"):
                    _, cur, tot = line.split()
                    self.progress.emit(int(cur), int(tot))
                elif line.startswith("OK"):
                    pass
            proc.wait()
            if proc.returncode == 0:
                self.elevated_finished.emit(True, "")
            else:
                self.elevated_finished.emit(False, proc.stderr.read().strip())
        else:
            total = len(self._sources)
            results = []
            for i, src in enumerate(self._sources, 1):
                r = core.relocate([src], self._destination, create_symlink=True)
                results.extend(r)
                self.progress.emit(i, total)
            self.finished.emit(results)


class RelocatorApp(QMainWindow, Ui_Relocator):
    def __init__(self, initial_sources=None):
        super().__init__()
        self.setupUi(self)

        self._source_rows = []  # list of (container, line_edit, remove_btn, file_btn, folder_btn)

        # Language detection
        self.current_lang = CATALOG.lang or "en"

        base_path = os.path.dirname(os.path.abspath(__file__))

        # Load custom font
        font_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        if os.path.exists(font_path):
            families = font_families(font_path)
            if families:
                self.app_title.setFont(QFont(families[0], 22, QFont.Weight.Bold))

        # Load stylesheet
        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            kit_qt.style(self, open(qss_path).read())

        # Load window icon
        icon_path = os.path.join(base_path, "equestria-os-relocator.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Компактный выпадающий список языков вместо ряда кнопок
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        # языки — найденные файлы locales/*.json, названия — из них же (_language_name)
        for code in CATALOG.languages:
            self.lang_combo.addItem(CATALOG.language_name(code), code)
        idx = self.lang_combo.findData(self.current_lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        # activated срабатывает только при выборе пользователем — без рекурсии
        self.lang_combo.activated.connect(
            lambda i: self._change_lang(self.lang_combo.itemData(i)))
        self.lang_row.addWidget(self.lang_combo)

        # Create initial source rows
        sources = initial_sources or []
        if sources:
            for path in sources:
                self._add_source_row(path)
        else:
            self._add_source_row()

        # Connect signals
        self.add_source_btn.clicked.connect(lambda: self._add_source_row())
        self.dest_browse_btn.clicked.connect(self._browse_destination)
        self.relocate_btn.clicked.connect(self._on_relocate_clicked)
        self.dest_edit.textChanged.connect(self._check_ntfs_warning)

        self._refresh_ui()

    # -------------------------------------------------------------------------
    # Localisation
    # -------------------------------------------------------------------------

    def t(self, key):
        return str(CATALOG.tr(key))

    def _change_lang(self, lang):
        self.current_lang = CATALOG.set_language(lang) or lang  # ещё и сохраняет выбор
        idx = self.lang_combo.findData(lang)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
        self._refresh_ui()

    def _refresh_ui(self):
        self.setWindowTitle(self.t("title"))
        self.app_title.setText(self.t("title"))
        self.sources_label.setText(self.t("sources"))
        self.dest_label.setText(self.t("destination"))
        self.add_source_btn.setText(self.t("add_source"))
        self.dest_browse_btn.setText(self.t("browse"))
        self.relocate_btn.setText(self.t("relocate"))
        self.dest_edit.setPlaceholderText(self.t("ph_dest"))
        self.ntfs_warning.setText(self.t("ntfs_warn"))

        # Update existing source rows
        for _, le, _, file_btn, folder_btn in self._source_rows:
            le.setPlaceholderText(self.t("ph_source"))
            file_btn.setText(self.t("browse_file"))
            folder_btn.setText(self.t("browse_folder"))

    # -------------------------------------------------------------------------
    # Source row management
    # -------------------------------------------------------------------------

    def _add_source_row(self, path=""):
        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        line_edit = QLineEdit(path)
        line_edit.setObjectName("SourceEdit")
        line_edit.setPlaceholderText(self.t("ph_source"))
        line_edit.textChanged.connect(self._check_ntfs_warning)

        file_btn = QPushButton(self.t("browse_file"))
        file_btn.setObjectName("BrowseBtn")
        file_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        folder_btn = QPushButton(self.t("browse_folder"))
        folder_btn.setObjectName("BrowseBtn")
        folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        remove_btn = QPushButton("✕")
        remove_btn.setObjectName("RemoveBtn")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        row_layout.addWidget(line_edit, 1)
        row_layout.addWidget(file_btn)
        row_layout.addWidget(folder_btn)
        row_layout.addWidget(remove_btn)

        entry = (container, line_edit, remove_btn, file_btn, folder_btn)
        self._source_rows.append(entry)
        self.source_rows_layout.addWidget(container)

        file_btn.clicked.connect(lambda: self._browse_source_file(entry))
        folder_btn.clicked.connect(lambda: self._browse_source_folder(entry))
        remove_btn.clicked.connect(lambda: self._remove_source_row(entry))

        self._update_remove_buttons()

    def _remove_source_row(self, entry):
        if len(self._source_rows) <= 1:
            return
        container, _, _, _, _ = entry
        self._source_rows.remove(entry)
        container.deleteLater()
        self._update_remove_buttons()
        self._check_ntfs_warning()

    def _update_remove_buttons(self):
        only_one = len(self._source_rows) == 1
        for _, _, remove_btn, _, _ in self._source_rows:
            remove_btn.setVisible(not only_one)

    # -------------------------------------------------------------------------
    # Browse dialogs
    # -------------------------------------------------------------------------

    def _browse_source_file(self, entry):
        _, line_edit, _, _, _ = entry
        path, _ = QFileDialog.getOpenFileName(self, self.t("dlg_file"))
        if path:
            line_edit.setText(path)

    def _browse_source_folder(self, entry):
        _, line_edit, _, _, _ = entry
        path = QFileDialog.getExistingDirectory(self, self.t("dlg_folder"))
        if path:
            line_edit.setText(path)

    def _browse_destination(self):
        path = QFileDialog.getExistingDirectory(self, self.t("dlg_dest"))
        if path:
            self.dest_edit.setText(path)

    # -------------------------------------------------------------------------
    # NTFS warning
    # -------------------------------------------------------------------------

    def _check_ntfs_warning(self):
        paths = [le.text() for _, le, _, _, _ in self._source_rows if le.text()]
        dest = self.dest_edit.text()
        if dest:
            paths.append(dest)

        if any(core.detect_ntfs(p) for p in paths):
            self.ntfs_warning.show()
        else:
            self.ntfs_warning.hide()

    # -------------------------------------------------------------------------
    # Validation and status
    # -------------------------------------------------------------------------

    def _validate_inputs(self) -> bool:
        sources = [le.text().strip() for _, le, _, _, _ in self._source_rows]
        if not any(sources):
            self._set_status(self.t("err_no_source"), is_error=True)
            return False
        if not self.dest_edit.text().strip():
            self._set_status(self.t("err_no_dest"), is_error=True)
            return False
        return True

    def _set_status(self, msg: str, is_error: bool = False):
        self.status_label.setText(msg)
        self.status_label.setProperty("status", "error" if is_error else "ok")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    # -------------------------------------------------------------------------
    # Relocate flow
    # -------------------------------------------------------------------------

    def _on_relocate_clicked(self):
        if not self._validate_inputs():
            return

        sources = [le.text().strip() for _, le, _, _, _ in self._source_rows if le.text().strip()]
        destination = self.dest_edit.text().strip()

        self.relocate_btn.setEnabled(False)
        self._set_status(self.t("working"))

        if privilege.needs_elevation(sources + [destination]):
            elevator = privilege.find_elevator()
            if not elevator:
                self._set_status(self.t("err_no_elevator"), is_error=True)
                self.relocate_btn.setEnabled(True)
                return
            self._worker = RelocateWorker(sources, destination, elevated=True, elevator=elevator)
            self._worker.elevated_finished.connect(self._on_elevated_done)
        else:
            self._worker = RelocateWorker(sources, destination)
            self._worker.finished.connect(self._on_done)

        self._worker.progress.connect(self._on_progress)
        self._worker.start()

    def _on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{current} / {total}  ({int(current / total * 100)}%)")
        self.progress_bar.show()

    def _on_done(self, results):
        self.progress_bar.hide()
        errors = [r for r in results if r.error]
        if errors:
            self._set_status("\n".join(f"• {r.source}: {r.error}" for r in errors), is_error=True)
        else:
            moved = len(results)
            symlinks = sum(1 for r in results if r.symlink_created)
            dest = self.dest_edit.text().strip()
            self._set_status(self.t("success").format(n=moved, dest=dest, s=symlinks))
        self.relocate_btn.setEnabled(True)

    def _on_elevated_done(self, success, err):
        self.progress_bar.hide()
        if success:
            sources = [le.text().strip() for _, le, _, _, _ in self._source_rows if le.text().strip()]
            dest = self.dest_edit.text().strip()
            self._set_status(self.t("success").format(n=len(sources), dest=dest, s=len(sources)))
        else:
            self._set_status(err or self.t("err_no_elevator"), is_error=True)
        self.relocate_btn.setEnabled(True)
