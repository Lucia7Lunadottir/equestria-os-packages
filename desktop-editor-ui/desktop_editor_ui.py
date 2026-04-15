#!/usr/bin/env python3
import sys
import os
import json
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QLabel, QComboBox, 
                             QFileDialog, QMessageBox, QFormLayout, QDialog)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QIcon

class LocalizationDialog(QDialog):
    def __init__(self, parent, t_func):
        super().__init__(parent)
        self.t = t_func
        self.setObjectName("ModalBox")
        self.setWindowTitle(self.t("add_loc_title"))
        self.resize(300, 200)
        self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout()

        self.lang_input = QLineEdit()
        self.lang_input.setObjectName("SearchField")
        self.lang_input.setPlaceholderText(self.t("loc_lang_ph"))
        layout.addWidget(self.lang_input)

        self.name_input = QLineEdit()
        self.name_input.setObjectName("SearchField")
        self.name_input.setPlaceholderText(self.t("loc_name_ph"))
        layout.addWidget(self.name_input)

        self.comment_input = QLineEdit()
        self.comment_input.setObjectName("SearchField")
        self.comment_input.setPlaceholderText(self.t("loc_desc_ph"))
        layout.addWidget(self.comment_input)

        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton(self.t("btn_save"))
        self.btn_save.setObjectName("ModalDeleteBtn")
        self.btn_save.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton(self.t("btn_cancel"))
        self.btn_cancel.setObjectName("ModalCancelBtn")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def get_data(self):
        return (self.lang_input.text().strip(), 
                self.name_input.text().strip(), 
                self.comment_input.text().strip())


class DesktopEditorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.localizations = {} 
        self.translations = {}
        self.current_lang = "ru"
        self.lang_buttons = {}
        
        self.load_translations()
        self.initUI()
        self.retranslate_ui()

    def load_translations(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        for file in os.listdir(self.script_dir):
            if file.endswith('.json'):
                try:
                    with open(os.path.join(self.script_dir, file), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if "en" in data and isinstance(data["en"], dict):
                            self.translations.update(data)
                        else:
                            lang_code = file.replace('.json', '')
                            self.translations[lang_code] = data
                except Exception as e:
                    print(f"Ошибка загрузки {file}: {e}")

        # Дефолтный словарь теперь включает pre_args
        if not self.translations:
            self.translations["ru"] = {
                "title": "Создание ярлыка", "app_name": "Имя приложения:",
                "desc": "Описание (Comment):", "langs": "Языки:",
                "no_locs": "Локализаций нет", "add_trans": "Добавить перевод",
                "pre_args": "Пре-аргументы (python3, wine):",
                "exec": "Путь к файлу (Exec):", "browse": "Обзор",
                "args": "Пост-аргументы (--fullscreen):", "icon": "Иконка (Icon):",
                "choose": "Выбрать", "category": "Категория в меню:",
                "btn_install": "Установить в меню Пуск", "btn_save_as": "Сохранить как...",
                "btn_clear": "Очистить форму", "add_loc_title": "Добавить локализацию",
                "loc_lang_ph": "Код страны (ru, en...)", "loc_name_ph": "Имя",
                "loc_desc_ph": "Описание", "btn_save": "Сохранить", "btn_cancel": "Отмена"
            }
            self.translations["en"] = {
                "title": "Create Shortcut", "app_name": "App Name:",
                "desc": "Description (Comment):", "langs": "Languages:",
                "no_locs": "No localizations", "add_trans": "Add translation",
                "pre_args": "Pre-arguments (python3, wine):",
                "exec": "Executable Path:", "browse": "Browse",
                "args": "Post-arguments (--fullscreen):", "icon": "Icon:",
                "choose": "Choose", "category": "Menu Category:",
                "btn_install": "Install to Start", "btn_save_as": "Save as...",
                "btn_clear": "Clear Form", "add_loc_title": "Add Localization",
                "loc_lang_ph": "Country Code (en, ru...)", "loc_name_ph": "Localized Name",
                "loc_desc_ph": "Localized Description", "btn_save": "Save", "btn_cancel": "Cancel"
            }

    def t(self, key):
        return self.translations.get(self.current_lang, {}).get(key, key)

    def initUI(self):
        self.setWindowTitle("Редактор .desktop файлов")
        self.resize(650, 600)
        
        icon_path = os.path.join(self.script_dir, "desktop-editor-ui.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        main_layout = QVBoxLayout()

        lang_layout = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("TitleLabel")
        lang_layout.addWidget(self.title_label)
        lang_layout.addStretch()

        for lang in sorted(self.translations.keys()):
            btn = QPushButton(lang.upper())
            btn.setObjectName("LangBtn")
            btn.clicked.connect(lambda checked, l=lang: self.set_language(l))
            self.lang_buttons[lang] = btn
            lang_layout.addWidget(btn)

        main_layout.addLayout(lang_layout)

        self.form_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setObjectName("SearchField")
        self.label_app_name = QLabel()
        self.form_layout.addRow(self.label_app_name, self.name_input)

        self.comment_input = QLineEdit()
        self.comment_input.setObjectName("SearchField")
        self.label_desc = QLabel()
        self.form_layout.addRow(self.label_desc, self.comment_input)

        loc_layout = QHBoxLayout()
        self.loc_label = QLabel()
        self.loc_label.setStyleSheet("color: rgb(180, 180, 200);")
        self.btn_add_loc = QPushButton()
        self.btn_add_loc.setObjectName("ModalCancelBtn")
        self.btn_add_loc.clicked.connect(self.add_localization)
        loc_layout.addWidget(self.loc_label)
        loc_layout.addWidget(self.btn_add_loc)
        self.label_langs = QLabel()
        self.form_layout.addRow(self.label_langs, loc_layout)

        # НОВОЕ ПОЛЕ: Пре-аргументы
        self.pre_args_input = QLineEdit()
        self.pre_args_input.setObjectName("SearchField")
        self.label_pre_args = QLabel()
        self.form_layout.addRow(self.label_pre_args, self.pre_args_input)

        exec_layout = QHBoxLayout()
        self.exec_input = QLineEdit()
        self.exec_input.setObjectName("SearchField")
        self.btn_exec_browse = QPushButton()
        self.btn_exec_browse.setObjectName("ModalCancelBtn")
        self.btn_exec_browse.clicked.connect(self.browse_exec)
        exec_layout.addWidget(self.exec_input)
        exec_layout.addWidget(self.btn_exec_browse)
        self.label_exec = QLabel()
        self.form_layout.addRow(self.label_exec, exec_layout)

        # Старое поле: Пост-аргументы
        self.args_input = QLineEdit()
        self.args_input.setObjectName("SearchField")
        self.label_args = QLabel()
        self.form_layout.addRow(self.label_args, self.args_input)

        icon_layout = QHBoxLayout()
        self.icon_preview = QLabel("❓")
        self.icon_preview.setFixedSize(40, 40)
        self.icon_preview.setStyleSheet("""
            border: 1px solid rgb(120, 90, 180); 
            border-radius: 8px; 
            background-color: rgb(40, 35, 60); 
            font-size: 16px;
        """)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.icon_input = QLineEdit()
        self.icon_input.setObjectName("SearchField")
        self.icon_input.textChanged.connect(self.update_icon_preview)
        
        self.btn_icon_browse = QPushButton()
        self.btn_icon_browse.setObjectName("ModalCancelBtn")
        self.btn_icon_browse.clicked.connect(self.browse_icon)
        
        icon_layout.addWidget(self.icon_preview)
        icon_layout.addWidget(self.icon_input)
        icon_layout.addWidget(self.btn_icon_browse)
        
        self.label_icon = QLabel()
        self.form_layout.addRow(self.label_icon, icon_layout)

        self.category_combo = QComboBox()
        self.category_combo.setObjectName("CategoryDropdown")
        self.category_combo.addItems([
            "Utility", "Development", "Game", "Graphics", 
            "Network", "AudioVideo", "Office", "System", "Settings"
        ])
        self.label_category = QLabel()
        self.form_layout.addRow(self.label_category, self.category_combo)

        main_layout.addLayout(self.form_layout)
        main_layout.addStretch()

        btn_layout = QHBoxLayout()

        self.btn_install = QPushButton()
        self.btn_install.setObjectName("ModalDeleteBtn")
        self.btn_install.clicked.connect(self.install_to_menu)
        btn_layout.addWidget(self.btn_install)

        self.btn_save_as = QPushButton()
        self.btn_save_as.setObjectName("ListDeleteBtn")
        self.btn_save_as.clicked.connect(self.save_as)
        btn_layout.addWidget(self.btn_save_as)

        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("ModalCancelBtn")
        self.btn_clear.clicked.connect(self.clear_form)
        btn_layout.addWidget(self.btn_clear)

        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def set_language(self, lang_code):
        self.current_lang = lang_code
        self.retranslate_ui()

    def retranslate_ui(self):
        for code, btn in self.lang_buttons.items():
            btn.setProperty("active", str(code == self.current_lang).lower())
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.setWindowTitle(self.t("title"))
        self.title_label.setText(self.t("title"))
        
        self.label_app_name.setText(self.t("app_name"))
        self.label_desc.setText(self.t("desc"))
        self.label_langs.setText(self.t("langs"))
        
        self.label_pre_args.setText(self.t("pre_args")) # Новое поле
        self.label_exec.setText(self.t("exec"))
        self.label_args.setText(self.t("args")) # Старое поле
        
        self.label_icon.setText(self.t("icon"))
        self.label_category.setText(self.t("category"))

        if not self.localizations:
            self.loc_label.setText(self.t("no_locs"))
            
        self.btn_add_loc.setText(self.t("add_trans"))
        self.btn_exec_browse.setText(self.t("browse"))
        self.btn_icon_browse.setText(self.t("choose"))
        
        self.btn_install.setText(self.t("btn_install"))
        self.btn_save_as.setText(self.t("btn_save_as"))
        self.btn_clear.setText(self.t("btn_clear"))

    def browse_exec(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Executable", "")
        if file_path:
            self.exec_input.setText(file_path)

    def browse_icon(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Icon", "", "Images (*.png *.svg *.xpm);;All Files (*)")
        if file_path:
            self.icon_input.setText(file_path)

    def update_icon_preview(self, text):
        text = text.strip()
        if not text:
            self.icon_preview.clear()
            self.icon_preview.setText("❓")
            return

        pixmap = QPixmap()
        
        if os.path.isabs(text) and os.path.exists(text):
            pixmap = QPixmap(text)
        else:
            icon = QIcon.fromTheme(text)
            if not icon.isNull():
                pixmap = icon.pixmap(40, 40)

        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_preview.setPixmap(scaled_pixmap)
        else:
            self.icon_preview.clear()
            self.icon_preview.setText("❌")

    def add_localization(self):
        dialog = LocalizationDialog(self, self.t)
        if dialog.exec():
            lang, name, comment = dialog.get_data()
            if lang:
                self.localizations[lang] = {'Name': name, 'Comment': comment}
                self.loc_label.setText(", ".join(self.localizations.keys()))

    def generate_desktop_content(self):
        name = self.name_input.text().strip() or "Unnamed_App"
        comment = self.comment_input.text().strip()
        
        pre_args = self.pre_args_input.text().strip()
        exec_path = self.exec_input.text().strip()
        args = self.args_input.text().strip()
        
        icon = self.icon_input.text().strip()
        category = self.category_combo.currentText()

        # Если путь есть, оборачиваем его в кавычки
        if exec_path:
            exec_path = exec_path.strip('"\'')
            exec_path = f'"{exec_path}"'

        # Собираем Exec в правильном порядке: Пре-аргументы -> Путь -> Пост-аргументы
        exec_parts = []
        if pre_args: exec_parts.append(pre_args)
        if exec_path: exec_parts.append(exec_path)
        if args: exec_parts.append(args)
        full_exec = " ".join(exec_parts)

        lines = ["[Desktop Entry]", "Type=Application", f"Name={name}"]
        if comment: lines.append(f"Comment={comment}")
            
        for lang, data in self.localizations.items():
            if data['Name']: lines.append(f"Name[{lang}]={data['Name']}")
            if data['Comment']: lines.append(f"Comment[{lang}]={data['Comment']}")

        lines.append(f"Exec={full_exec}")
        if icon: lines.append(f"Icon={icon}")
        lines.append(f"Categories={category};")
        lines.append("Terminal=false")

        return "\n".join(lines) + "\n"

    def install_to_menu(self):
        content = self.generate_desktop_content()
        name = self.name_input.text().strip().replace(" ", "_") or "app"
        target_dir = os.path.expanduser("~/.local/share/applications")
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, f"{name.lower()}.desktop")
        
        try:
            with open(target_path, "w", encoding="utf-8") as f: f.write(content)
            os.chmod(target_path, 0o755)
            os.system(f"update-desktop-database {target_dir} >/dev/null 2>&1")
            QMessageBox.information(self, "OK", f"Installed!\n{target_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def save_as(self):
        content = self.generate_desktop_content()
        file_path, _ = QFileDialog.getSaveFileName(self, "Save .desktop", "", "Desktop Files (*.desktop)")
        if file_path:
            if not file_path.endswith('.desktop'): file_path += '.desktop'
            try:
                with open(file_path, "w", encoding="utf-8") as f: f.write(content)
                os.chmod(file_path, 0o755)
                QMessageBox.information(self, "OK", "Saved!")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def clear_form(self):
        self.name_input.clear()
        self.comment_input.clear()
        self.pre_args_input.clear() # Очистка нового поля
        self.exec_input.clear()
        self.args_input.clear()
        self.icon_input.clear()
        self.localizations.clear()
        self.loc_label.setText(self.t("no_locs"))
        self.category_combo.setCurrentIndex(0)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    app.setDesktopFileName("desktop-editor-ui")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    qss = ""
    try:
        with open(os.path.join(script_dir, "style.qss"), "r", encoding="utf-8") as f:
            qss = f.read()
    except FileNotFoundError:
        pass
        
    qss += "\nQLabel { color: rgb(240, 240, 240); }"
    app.setStyleSheet(qss)

    window = DesktopEditorApp()
    window.show()
    sys.exit(app.exec())