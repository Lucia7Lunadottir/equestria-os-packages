#!/usr/bin/env python3
import sys
import os
import csv
from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout,
                             QLabel, QLineEdit, QPushButton, QHBoxLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

# Полностью отвязываемся от хардкода. Все пути строим относительно самого скрипта
SYSTEM_PATH = os.path.dirname(os.path.abspath(__file__))

# --- Локализация ---
def get_sys_lang():
    lang = os.environ.get("LANG", "en_US").split('_')[0]
    supported = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
    return lang if lang in supported else "en"

def load_localization():
    csv_path = os.path.join(SYSTEM_PATH, "localization.csv")
    translations = {}
    if not os.path.exists(csv_path):
        return translations

    lang = get_sys_lang()
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
            lang_idx = headers.index(lang)
        except (StopIteration, ValueError):
            try:
                lang_idx = headers.index("en")
            except ValueError:
                lang_idx = 1

        for row in reader:
            if len(row) > lang_idx:
                translations[row[0]] = row[lang_idx]
    return translations

t = load_localization()

def t_str(key, default):
    return t.get(key, default)

# --- GUI ---
class AskPassDialog(QDialog):
    def __init__(self, prompt_text):
        super().__init__()
        self.setWindowTitle(t_str("askpass.title", "Equestria OS Git Authentication"))
        self.setFixedSize(450, 160)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.lbl_prompt = QLabel(prompt_text)
        self.lbl_prompt.setWordWrap(True)
        layout.addWidget(self.lbl_prompt)

        self.txt_input = QLineEdit()
        if "password" in prompt_text.lower() or "token" in prompt_text.lower():
            self.txt_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.txt_input)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton(t_str("askpass.btn_cancel", "Cancel"))
        self.btn_cancel.setObjectName("btnDanger")
        self.btn_ok = QPushButton(t_str("askpass.btn_ok", "OK"))
        self.btn_ok.setObjectName("btnSave")

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.txt_input.returnPressed.connect(self.btn_ok.click)

    def get_value(self):
        return self.txt_input.text()

def main():
    prompt_text = sys.argv[1] if len(sys.argv) > 1 else "Enter Git credentials:"
    app = QApplication(sys.argv)

    # Иконка тоже ищется динамически (сначала в системе, если нет — берем стандартную)
    icon_path = "/usr/share/pixmaps/equestria-os-git-askpass.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(QIcon.fromTheme("preferences-desktop-theme"))

    qss_path = os.path.join(SYSTEM_PATH, "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    dialog = AskPassDialog(prompt_text)
    if dialog.exec():
        print(dialog.get_value())
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
