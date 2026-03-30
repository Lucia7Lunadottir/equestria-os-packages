import sys
import os
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QMessageBox,
    QCheckBox, QProgressBar, QSpinBox, QSlider
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFontDatabase

import privilege

ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKMARK_SVG = os.path.join(ASSETS_DIR, "check_mark.svg")

def generate_assets():
    if os.path.exists(CHECKMARK_SVG):
        return
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path fill="#ffffff" d="M13.485 1.414l1.414 1.414L6.343 11.373 1.1 6.13l1.414-1.414 3.829 3.829z"/>
</svg>"""
    try:
        with open(CHECKMARK_SVG, 'w') as f:
            f.write(svg_content)
    except Exception:
        pass

LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
STRINGS = {
    "title":        {"en": "Equestria OS Swap Manager",       "ru": "Equestria OS: Менеджер Подкачки",    "de": "Equestria OS Swap-Manager",        "fr": "Equestria OS Gestionnaire Swap",    "es": "Equestria OS Gestor Swap",          "pt": "Equestria OS Gerenciador Swap",     "pl": "Equestria OS Menedżer Swap",         "uk": "Equestria OS Менеджер Swap",         "zh": "E交换空间管理器",            "ja": "Equestria OS スワップマネージャー"},
    "current_swap": {"en": "Active Swap Files",               "ru": "Активные файлы подкачки",            "de": "Aktive Swap-Dateien",              "fr": "Fichiers Swap actifs",              "es": "Archivos Swap activos",             "pt": "Arquivos Swap ativos",              "pl": "Aktywne pliki wymiany",              "uk": "Активні файли підкачки",             "zh": "活动交换文件",                           "ja": "アクティブなスワップファイル"},
    "path":         {"en": "Swap File Path",                  "ru": "Путь к файлу подкачки",              "de": "Swap-Dateipfad",                   "fr": "Chemin du fichier Swap",            "es": "Ruta del archivo Swap",             "pt": "Caminho do arquivo Swap",           "pl": "Ścieżka pliku wymiany",              "uk": "Шлях до файлу підкачки",             "zh": "交换文件路径",                           "ja": "スワップファイルパス"},
    "size":         {"en": "Size (GB)",                       "ru": "Размер (ГБ)",                        "de": "Größe (GB)",                       "fr": "Taille (Go)",                       "es": "Tamaño (GB)",                       "pt": "Tamanho (GB)",                      "pl": "Rozmiar (GB)",                       "uk": "Розмір (ГБ)",                        "zh": "大小 (GB)",                              "ja": "サイズ (GB)"},
    "fstab_chk":    {"en": "Mount on boot (/etc/fstab)",      "ru": "Включать при загрузке (/etc/fstab)", "de": "Beim Booten einbinden (/etc/fstab)", "fr": "Monter au démarrage (/etc/fstab)","es": "Montar al inicio (/etc/fstab)",       "pt": "Montar na inicialização (/etc/fstab)","pl": "Montuj przy rozruchu (/etc/fstab)",  "uk": "Вмикати при завантаженні (/etc/fstab)", "zh": "开机挂载 (/etc/fstab)",                  "ja": "起動時にマウント (/etc/fstab)"},
    "swappiness":   {"en": "Kernel Swappiness (0-100)",       "ru": "Жадность подкачки (Swappiness)",     "de": "Kernel Swappiness",                "fr": "Swappiness du Noyau",               "es": "Swappiness del Kernel",             "pt": "Swappiness do Kernel",              "pl": "Swappiness Jądra",                   "uk": "Swappiness Ядра",                    "zh": "内核 Swappiness",                        "ja": "カーネル Swappiness"},
    "btn_apply":    {"en": "Create / Resize Swap",            "ru": "Создать / Изменить размер",          "de": "Swap erstellen / ändern",          "fr": "Créer / Redimensionner Swap",       "es": "Crear / Redimensionar Swap",        "pt": "Criar / Redimensionar Swap",        "pl": "Utwórz / Zmień rozmiar Swap",        "uk": "Створити / Змінити розмір Swap",     "zh": "创建 / 调整交换空间",                    "ja": "スワップを作成 / サイズ変更"},
    "btn_swapp":    {"en": "Apply Swappiness",                "ru": "Применить Swappiness",               "de": "Swappiness anwenden",              "fr": "Appliquer Swappiness",              "es": "Aplicar Swappiness",                "pt": "Aplicar Swappiness",                "pl": "Zastosuj Swappiness",                "uk": "Застосувати Swappiness",             "zh": "应用 Swappiness",                        "ja": "Swappiness を適用"},
    "btn_disable":  {"en": "Disable Swap",                    "ru": "Отключить Swap",                     "de": "Swap deaktivieren",                "fr": "Désactiver Swap",                   "es": "Desactivar Swap",                   "pt": "Desativar Swap",                    "pl": "Wyłącz Swap",                        "uk": "Вимкнути Swap",                      "zh": "禁用交换空间",                           "ja": "スワップを無効化"},
    "btn_delete":   {"en": "Delete File",                     "ru": "Удалить файл",                       "de": "Datei löschen",                    "fr": "Supprimer le fichier",              "es": "Eliminar archivo",                  "pt": "Excluir arquivo",                   "pl": "Usuń plik",                          "uk": "Видалити файл",                      "zh": "删除文件",                               "ja": "ファイルを削除"},
    "status_app":   {"en": "Applying changes (may take time)...", "ru": "Применение (может занять время)...", "de": "Änderungen werden angewendet...", "fr": "Application en cours...",           "es": "Aplicando cambios...",              "pt": "Aplicando alterações...",           "pl": "Stosowanie zmian...",                "uk": "Застосування (може зайняти час)...", "zh": "正在应用更改...",                        "ja": "変更を適用中..."},
    "success":      {"en": "Operation successful!",           "ru": "Операция выполнена успешно!",        "de": "Vorgang erfolgreich!",             "fr": "Opération réussie !",               "es": "¡Operación exitosa!",               "pt": "Operação bem-sucedida!",            "pl": "Operacja zakończona pomyślnie!",     "uk": "Операцію виконано успішно!",         "zh": "操作成功！",                             "ja": "操作が完了しました！"},
    "err_elevate":  {"en": "Failed to get root access.",      "ru": "Не удалось получить права root.",    "de": "Root-Zugriff fehlgeschlagen.",     "fr": "Échec de l'accès root.",            "es": "Error al obtener acceso root.",     "pt": "Falha ao obter acesso root.",       "pl": "Błąd uzyskania dostępu root.",       "uk": "Помилка отримання прав root.",       "zh": "获取 root 权限失败。",                   "ja": "root アクセスに失敗しました。"},
    "no_swap":      {"en": "No active swap found.",           "ru": "Нет активных файлов подкачки.",      "de": "Kein aktiver Swap gefunden.",      "fr": "Aucun swap actif trouvé.",          "es": "No se encontró swap activo.",       "pt": "Nenhum swap ativo encontrado.",     "pl": "Brak aktywnego swapu.",              "uk": "Немає активних файлів підкачки.",    "zh": "未找到活动的交换空间。",                 "ja": "アクティブなスワップはありません。"}
}

class SwapWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, command_args):
        super().__init__()
        self.command_args = command_args

    def run(self):
        elevator = privilege.find_elevator()
        if not elevator:
            self.finished.emit(False, "No elevation tool found.")
            return

        backend_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swap_backend.py")
        inner = [sys.executable, backend_script] + self.command_args

        cmd = [elevator, "--"] + inner if os.path.basename(elevator) == "kdesu" else [elevator] + inner

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate()

        if proc.returncode == 0:
            self.finished.emit(True, stdout.strip())
        else:
            self.finished.emit(False, stderr.strip())

class SwapManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in LANGS:
            self.current_lang = "en"

        self._setup_ui()
        self._load_data()

    def t(self, key):
        d = STRINGS.get(key, {})
        return d.get(self.current_lang) or d.get("en", key)

    def _change_lang(self, lang):
        self.current_lang = lang
        for code, btn in self._lang_btns.items():
            btn.setProperty("active", "true" if code == lang else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._refresh_ui()

    def _make_divider(self):
        d = QFrame()
        d.setObjectName("Divider")
        d.setFrameShape(QFrame.Shape.HLine)
        d.setFixedHeight(1)
        return d

    def _setup_ui(self):
        self.setWindowTitle(self.t("title"))
        self.resize(550, 700)

        base_path = os.path.dirname(os.path.abspath(__file__))

        title_font_family = "sans-serif"
        font_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        if os.path.exists(font_path):
            fid = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                title_font_family = families[0]

        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            qss = open(qss_path).read()
            qss = qss.replace("{{CHECKMARK_SVG_PATH}}", CHECKMARK_SVG)
            qss = qss.replace("{{TITLE_FONT}}", f'"{title_font_family}"')

            # Добавим стили для слайдера на лету, если их нет в основном файле
            qss += """
            QSlider::groove:horizontal { border-radius: 4px; height: 6px; background: #313244; }
            QSlider::handle:horizontal { background: #f5c2e7; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::handle:horizontal:hover { background: #f2cdcd; }
            """
            self.setStyleSheet(qss)

        central = QWidget()
        central.setObjectName("CentralBg")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(30, 20, 30, 20)
        main_layout.setSpacing(12)

        # --- Title & Lang ---
        title_row = QHBoxLayout()
        self.app_title = QLabel(self.t("title"))
        self.app_title.setObjectName("AppTitle")
        title_row.addWidget(self.app_title)
        title_row.addStretch()

        self._lang_btns = {}
        lang_row = QHBoxLayout()
        lang_row.setSpacing(4)
        for code in LANGS:
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self._change_lang(c))
            lang_row.addWidget(btn)
            self._lang_btns[code] = btn
        title_row.addLayout(lang_row)
        main_layout.addLayout(title_row)
        main_layout.addWidget(self._make_divider())

        # --- Current Swap Info ---
        info_row = QHBoxLayout()
        self.lbl_current = QLabel(self.t("current_swap"))
        self.lbl_current.setObjectName("SectionLabel")
        info_row.addWidget(self.lbl_current)

        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setObjectName("BrowseBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._load_data)
        info_row.addWidget(self.refresh_btn)
        info_row.addStretch()
        main_layout.addLayout(info_row)

        self.info_lbl = QLabel(self.t("no_swap"))
        self.info_lbl.setObjectName("StatusLabel")
        main_layout.addWidget(self.info_lbl)
        main_layout.addWidget(self._make_divider())

        # --- Swap Settings ---
        self.lbl_path = QLabel(self.t("path"))
        self.lbl_path.setObjectName("SectionLabel")
        main_layout.addWidget(self.lbl_path)

        self.path_input = QLineEdit()
        self.path_input.setObjectName("DestEdit")
        self.path_input.setText("/swapfile")
        main_layout.addWidget(self.path_input)

        size_row = QHBoxLayout()
        self.lbl_size = QLabel(self.t("size"))
        self.lbl_size.setObjectName("SectionLabel")
        size_row.addWidget(self.lbl_size)

        self.size_spin = QSpinBox()
        self.size_spin.setObjectName("SourceEdit")
        self.size_spin.setRange(1, 128)
        self.size_spin.setValue(32) # Default 32 GB for Unity builds!
        self.size_spin.setSuffix(" GB")
        self.size_spin.setFixedHeight(34)
        size_row.addWidget(self.size_spin)
        size_row.addStretch()
        main_layout.addLayout(size_row)

        self.fstab_cb = QCheckBox(self.t("fstab_chk"))
        self.fstab_cb.setChecked(True)
        self.fstab_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fstab_cb.setObjectName("SwapCheckBox")
        main_layout.addWidget(self.fstab_cb)

        # --- Actions for Swap ---
        self.apply_btn = QPushButton(self.t("btn_apply"))
        self.apply_btn.setObjectName("RelocateBtn")
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.clicked.connect(self._apply_swap)
        main_layout.addWidget(self.apply_btn)

        action_row = QHBoxLayout()
        self.disable_btn = QPushButton(self.t("btn_disable"))
        self.disable_btn.setObjectName("BrowseBtn")
        self.disable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.disable_btn.clicked.connect(self._disable_swap)

        self.delete_btn = QPushButton(self.t("btn_delete"))
        self.delete_btn.setObjectName("DangerBtn")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(self._delete_swap)

        action_row.addWidget(self.disable_btn)
        action_row.addWidget(self.delete_btn)
        main_layout.addLayout(action_row)
        main_layout.addWidget(self._make_divider())

        # --- Swappiness Settings ---
        self.lbl_swappiness = QLabel(self.t("swappiness"))
        self.lbl_swappiness.setObjectName("SectionLabel")
        main_layout.addWidget(self.lbl_swappiness)

        swapp_row = QHBoxLayout()
        self.swapp_slider = QSlider(Qt.Orientation.Horizontal)
        self.swapp_slider.setRange(0, 100)
        self.swapp_slider.setValue(60)
        self.swapp_slider.valueChanged.connect(self._update_swapp_label)

        self.swapp_val_lbl = QLabel("60")
        self.swapp_val_lbl.setObjectName("StatusLabel")
        self.swapp_val_lbl.setFixedWidth(30)

        swapp_row.addWidget(self.swapp_slider)
        swapp_row.addWidget(self.swapp_val_lbl)
        main_layout.addLayout(swapp_row)

        self.apply_swapp_btn = QPushButton(self.t("btn_swapp"))
        self.apply_swapp_btn.setObjectName("BrowseBtn")
        self.apply_swapp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_swapp_btn.clicked.connect(self._apply_swappiness)
        main_layout.addWidget(self.apply_swapp_btn)

        main_layout.addStretch()

        # --- Progress ---
        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("ProgressFrame")
        self.progress_frame.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_frame)
        prog_layout.setContentsMargins(0, 10, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        prog_layout.addWidget(self.progress_bar)

        self.prog_status_lbl = QLabel(self.t("status_app"))
        self.prog_status_lbl.setObjectName("StatusLabel")
        self.prog_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prog_layout.addWidget(self.prog_status_lbl)

        main_layout.addWidget(self.progress_frame)

    def _update_swapp_label(self, val):
        self.swapp_val_lbl.setText(str(val))

    def _refresh_ui(self):
        self.setWindowTitle(self.t("title"))
        self.app_title.setText(self.t("title"))
        self.lbl_current.setText(self.t("current_swap"))
        self.lbl_path.setText(self.t("path"))
        self.lbl_size.setText(self.t("size"))
        self.lbl_swappiness.setText(self.t("swappiness"))
        self.fstab_cb.setText(self.t("fstab_chk"))
        self.apply_btn.setText(self.t("btn_apply"))
        self.apply_swapp_btn.setText(self.t("btn_swapp"))
        self.disable_btn.setText(self.t("btn_disable"))
        self.delete_btn.setText(self.t("btn_delete"))
        self.prog_status_lbl.setText(self.t("status_app"))
        self._load_data()

    def _load_data(self):
        # Чтение файла подкачки
        try:
            result = subprocess.run(["swapon", "--show=NAME,SIZE"], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) <= 1:
                self.info_lbl.setText(self.t("no_swap"))
            else:
                formatted_lines = []
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        formatted_lines.append(f"• {parts[0]}  —  {parts[1]}")
                self.info_lbl.setText("\n".join(formatted_lines))
        except Exception:
            self.info_lbl.setText(self.t("no_swap"))

        # Чтение текущего значения swappiness
        try:
            with open("/proc/sys/vm/swappiness", "r") as f:
                val = int(f.read().strip())
                self.swapp_slider.setValue(val)
                self._update_swapp_label(val)
        except Exception:
            pass

    def _run_backend(self, args):
        for w in (self.apply_btn, self.disable_btn, self.delete_btn, self.path_input,
                  self.size_spin, self.fstab_cb, self.refresh_btn, self.apply_swapp_btn, self.swapp_slider):
            w.setEnabled(False)

        self.progress_frame.setVisible(True)

        self.worker = SwapWorker(args)
        self.worker.finished.connect(self._on_worker_done)
        self.worker.start()

    def _on_worker_done(self, success, message):
        for w in (self.apply_btn, self.disable_btn, self.delete_btn, self.path_input,
                  self.size_spin, self.fstab_cb, self.refresh_btn, self.apply_swapp_btn, self.swapp_slider):
            w.setEnabled(True)
        self.progress_frame.setVisible(False)

        if success:
            QMessageBox.information(self, "Success", self.t("success"))
        else:
            QMessageBox.critical(self, "Error", f"{self.t('err_elevate')}\n{message}")

        self._load_data()

    def _apply_swap(self):
        path = self.path_input.text().strip()
        size = str(self.size_spin.value())
        fstab = "yes" if self.fstab_cb.isChecked() else "no"
        if not path:
            return
        self._run_backend(["--create", path, size, fstab])

    def _disable_swap(self):
        path = self.path_input.text().strip()
        if not path:
            return
        self._run_backend(["--disable", path])

    def _delete_swap(self):
        path = self.path_input.text().strip()
        if not path:
            return
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete {path} completely?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._run_backend(["--delete", path])

    def _apply_swappiness(self):
        val = str(self.swapp_slider.value())
        self._run_backend(["--swappiness", val])

def main():
    generate_assets()
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-os-swap-manager")
    win = SwapManagerApp()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
