import sys, os, subprocess, threading
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui_pkg import Ui_PackageManager, PackageRow

class PackageData:
    def __init__(self, name, source):
        self.name = name
        self.source = source
        self.category = "Drivers" if any(x in name.lower() for x in ["nvidia", "vulkan", "firmware"]) else "Software"

class main_app(QMainWindow, Ui_PackageManager):
    uninstall_finished = pyqtSignal(bool, str)
    fetch_finished = pyqtSignal(list)
    cache_clear_finished = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.uninstall_finished.connect(self.on_uninstall_finished)
        self.fetch_finished.connect(self.on_fetch_finished)
        self.cache_clear_finished.connect(self.on_cache_clear_finished)

        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.title_label.setFont(QFont(families[0], 28, QFont.Weight.Bold))
                self.modal_title.setFont(QFont(families[0], 22, QFont.Weight.Bold))

        q_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(q_path): self.setStyleSheet(open(q_path, "r").read())

        icon_path = os.path.join(self.base_path, "equestria-os-logo.png")
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))

        QApplication.setDesktopFileName("equestria-os-package-manager")

        self.langs_db = {
            "ui.title": {"en": "✨ Equestria OS Packages", "ru": "✨ Пакеты Equestria OS", "de": "✨ Equestria OS Pakete", "fr": "✨ Paquets Equestria OS", "es": "✨ Paquetes Equestria OS", "pt": "✨ Pacotes Equestria OS", "pl": "✨ Pakiety Equestria OS", "uk": "✨ Пакети Equestria OS", "zh": "✨ Equestria OS 软件包", "ja": "✨ Equestria OS パッケージ"},
            "cat.all": {"en": "All", "ru": "Все", "de": "Alle", "fr": "Tous", "es": "Todos", "pt": "Todos", "pl": "Wszystkie", "uk": "Всі", "zh": "全部", "ja": "すべて"},
            "cat.software": {"en": "Software", "ru": "Программы", "de": "Software", "fr": "Logiciels", "es": "Software", "pt": "Software", "pl": "Oprogramowanie", "uk": "Програми", "zh": "软件", "ja": "ソフトウェア"},
            "cat.drivers": {"en": "Drivers", "ru": "Драйверы", "de": "Treiber", "fr": "Pilotes", "es": "Controladores", "pt": "Drivers", "pl": "Sterowniki", "uk": "Драйвери", "zh": "驱动程序", "ja": "ドライバー"},
            "cat.aur": {"en": "AUR", "ru": "AUR", "de": "AUR", "fr": "AUR", "es": "AUR", "pt": "AUR", "pl": "AUR", "uk": "AUR", "zh": "AUR", "ja": "AUR"},
            "modal.title": {"en": "✨ Confirmation", "ru": "✨ Подтверждение", "de": "✨ Bestätigung", "fr": "✨ Confirmation", "es": "✨ Confirmación", "pt": "✨ Confirmação", "pl": "✨ Potwierdzenie", "uk": "✨ Підтвердження", "zh": "✨ 确认", "ja": "✨ 確認"},
            "modal.confirm": {
                "en": "Are you sure you want to delete {0}?",
                "ru": "Вы уверены, что хотите удалить {0}?",
                "de": "Sind Sie sicher, dass Sie {0} löschen möchten?",
                "fr": "Voulez-vous vraiment supprimer {0} ?",
                "es": "¿Seguro que quieres eliminar {0}?",
                "pt": "Tem certeza de que deseja excluir {0}?",
                "pl": "Czy na pewno chcesz usunąć {0}?",
                "uk": "Ви впевнені, що хочете видалити {0}?",
                "zh": "您确定要删除 {0} 吗？",
                "ja": "{0} を削除してもよろしいですか？"
            },
            "modal.wait": {
                "en": "Deleting {0}...",
                "ru": "Удаление {0}...",
                "de": "Verarbeitung {0}...",
                "fr": "Suppression de {0}...",
                "es": "Eliminando {0}...",
                "pt": "Excluindo {0}...",
                "pl": "Usuwanie {0}...",
                "uk": "Видалення {0}...",
                "zh": "正在删除 {0}...",
                "ja": "{0} を削除しています..."
            },
            "btn.delete": {"en": "Delete", "ru": "Удалить", "de": "Löschen", "fr": "Supprimer", "es": "Eliminar", "pt": "Excluir", "pl": "Usuń", "uk": "Видалити", "zh": "删除", "ja": "削除"},
            "btn.cancel": {"en": "Cancel", "ru": "Отмена", "de": "Abbrechen", "fr": "Annuler", "es": "Cancelar", "pt": "Cancelar", "pl": "Anuluj", "uk": "Скасувати", "zh": "取消", "ja": "キャンセル"},
            "btn.clearcache": {"en": "🧹 Clear Cache", "ru": "🧹 Очистить кэш", "de": "🧹 Cache leeren", "fr": "🧹 Vider le cache", "es": "🧹 Limpiar caché", "pt": "🧹 Limpar cache", "pl": "🧹 Wyczyść cache", "uk": "🧹 Очистити кеш", "zh": "🧹 清理缓存", "ja": "🧹 キャッシュを削除"},
            "btn.clear": {"en": "Clear", "ru": "Очистить", "de": "Leeren", "fr": "Vider", "es": "Limpiar", "pt": "Limpar", "pl": "Wyczyść", "uk": "Очистити", "zh": "清理", "ja": "削除"},
            "modal.clearcache_confirm": {
                "en": "Remove cached packages that are no longer installed?",
                "ru": "Удалить из кэша пакеты, которые больше не установлены?",
                "de": "Nicht mehr installierte Pakete aus dem Cache entfernen?",
                "fr": "Supprimer du cache les paquets qui ne sont plus installés ?",
                "es": "¿Eliminar del caché los paquetes que ya no están instalados?",
                "pt": "Remover do cache os pacotes que não estão mais instalados?",
                "pl": "Usunąć z pamięci podręcznej pakiety, które nie są już zainstalowane?",
                "uk": "Видалити з кешу пакети, які більше не встановлені?",
                "zh": "从缓存中删除不再安装的软件包？",
                "ja": "インストールされていないパッケージをキャッシュから削除しますか？"
            },
            "modal.clearcache_wait": {
                "en": "Clearing package cache...",
                "ru": "Очистка кэша пакетов...",
                "de": "Cache wird geleert...",
                "fr": "Nettoyage du cache...",
                "es": "Limpiando caché...",
                "pt": "Limpando cache...",
                "pl": "Czyszczenie pamięci podręcznej...",
                "uk": "Очищення кешу пакетів...",
                "zh": "正在清理软件包缓存...",
                "ja": "パッケージキャッシュをクリア中..."
            }
        }

        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in self.langs_db["cat.all"]: self.current_lang = "en"

        self.all_packages = []
        self.pkg_to_delete = None
        self.action_type = None

        self.setup_logic()
        self.apply_localization()
        self.refresh_packages()

    def t(self, key):
        return self.langs_db.get(key, {}).get(self.current_lang, self.langs_db.get(key, {}).get("en", key))

    def setup_logic(self):
        self.search_field.textChanged.connect(self.apply_filters)
        self.category_dropdown.currentTextChanged.connect(self.apply_filters)

        self.btn_confirm_cancel.clicked.connect(self.modal_overlay.hide)
        self.btn_confirm_delete.clicked.connect(self.execute_confirm)
        self.btn_clearcache.clicked.connect(self.show_clearcache_confirm)

        codes = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
        for code in codes:
            btn = QPushButton(code.upper())
            btn.setObjectName("LangBtn") # ФИКС: Жесткая привязка ID
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda chk, c=code: self.change_lang(c))
            self.lang_layout.addWidget(btn)

    def resizeEvent(self, event):
        self.modal_overlay.resize(event.size())
        super().resizeEvent(event)

    def change_lang(self, lang):
        self.current_lang = lang
        for i in range(self.lang_layout.count()):
            btn = self.lang_layout.itemAt(i).widget()
            if btn and isinstance(btn, QPushButton):
                btn.setProperty("active", "true" if btn.text().lower() == lang else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self.apply_localization()

    def apply_localization(self):
        title = self.t("ui.title")
        self.title_label.setText(title)
        self.setWindowTitle(title)

        self.modal_title.setText(self.t("modal.title"))

        self.category_dropdown.blockSignals(True)
        self.category_dropdown.clear()

        self.category_dropdown.addItems([
            self.t("cat.all"), self.t("cat.software"), self.t("cat.drivers"),
            self.t("cat.aur"), "Flatpak", "Snap"
        ])
        self.category_dropdown.blockSignals(False)

        self.btn_confirm_cancel.setText(self.t("btn.cancel"))
        self.btn_confirm_delete.setText(self.t("btn.delete"))
        self.btn_clearcache.setText(self.t("btn.clearcache"))

        delete_text = self.t("btn.delete")
        for i in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(i).widget()
            if isinstance(widget, PackageRow):
                widget.btn_delete.setText(delete_text)

        self.apply_filters()

    def refresh_packages(self):
        def _fetch():
            pkgs = []
            r1 = subprocess.run(["pacman", "-Qnq"], capture_output=True, text=True)
            for l in r1.stdout.splitlines(): pkgs.append(PackageData(l.strip(), "pacman"))

            r2 = subprocess.run(["yay", "-Qmq"], capture_output=True, text=True)
            for l in r2.stdout.splitlines(): pkgs.append(PackageData(l.strip(), "aur"))

            self.fetch_finished.emit(pkgs)

        threading.Thread(target=_fetch, daemon=True).start()

    def on_fetch_finished(self, pkgs):
        self.all_packages = pkgs
        self.build_list()

    def build_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for pkg in self.all_packages:
            row = PackageRow(pkg, self.t("btn.delete"), self.show_confirm)
            self.list_layout.addWidget(row)

        self.apply_filters()

    def apply_filters(self):
        query = self.search_field.text().lower()
        cat = self.category_dropdown.currentText()

        for i in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(i).widget()
            if isinstance(widget, PackageRow):
                pkg = widget.pkg_data
                text_match = not query or query in pkg.name.lower()
                cat_match = (cat == self.t("cat.all") or
                             (cat == self.t("cat.software") and pkg.category == "Software") or
                             (cat == self.t("cat.drivers") and pkg.category == "Drivers") or
                             (cat == self.t("cat.aur") and pkg.source == "aur") or
                             (cat == "Flatpak" and pkg.source == "flatpak") or
                             (cat == "Snap" and pkg.source == "snap"))

                widget.setVisible(text_match and cat_match)

    def show_confirm(self, pkg):
        self.action_type = "delete"
        self.pkg_to_delete = pkg
        self.modal_text.setText(self.t("modal.confirm").format(pkg.name))
        self.btn_confirm_delete.setText(self.t("btn.delete"))
        self.btn_confirm_delete.show()
        self.btn_confirm_cancel.show()
        self.modal_overlay.show()
        self.modal_overlay.raise_()

    def show_clearcache_confirm(self):
        self.action_type = "clearcache"
        self.modal_text.setText(self.t("modal.clearcache_confirm"))
        self.btn_confirm_delete.setText(self.t("btn.clear"))
        self.btn_confirm_delete.show()
        self.btn_confirm_cancel.show()
        self.modal_overlay.show()
        self.modal_overlay.raise_()

    def execute_confirm(self):
        if self.action_type == "delete":
            self.execute_uninstall()
        elif self.action_type == "clearcache":
            self.execute_clearcache()

    def execute_uninstall(self):
        if not self.pkg_to_delete: return
        pkg_name = self.pkg_to_delete.name

        self.modal_text.setText(self.t("modal.wait").format(pkg_name))

        self.btn_confirm_delete.hide()
        self.btn_confirm_cancel.hide()

        cmd = f"pkexec pacman -Rns --noconfirm {pkg_name}"

        def _run():
            proc = subprocess.run(["/bin/bash", "-c", cmd])
            self.uninstall_finished.emit(proc.returncode == 0, pkg_name)

        threading.Thread(target=_run, daemon=True).start()

    def on_uninstall_finished(self, success, pkg_name):
        self.modal_overlay.hide()
        self.btn_confirm_delete.show()
        self.btn_confirm_cancel.show()

        if success:
            self.all_packages = [p for p in self.all_packages if p.name != pkg_name]
            self.build_list()

    def execute_clearcache(self):
        self.modal_text.setText(self.t("modal.clearcache_wait"))
        self.btn_confirm_delete.hide()
        self.btn_confirm_cancel.hide()

        def _run():
            proc = subprocess.run(["/bin/bash", "-c", "pkexec pacman -Sc --noconfirm"])
            self.cache_clear_finished.emit(proc.returncode == 0)

        threading.Thread(target=_run, daemon=True).start()

    def on_cache_clear_finished(self, success):
        self.modal_overlay.hide()
        self.btn_confirm_delete.show()
        self.btn_confirm_cancel.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = main_app()
    win.show()
    sys.exit(app.exec())
