import sys, os, subprocess, threading, shutil, shlex
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QComboBox
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui_pkg import Ui_PackageManager, PackageRow

class PackageData:
    def __init__(self, name, source, app_id=None):
        self.name = name
        self.source = source
        self.app_id = app_id  # used for Flatpak uninstall
        self.category = "Drivers" if any(x in name.lower() for x in ["nvidia", "vulkan", "firmware"]) else "Software"

class main_app(QMainWindow, Ui_PackageManager):
    uninstall_finished = pyqtSignal(bool, str)
    fetch_finished = pyqtSignal(list)
    leftovers_found = pyqtSignal(str, list)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.uninstall_finished.connect(self.on_uninstall_finished)
        self.fetch_finished.connect(self.on_fetch_finished)
        self.leftovers_found.connect(self.on_leftovers_found)

        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.title_label.setFont(QFont(families[0], 28, QFont.Weight.Bold))
                self.modal_title.setFont(QFont(families[0], 22, QFont.Weight.Bold))

        q_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(q_path): self.setStyleSheet(open(q_path, "r").read())

        icon_path = os.path.join(self.base_path, "equestria-os-package-manager.png")
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
            "modal.data_none": {
                "en": "No files created by the program were found in your home folder.",
                "ru": "Файлов, созданных программой, в домашней папке не найдено.",
                "de": "Keine vom Programm erstellten Dateien im Home-Ordner gefunden.",
                "fr": "Aucun fichier créé par le programme n'a été trouvé dans le dossier personnel.",
                "es": "No se encontraron archivos creados por el programa en la carpeta personal.",
                "pt": "Nenhum arquivo criado pelo programa foi encontrado na pasta pessoal.",
                "pl": "Nie znaleziono plików utworzonych przez program w katalogu domowym.",
                "uk": "Файлів, створених програмою, у домашній теці не знайдено.",
                "zh": "未在主目录中找到程序创建的文件。",
                "ja": "ホームフォルダーにプログラムが作成したファイルは見つかりませんでした。"
            },
            "modal.data": {
                "en": "Also delete files created by the program ({0})",
                "ru": "Также удалить файлы, созданные программой ({0})",
                "de": "Auch vom Programm erstellte Dateien löschen ({0})",
                "fr": "Supprimer aussi les fichiers créés par le programme ({0})",
                "es": "Eliminar también los archivos creados por el programa ({0})",
                "pt": "Excluir também os arquivos criados pelo programa ({0})",
                "pl": "Usuń także pliki utworzone przez program ({0})",
                "uk": "Також видалити файли, створені програмою ({0})",
                "zh": "同时删除程序创建的文件（{0}）",
                "ja": "プログラムが作成したファイルも削除する（{0}）"
            }
        }

        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in self.langs_db["cat.all"]: self.current_lang = "en"

        self.all_packages = []
        self.pkg_to_delete = None
        self.leftover_paths = []
        self.leftover_size = 0

        self.setup_logic()
        self.apply_localization()
        self.refresh_packages()

    def t(self, key):
        return self.langs_db.get(key, {}).get(self.current_lang, self.langs_db.get(key, {}).get("en", key))

    def fmt_size(self, n):
        units = {"ru": ["Б", "КБ", "МБ", "ГБ"],
                 "uk": ["Б", "КБ", "МБ", "ГБ"]}.get(self.current_lang, ["B", "KB", "MB", "GB"])
        size = float(n)
        unit = units[0]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                break
            size /= 1024
        return f"{int(size)} {unit}" if unit == units[0] else f"{size:.1f} {unit}"

    def leftover_candidates(self, pkg):
        """
        Где программа могла оставить свои файлы. Только точное совпадение
        имени (без регистра) — никаких догадок, чтобы не удалить чужое.
        """
        home = os.path.expanduser("~")
        if pkg.source == "flatpak":
            return [os.path.join(home, ".var", "app", pkg.app_id or pkg.name)]
        if pkg.source == "snap":
            return [os.path.join(home, "snap", pkg.name)]

        names = {pkg.name.lower()}
        for suf in ("-bin", "-git", "-appimage"):
            if pkg.name.lower().endswith(suf):
                names.add(pkg.name.lower()[:-len(suf)])

        bases = [os.path.join(home, ".config"),
                 os.path.join(home, ".cache"),
                 os.path.join(home, ".local", "share"),
                 os.path.join(home, ".local", "state")]
        if pkg.source == "aur":
            bases.append(os.path.join(home, ".cache", "yay"))

        found = []
        for base in bases:
            try:
                for entry in os.listdir(base):
                    if entry.lower() in names:
                        found.append(os.path.join(base, entry))
            except OSError:
                pass
        # Скрытая папка прямо в домашней: ~/.имя
        for n in sorted(names):
            p = os.path.join(home, "." + n)
            if os.path.isdir(p):
                found.append(p)
        return found

    @staticmethod
    def _path_size(path):
        if not os.path.isdir(path) or os.path.islink(path):
            try:
                return os.lstat(path).st_size
            except OSError:
                return 0
        total = 0
        for root, dirs, files in os.walk(path, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
        return total

    def scan_leftovers(self, pkg):
        found = []
        for p in self.leftover_candidates(pkg):
            if os.path.lexists(p):
                found.append((p, self._path_size(p)))
        self.leftovers_found.emit(pkg.name, found)

    def on_leftovers_found(self, pkg_name, found):
        # Модалка могла уже закрыться или перейти к другому пакету
        if not self.pkg_to_delete or self.pkg_to_delete.name != pkg_name:
            return
        if not self.modal_overlay.isVisible() or self.btn_confirm_delete.isHidden():
            return
        if not found:
            # Показываем и «ничего не нашлось» — иначе непонятно, есть ли функция вообще
            self.modal_paths.setText(self.t("modal.data_none"))
            self.modal_paths.show()
            return
        self.leftover_paths = [p for p, s in found]
        self.leftover_size = sum(s for p, s in found)
        home = os.path.expanduser("~")
        self.chk_delete_data.setText(self.t("modal.data").format(self.fmt_size(self.leftover_size)))
        self.modal_paths.setText("\n".join(p.replace(home, "~", 1) for p in self.leftover_paths))
        self.chk_delete_data.show()
        self.modal_paths.show()

    def setup_logic(self):
        self.search_field.textChanged.connect(self.apply_filters)
        self.category_dropdown.currentTextChanged.connect(self.apply_filters)

        self.btn_confirm_cancel.clicked.connect(self.modal_overlay.hide)
        self.btn_confirm_delete.clicked.connect(self.execute_uninstall)

        codes = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
        # Компактный выпадающий список языков вместо ряда кнопок
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for code in codes:
            self.lang_combo.addItem(code.upper(), code)
        idx = self.lang_combo.findData(self.current_lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        # activated срабатывает только при выборе пользователем — без рекурсии
        self.lang_combo.activated.connect(
            lambda i: self.change_lang(self.lang_combo.itemData(i)))
        self.lang_layout.addWidget(self.lang_combo)

    def resizeEvent(self, event):
        self.modal_overlay.resize(event.size())
        super().resizeEvent(event)

    def change_lang(self, lang):
        self.current_lang = lang
        idx = self.lang_combo.findData(lang)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
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
        if self.chk_delete_data.isVisible():
            self.chk_delete_data.setText(self.t("modal.data").format(self.fmt_size(self.leftover_size)))

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

            try:
                r3 = subprocess.run(["flatpak", "list", "--app", "--columns=name,application"],
                                     capture_output=True, text=True)
                if r3.returncode == 0:
                    for l in r3.stdout.splitlines():
                        parts = l.split("\t")
                        if len(parts) >= 2:
                            pkgs.append(PackageData(parts[0].strip(), "flatpak", app_id=parts[1].strip()))
            except FileNotFoundError:
                pass

            try:
                r4 = subprocess.run(["snap", "list"], capture_output=True, text=True)
                if r4.returncode == 0:
                    for l in r4.stdout.splitlines()[1:]:
                        parts = l.split()
                        if parts:
                            pkgs.append(PackageData(parts[0], "snap"))
            except FileNotFoundError:
                pass

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
        self.pkg_to_delete = pkg
        self.leftover_paths = []
        self.leftover_size = 0
        self.modal_text.setText(self.t("modal.confirm").format(pkg.name))

        self.chk_delete_data.setChecked(False)
        self.chk_delete_data.hide()
        self.modal_paths.hide()

        self.btn_confirm_delete.show()
        self.btn_confirm_cancel.show()

        self.modal_overlay.show()
        self.modal_overlay.raise_()

        threading.Thread(target=self.scan_leftovers, args=(pkg,), daemon=True).start()

    def execute_uninstall(self):
        if not self.pkg_to_delete: return
        pkg_name = self.pkg_to_delete.name

        delete_data = self.chk_delete_data.isVisible() and self.chk_delete_data.isChecked()
        leftovers = list(self.leftover_paths) if delete_data else []

        self.modal_text.setText(self.t("modal.wait").format(pkg_name))

        self.btn_confirm_delete.hide()
        self.btn_confirm_cancel.hide()
        self.chk_delete_data.hide()
        self.modal_paths.hide()

        if self.pkg_to_delete.source == "flatpak":
            app_id = self.pkg_to_delete.app_id or pkg_name
            # --delete-data убирает ~/.var/app сам — вручную не трогаем
            flag = "--delete-data " if delete_data else ""
            cmd = f"flatpak uninstall -y {flag}{shlex.quote(app_id)}"
            leftovers = []
        elif self.pkg_to_delete.source == "snap":
            flag = "--purge " if delete_data else ""
            cmd = f"pkexec snap remove {flag}{shlex.quote(pkg_name)}"
            leftovers = []
        else:
            cmd = f"pkexec pacman -Rns --noconfirm {shlex.quote(pkg_name)}"

        def _run():
            proc = subprocess.run(["/bin/bash", "-c", cmd])
            if proc.returncode == 0:
                for p in leftovers:
                    try:
                        if os.path.isdir(p) and not os.path.islink(p):
                            shutil.rmtree(p, ignore_errors=True)
                        else:
                            os.remove(p)
                    except OSError:
                        pass
            self.uninstall_finished.emit(proc.returncode == 0, pkg_name)

        threading.Thread(target=_run, daemon=True).start()

    def on_uninstall_finished(self, success, pkg_name):
        self.modal_overlay.hide()
        self.btn_confirm_delete.show()
        self.btn_confirm_cancel.show()

        if success:
            self.all_packages = [p for p in self.all_packages if p.name != pkg_name]
            self.build_list()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = main_app()
    win.show()
    sys.exit(app.exec())
