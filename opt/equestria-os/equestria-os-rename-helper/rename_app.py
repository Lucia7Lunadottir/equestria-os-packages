import sys
import os
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QMessageBox,
    QProgressBar, QFileDialog, QListWidget, QListWidgetItem, QSpinBox,
    QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase

# Используем твои наработки
import privilege
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit.i18n import detect_language
from equestria_kit.widgets import font_families

LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "zh_TW", "ja", "ko"]
STRINGS = {
    "title":      {"en": "Equestria OS: Bulk Renamer", "ru": "Equestria OS: Массовое переименование", "de": "Equestria OS: Massen-Umbenennung", "fr": "Equestria OS : renommage en masse", "es": "Equestria OS: renombrado masivo", "pt": "Equestria OS: renomeação em massa", "pl": "Equestria OS: masowa zmiana nazw", "uk": "Equestria OS: масове перейменування", "zh": "Equestria OS：批量重命名", "zh_TW": "Equestria OS：批次重新命名", "ja": "Equestria OS：一括リネーム", "ko": "Equestria OS: 일괄 이름 변경"},
    "dir_label":  {"en": "Target Directory",          "ru": "Целевая папка", "de": "Zielverzeichnis", "fr": "Dossier cible", "es": "Carpeta de destino", "pt": "Pasta de destino", "pl": "Katalog docelowy", "uk": "Цільова тека", "zh": "目标目录", "zh_TW": "目標目錄", "ja": "対象ディレクトリ", "ko": "대상 디렉터리"},
    "filter":     {"en": "Filter (only files containing)", "ru": "Фильтр (только файлы содержащие)", "de": "Filter (nur Dateien, die enthalten)", "fr": "Filtre (seulement les fichiers contenant)", "es": "Filtro (solo archivos que contengan)", "pt": "Filtro (apenas arquivos que contêm)", "pl": "Filtr (tylko pliki zawierające)", "uk": "Фільтр (лише файли, що містять)", "zh": "筛选（仅包含该文本的文件）", "zh_TW": "篩選（僅包含該文本的檔案）", "ja": "フィルター（含むファイルのみ）", "ko": "필터 (이 텍스트를 포함하는 파일만)"},
    "find":       {"en": "Find text",                 "ru": "Найти текст", "de": "Text suchen", "fr": "Texte à rechercher", "es": "Texto a buscar", "pt": "Texto a procurar", "pl": "Szukany tekst", "uk": "Знайти текст", "zh": "查找文本", "zh_TW": "查詢文本", "ja": "検索する文字列", "ko": "찾을 텍스트"},
    "replace":    {"en": "Replace with",              "ru": "Заменить на", "de": "Ersetzen durch", "fr": "Remplacer par", "es": "Reemplazar por", "pt": "Substituir por", "pl": "Zamień na", "uk": "Замінити на", "zh": "替换为", "zh_TW": "替換為", "ja": "置換後", "ko": "바꿀 내용"},
    "prefix":     {"en": "Add Prefix",                "ru": "Добавить префикс", "de": "Präfix hinzufügen", "fr": "Ajouter un préfixe", "es": "Añadir prefijo", "pt": "Adicionar prefixo", "pl": "Dodaj przedrostek", "uk": "Додати префікс", "zh": "添加前缀", "zh_TW": "新增字首", "ja": "接頭辞を追加", "ko": "접두사 추가"},
    "suffix":     {"en": "Add Suffix",                "ru": "Добавить суффикс", "de": "Suffix hinzufügen", "fr": "Ajouter un suffixe", "es": "Añadir sufijo", "pt": "Adicionar sufixo", "pl": "Dodaj przyrostek", "uk": "Додати суфікс", "zh": "添加后缀", "zh_TW": "新增字尾", "ja": "接尾辞を追加", "ko": "접미사 추가"},
    "numbers":    {"en": "Numbering (Start at)",      "ru": "Нумерация (начиная с)", "de": "Nummerierung (Start bei)", "fr": "Numérotation (à partir de)", "es": "Numeración (empezar en)", "pt": "Numeração (começar em)", "pl": "Numeracja (od)", "uk": "Нумерація (почати з)", "zh": "编号（起始值）", "zh_TW": "編號（起始值）", "ja": "番号付け（開始番号）", "ko": "번호 매기기 (시작 번호)"},
    "preview":    {"en": "Preview",                   "ru": "Предпросмотр", "de": "Vorschau", "fr": "Aperçu", "es": "Vista previa", "pt": "Pré-visualizar", "pl": "Podgląd", "uk": "Попередній перегляд", "zh": "预览", "zh_TW": "預覽", "ja": "プレビュー", "ko": "미리 보기"},
    "apply":      {"en": "Rename All",                "ru": "Переименовать всё", "de": "Alle umbenennen", "fr": "Tout renommer", "es": "Renombrar todo", "pt": "Renomear tudo", "pl": "Zmień nazwy wszystkich", "uk": "Перейменувати все", "zh": "全部重命名", "zh_TW": "全部重新命名", "ja": "すべてリネーム", "ko": "모두 이름 바꾸기"},
    "browse":     {"en": "Browse",                    "ru": "Обзор", "de": "Durchsuchen", "fr": "Parcourir", "es": "Examinar", "pt": "Procurar", "pl": "Przeglądaj", "uk": "Огляд", "zh": "浏览", "zh_TW": "瀏覽", "ja": "参照", "ko": "찾아보기"},
    "success":    {"en": "Successfully renamed {n} files!", "ru": "Успешно переименовано {n} файлов!", "de": "{n} Dateien erfolgreich umbenannt!", "fr": "{n} fichiers renommés avec succès !", "es": "¡Se renombraron {n} archivos correctamente!", "pt": "{n} arquivos renomeados com sucesso!", "pl": "Pomyślnie zmieniono nazwy {n} plików!", "uk": "Успішно перейменовано файлів: {n}!", "zh": "已成功重命名 {n} 个文件！", "zh_TW": "已成功重新命名 {n} 個檔案！", "ja": "{n} 個のファイルをリネームしました！", "ko": "파일 {n}개의 이름을 바꿨습니다!"},
    "undo":       {"en": "Undo",                      "ru": "Отменить", "de": "Rückgängig", "fr": "Annuler", "es": "Deshacer", "pt": "Desfazer", "pl": "Cofnij", "uk": "Скасувати", "zh": "撤销", "zh_TW": "撤銷", "ja": "元に戻す", "ko": "실행 취소"},
    "history":    {"en": "History",                   "ru": "История", "de": "Verlauf", "fr": "Historique", "es": "Historial", "pt": "Histórico", "pl": "Historia", "uk": "Історія", "zh": "历史", "zh_TW": "歷史", "ja": "履歴", "ko": "기록"},
    "undo_ok":    {"en": "Reverted {n} files.",       "ru": "Отменено {n} файлов.", "de": "{n} Dateien zurückgesetzt.", "fr": "{n} fichiers restaurés.", "es": "Se revirtieron {n} archivos.", "pt": "{n} arquivos revertidos.", "pl": "Przywrócono {n} plików.", "uk": "Відновлено файлів: {n}.", "zh": "已还原 {n} 个文件。", "zh_TW": "已還原 {n} 個檔案。", "ja": "{n} 個のファイルを元に戻しました。", "ko": "파일 {n}개를 되돌렸습니다."},
    "undo_empty": {"en": "Nothing to undo.",          "ru": "Нечего отменять.", "de": "Nichts rückgängig zu machen.", "fr": "Rien à annuler.", "es": "Nada que deshacer.", "pt": "Nada para desfazer.", "pl": "Nie ma czego cofać.", "uk": "Нічого скасовувати.", "zh": "没有可撤销的操作。", "zh_TW": "沒有可撤銷的操作。", "ja": "元に戻す操作はありません。", "ko": "되돌릴 작업이 없습니다."},
    "hist_title": {"en": "Rename History",            "ru": "История переименований", "de": "Umbenennungsverlauf", "fr": "Historique des renommages", "es": "Historial de renombrados", "pt": "Histórico de renomeações", "pl": "Historia zmian nazw", "uk": "Історія перейменувань", "zh": "重命名历史", "zh_TW": "重新命名歷史", "ja": "リネーム履歴", "ko": "이름 변경 기록"},
    "hist_empty": {"en": "History is empty.",         "ru": "История пуста.", "de": "Der Verlauf ist leer.", "fr": "L'historique est vide.", "es": "El historial está vacío.", "pt": "O histórico está vazio.", "pl": "Historia jest pusta.", "uk": "Історія порожня.", "zh": "历史为空。", "zh_TW": "歷史為空。", "ja": "履歴は空です。", "ko": "기록이 비어 있습니다."},
}


class HistoryDialog(QDialog):
    """Диалог просмотра и выборочной отмены истории переименований."""

    def __init__(self, history, lang, parent=None):
        super().__init__(parent)
        self.history = history  # list of (batch_label, [(new, old), ...])
        self.lang = lang
        self._selected_idx = None
        self._setup_ui()

    def t(self, key):
        return STRINGS.get(key, {}).get(self.lang, STRINGS[key]["en"])

    def _setup_ui(self):
        self.setWindowTitle(self.t("hist_title"))
        self.resize(600, 400)
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        if not self.history:
            self.list_widget.addItem(self.t("hist_empty"))
        else:
            for i, (label, _) in enumerate(reversed(self.history)):
                self.list_widget.addItem(f"{len(self.history) - i}. {label}")
        self.list_widget.currentRowChanged.connect(self._on_select)
        layout.addWidget(self.list_widget)

        self.detail_list = QListWidget()
        layout.addWidget(self.detail_list)

        btns = QDialogButtonBox()
        self.btn_undo_sel = btns.addButton(self.t("undo"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_undo_sel.setEnabled(False)
        btns.addButton(QDialogButtonBox.StandardButton.Close)
        btns.accepted.connect(self._undo_selected)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_select(self, row):
        self.detail_list.clear()
        if not self.history or row < 0:
            self.btn_undo_sel.setEnabled(False)
            return
        # список отображается в обратном порядке
        real_idx = len(self.history) - 1 - row
        _, pairs = self.history[real_idx]
        for new_path, old_path in pairs:
            self.detail_list.addItem(
                f"{os.path.basename(new_path)}  →  {os.path.basename(old_path)}"
            )
        self._selected_idx = real_idx
        self.btn_undo_sel.setEnabled(True)

    def _undo_selected(self):
        if self._selected_idx is None:
            return
        self.selected_batch_idx = self._selected_idx
        self.accept()


class RenamerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = detect_language()
        if self.current_lang not in LANGS:
            self.current_lang = "en"

        self.files_map = []  # [(старый_путь, новый_путь), ...]
        # История: список (метка, [(новый_путь, старый_путь), ...])
        # Хранится как стек — последняя операция в конце
        self.rename_history = []
        self._setup_ui()

    def t(self, key):
        return STRINGS.get(key, {}).get(self.current_lang, STRINGS[key]["en"])

    def _setup_ui(self):
        self.setWindowTitle(self.t("title"))
        self.resize(700, 850)

        base_path = os.path.dirname(os.path.abspath(__file__))
        title_font = "sans-serif"
        f_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            families = font_families(f_path)
            if families:
                title_font = families[0]

        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            qss = open(qss_path).read().replace("{{TITLE_FONT}}", f'"{title_font}"')
            qss += "\nQListWidget { background-color: @base@; border: 1px solid @surface0@; border-radius: 8px; padding: 5px; }"
            kit_qt.style(self, qss)

        central = QWidget()
        central.setObjectName("CentralBg")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(15)

        # Заголовок
        self.lbl_title = QLabel(self.t("title"))
        self.lbl_title.setObjectName("AppTitle")
        layout.addWidget(self.lbl_title)

        # Выбор папки
        dir_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("DestEdit")
        self.path_edit.setPlaceholderText(self.t("dir_label"))
        self.btn_browse = QPushButton(self.t("browse"))
        self.btn_browse.setObjectName("BrowseBtn")
        self.btn_browse.clicked.connect(self._select_dir)
        dir_row.addWidget(self.path_edit)
        dir_row.addWidget(self.btn_browse)
        layout.addLayout(dir_row)

        # Панель настроек
        opts_frame = QFrame()
        opts_frame.setObjectName("ProgressFrame")
        opts_layout = QVBoxLayout(opts_frame)
        opts_layout.setSpacing(10)

        # Фильтр файлов
        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText(self.t("filter"))
        self.edit_filter.textChanged.connect(self._update_preview)
        opts_layout.addWidget(self.edit_filter)

        # Найти и заменить
        self.edit_find = QLineEdit()
        self.edit_find.setPlaceholderText(self.t("find"))
        self.edit_replace = QLineEdit()
        self.edit_replace.setPlaceholderText(self.t("replace"))
        opts_layout.addWidget(self.edit_find)
        opts_layout.addWidget(self.edit_replace)

        # Префикс и Суффикс
        pre_suf_row = QHBoxLayout()
        self.edit_prefix = QLineEdit()
        self.edit_prefix.setPlaceholderText(self.t("prefix"))
        self.edit_suffix = QLineEdit()
        self.edit_suffix.setPlaceholderText(self.t("suffix"))
        pre_suf_row.addWidget(self.edit_prefix)
        pre_suf_row.addWidget(self.edit_suffix)
        opts_layout.addLayout(pre_suf_row)

        # Нумерация
        num_row = QHBoxLayout()
        num_row.addWidget(QLabel(self.t("numbers")))
        self.num_spin = QSpinBox()
        self.num_spin.setRange(0, 9999)
        self.num_spin.setValue(0)
        self.num_spin.setObjectName("SourceEdit")
        num_row.addWidget(self.num_spin)
        num_row.addStretch()
        opts_layout.addLayout(num_row)

        layout.addWidget(opts_frame)

        # Предпросмотр
        layout.addWidget(QLabel(self.t("preview") + ":"))
        self.list_preview = QListWidget()
        layout.addWidget(self.list_preview)

        # Кнопки действий
        btn_row = QHBoxLayout()
        self.btn_preview = QPushButton(self.t("preview"))
        self.btn_preview.setObjectName("BrowseBtn")
        self.btn_preview.clicked.connect(self._update_preview)

        self.btn_apply = QPushButton(self.t("apply"))
        self.btn_apply.setObjectName("RelocateBtn")
        self.btn_apply.clicked.connect(self._do_rename)

        self.btn_undo = QPushButton(self.t("undo"))
        self.btn_undo.setObjectName("BrowseBtn")
        self.btn_undo.clicked.connect(self._do_undo)
        self.btn_undo.setEnabled(False)

        self.btn_history = QPushButton(self.t("history"))
        self.btn_history.setObjectName("BrowseBtn")
        self.btn_history.clicked.connect(self._show_history)

        btn_row.addWidget(self.btn_preview)
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_undo)
        btn_row.addWidget(self.btn_history)
        layout.addLayout(btn_row)

    def _select_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            self.path_edit.setText(path)
            self._update_preview()

    def _get_new_name(self, old_name, index):
        find_txt = self.edit_find.text()
        replace_txt = self.edit_replace.text()
        prefix = self.edit_prefix.text()
        suffix = self.edit_suffix.text()
        start_num = self.num_spin.value()

        name, ext = os.path.splitext(old_name)

        if find_txt:
            name = name.replace(find_txt, replace_txt)

        name = f"{prefix}{name}{suffix}"

        if start_num > 0 or self.num_spin.value() > 0:
            name = f"{name}_{start_num + index:03d}"

        return name + ext

    def _update_preview(self):
        self.list_preview.clear()
        dir_path = self.path_edit.text()
        if not os.path.isdir(dir_path):
            return

        self.files_map = []
        try:
            all_items = sorted(os.listdir(dir_path))
        except Exception:
            return

        filter_txt = self.edit_filter.text()
        seen_destinations = set()
        idx = 0
        for item_name in all_items:
            full_path = os.path.join(dir_path, item_name)
            if not os.path.isfile(full_path):
                continue
            if filter_txt and filter_txt not in item_name:
                continue

            new_name = self._get_new_name(item_name, idx)
            dest_path = os.path.join(dir_path, new_name)

            display_text = f"{item_name}  →  {new_name}"
            list_item = QListWidgetItem(display_text)

            if item_name != new_name:
                if dest_path in seen_destinations or (os.path.exists(dest_path) and dest_path != full_path):
                    list_item.setForeground(Qt.GlobalColor.red)
                    list_item.setText(display_text + "  ⚠ конфликт!")
                else:
                    list_item.setForeground(Qt.GlobalColor.green)

            seen_destinations.add(dest_path)
            self.list_preview.addItem(list_item)
            self.files_map.append((full_path, dest_path))
            idx += 1

    def _do_rename(self):
        if not self.files_map:
            return

        changes = [pair for pair in self.files_map if pair[0] != pair[1]]
        if not changes:
            return

        new_paths = [new for _, new in changes]
        if len(new_paths) != len(set(new_paths)):
            QMessageBox.critical(self, "Error", "Конфликт: несколько файлов получат одинаковое имя. Переименование отменено.")
            return
        for _, new in changes:
            if os.path.exists(new) and new not in [old for old, _ in changes]:
                QMessageBox.critical(self, "Error", f"Файл уже существует: {os.path.basename(new)}. Переименование отменено.")
                return

        done = []  # [(new_path, old_path)] для истории
        for old, new in changes:
            try:
                os.rename(old, new)
                done.append((new, old))
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not rename {os.path.basename(old)}: {e}")

        if done:
            # Метка батча: первые 3 файла
            sample = ", ".join(os.path.basename(n) for n, _ in done[:3])
            if len(done) > 3:
                sample += f" и ещё {len(done) - 3}"
            self.rename_history.append((f"{len(done)} файл(ов): {sample}", done))
            self.btn_undo.setEnabled(True)

        QMessageBox.information(self, "Success", self.t("success").format(n=len(done)))
        self._update_preview()

    def _do_undo(self):
        """Отменить последний батч переименований."""
        if not self.rename_history:
            QMessageBox.information(self, self.t("undo"), self.t("undo_empty"))
            self.btn_undo.setEnabled(False)
            return

        self._apply_undo_batch(len(self.rename_history) - 1)

    def _apply_undo_batch(self, idx):
        label, pairs = self.rename_history[idx]
        errors = []
        count = 0
        for new_path, old_path in pairs:
            if not os.path.exists(new_path):
                errors.append(f"{os.path.basename(new_path)} не найден")
                continue
            if os.path.exists(old_path):
                errors.append(f"{os.path.basename(old_path)} уже существует, пропуск")
                continue
            try:
                os.rename(new_path, old_path)
                count += 1
            except Exception as e:
                errors.append(str(e))

        self.rename_history.pop(idx)
        self.btn_undo.setEnabled(bool(self.rename_history))

        msg = self.t("undo_ok").format(n=count)
        if errors:
            msg += "\n\nОшибки:\n" + "\n".join(errors)
        QMessageBox.information(self, self.t("undo"), msg)
        self._update_preview()

    def _show_history(self):
        """Открыть диалог истории для просмотра и выборочной отмены."""
        dlg = HistoryDialog(self.rename_history, self.current_lang, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._apply_undo_batch(dlg.selected_batch_idx)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    app.setDesktopFileName("equestria-os-rename-helper")
    win = RenamerApp()
    win.show()
    sys.exit(app.exec())
