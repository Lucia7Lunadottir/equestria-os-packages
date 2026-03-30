import sys
import os
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QMessageBox,
    QProgressBar, QFileDialog, QListWidget, QListWidgetItem, QSpinBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase

# Используем твои наработки
import privilege

LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
STRINGS = {
    "title":      {"en": "Equestria OS: Bulk Renamer", "ru": "Equestria OS: Массовое переименование"},
    "dir_label":  {"en": "Target Directory",          "ru": "Целевая папка"},
    "find":       {"en": "Find text",                 "ru": "Найти текст"},
    "replace":    {"en": "Replace with",              "ru": "Заменить на"},
    "prefix":     {"en": "Add Prefix",                "ru": "Добавить префикс"},
    "suffix":     {"en": "Add Suffix",                "ru": "Добавить суффикс"},
    "numbers":    {"en": "Numbering (Start at)",      "ru": "Нумерация (начиная с)"},
    "preview":    {"en": "Preview",                   "ru": "Предпросмотр"},
    "apply":      {"en": "Rename All",                "ru": "Переименовать всё"},
    "browse":     {"en": "Browse",                    "ru": "Обзор"},
    "success":    {"en": "Successfully renamed {n} files!", "ru": "Успешно переименовано {n} файлов!"},
}

class RenamerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in LANGS: self.current_lang = "en"

        self.files_map = [] # Список кортежей (старый_путь, новое_имя)
        self._setup_ui()

    def t(self, key):
        return STRINGS.get(key, {}).get(self.current_lang, STRINGS[key]["en"])

    def _setup_ui(self):
        self.setWindowTitle(self.t("title"))
        self.resize(700, 800)

        base_path = os.path.dirname(os.path.abspath(__file__))
        title_font = "sans-serif"
        f_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families: title_font = families[0]

        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            qss = open(qss_path).read().replace("{{TITLE_FONT}}", f'"{title_font}"')
            # Фикс для корректного отображения QListWidget в темной теме
            qss += "\nQListWidget { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 8px; padding: 5px; }"
            self.setStyleSheet(qss)

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

        btn_row.addWidget(self.btn_preview)
        btn_row.addWidget(self.btn_apply)
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

        # Разделяем имя и расширение, чтобы не переименовать само расширение случайно
        name, ext = os.path.splitext(old_name)

        # 1. Замена текста
        if find_txt:
            name = name.replace(find_txt, replace_txt)

        # 2. Префикс и Суффикс
        name = f"{prefix}{name}{suffix}"

        # 3. Нумерация (если не 0)
        if start_num > 0 or self.num_spin.value() > 0:
            # Формат _001, _002 и т.д.
            name = f"{name}_{start_num + index:03d}"

        return name + ext

    def _update_preview(self):
        self.list_preview.clear()
        dir_path = self.path_edit.text()
        if not os.path.isdir(dir_path): return

        self.files_map = []
        # Берем только файлы, сортируем для предсказуемости
        try:
            all_items = sorted(os.listdir(dir_path))
        except Exception: return

        idx = 0
        for item_name in all_items:
            full_path = os.path.join(dir_path, item_name)
            if os.path.isfile(full_path):
                new_name = self._get_new_name(item_name, idx)

                # Показываем изменения
                display_text = f"{item_name}  →  {new_name}"
                list_item = QListWidgetItem(display_text)

                if item_name != new_name:
                    list_item.setForeground(Qt.GlobalColor.green)

                self.list_preview.addItem(list_item)
                self.files_map.append((full_path, os.path.join(dir_path, new_name)))
                idx += 1

    def _do_rename(self):
        if not self.files_map: return

        # Простая проверка на изменения
        changes = [pair for pair in self.files_map if pair[0] != pair[1]]
        if not changes: return

        count = 0
        for old, new in changes:
            try:
                os.rename(old, new)
                count += 1
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not rename {os.path.basename(old)}: {e}")

        QMessageBox.information(self, "Success", self.t("success").format(n=count))
        self._update_preview()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = RenamerApp()
    win.show()
    sys.exit(app.exec())
