import os

from PyQt6.QtWidgets import (
    QMainWindow, QHBoxLayout, QLineEdit, QPushButton,
    QFileDialog, QWidget
)
from PyQt6.QtGui import QFontDatabase, QFont, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ui_relocator import Ui_Relocator
import core, privilege

LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]

STRINGS = {
    "title":            {"en": "Relocate Files",            "ru": "Переместить файлы",          "de": "Dateien verschieben",        "fr": "Déplacer des fichiers",          "es": "Mover archivos",             "pt": "Mover arquivos",             "pl": "Przenieś pliki",             "uk": "Перемістити файли",          "zh": "移动文件",       "ja": "ファイルを移動"},
    "sources":          {"en": "Source(s)",                 "ru": "Источник(и)",                 "de": "Quelle(n)",                  "fr": "Source(s)",                      "es": "Origen(es)",                 "pt": "Origem(ns)",                 "pl": "Źródło(-a)",                 "uk": "Джерело(-а)",                "zh": "来源",           "ja": "移動元"},
    "destination":      {"en": "Destination",               "ru": "Назначение",                  "de": "Ziel",                       "fr": "Destination",                    "es": "Destino",                    "pt": "Destino",                    "pl": "Cel",                        "uk": "Призначення",                "zh": "目标",           "ja": "移動先"},
    "add_source":       {"en": "+ Add Source",              "ru": "+ Добавить источник",          "de": "+ Quelle hinzufügen",         "fr": "+ Ajouter source",               "es": "+ Añadir origen",            "pt": "+ Adicionar origem",         "pl": "+ Dodaj źródło",             "uk": "+ Додати джерело",           "zh": "+ 添加来源",     "ja": "+ 追加"},
    "browse_file":      {"en": "File…",                     "ru": "Файл…",                       "de": "Datei…",                     "fr": "Fichier…",                       "es": "Archivo…",                   "pt": "Arquivo…",                   "pl": "Plik…",                      "uk": "Файл…",                      "zh": "文件…",          "ja": "ファイル…"},
    "browse_folder":    {"en": "Folder…",                   "ru": "Папка…",                      "de": "Ordner…",                    "fr": "Dossier…",                       "es": "Carpeta…",                   "pt": "Pasta…",                     "pl": "Folder…",                    "uk": "Тека…",                      "zh": "文件夹…",        "ja": "フォルダ…"},
    "browse":           {"en": "Browse…",                   "ru": "Обзор…",                      "de": "Durchsuchen…",               "fr": "Parcourir…",                     "es": "Examinar…",                  "pt": "Procurar…",                  "pl": "Przeglądaj…",                "uk": "Огляд…",                     "zh": "浏览…",          "ja": "参照…"},
    "relocate":         {"en": "Relocate",                  "ru": "Переместить",                 "de": "Verschieben",                "fr": "Déplacer",                       "es": "Mover",                      "pt": "Mover",                      "pl": "Przenieś",                   "uk": "Перемістити",                "zh": "移动",           "ja": "移動"},
    "ph_source":        {"en": "Select file or folder…",   "ru": "Выберите файл или папку…",    "de": "Datei oder Ordner wählen…",  "fr": "Fichier ou dossier…",            "es": "Archivo o carpeta…",         "pt": "Arquivo ou pasta…",          "pl": "Plik lub folder…",           "uk": "Файл або тека…",             "zh": "选择文件或文件夹…","ja": "ファイルまたはフォルダ…"},
    "ph_dest":          {"en": "Select destination folder…","ru": "Выберите папку назначения…",  "de": "Zielordner wählen…",         "fr": "Dossier de destination…",        "es": "Carpeta de destino…",        "pt": "Pasta de destino…",          "pl": "Folder docelowy…",           "uk": "Тека призначення…",          "zh": "选择目标文件夹…","ja": "移動先フォルダ…"},
    "ntfs_warn":        {"en": "⚠  Symlinks are not supported on NTFS. The file will be moved without a symlink.",
                         "ru": "⚠  Символические ссылки не поддерживаются на NTFS. Файл будет перемещён без ссылки.",
                         "de": "⚠  Symlinks werden auf NTFS nicht unterstützt. Die Datei wird ohne Symlink verschoben.",
                         "fr": "⚠  Les liens symboliques ne sont pas pris en charge sur NTFS. Le fichier sera déplacé sans lien.",
                         "es": "⚠  Los enlaces simbólicos no son compatibles con NTFS. El archivo se moverá sin enlace.",
                         "pt": "⚠  Links simbólicos não são suportados em NTFS. O arquivo será movido sem link.",
                         "pl": "⚠  Dowiązania symboliczne nie są obsługiwane na NTFS. Plik zostanie przeniesiony bez dowiązania.",
                         "uk": "⚠  Символічні посилання не підтримуються на NTFS. Файл буде переміщено без посилання.",
                         "zh": "⚠  NTFS 不支持符号链接。文件将在没有符号链接的情况下移动。",
                         "ja": "⚠  NTFSではシンボリックリンクがサポートされていません。リンクなしで移動されます。"},
    "err_no_source":    {"en": "Please specify at least one source.",       "ru": "Укажите хотя бы один источник.",             "de": "Bitte mindestens eine Quelle angeben.",      "fr": "Veuillez spécifier au moins une source.",        "es": "Especifique al menos un origen.",        "pt": "Especifique pelo menos uma origem.",     "pl": "Podaj co najmniej jedno źródło.",        "uk": "Вкажіть принаймні одне джерело.",        "zh": "请至少指定一个来源。",   "ja": "移動元を1つ以上指定してください。"},
    "err_no_dest":      {"en": "Please specify a destination folder.",      "ru": "Укажите папку назначения.",                  "de": "Bitte Zielordner angeben.",                  "fr": "Veuillez spécifier un dossier de destination.",  "es": "Especifique una carpeta de destino.",    "pt": "Especifique uma pasta de destino.",      "pl": "Podaj folder docelowy.",                 "uk": "Вкажіть теку призначення.",              "zh": "请指定目标文件夹。",     "ja": "移動先フォルダを指定してください。"},
    "err_no_elevator":  {"en": "Root privileges required but no elevation tool (pkexec/kdesu) was found.",
                         "ru": "Требуются права root, но инструмент повышения прав (pkexec/kdesu) не найден.",
                         "de": "Root-Rechte erforderlich, aber kein Elevation-Tool (pkexec/kdesu) gefunden.",
                         "fr": "Droits root requis mais aucun outil d'élévation (pkexec/kdesu) trouvé.",
                         "es": "Se requieren privilegios root pero no se encontró herramienta de elevación (pkexec/kdesu).",
                         "pt": "Privilégios root necessários mas nenhuma ferramenta de elevação (pkexec/kdesu) encontrada.",
                         "pl": "Wymagane uprawnienia root, ale nie znaleziono narzędzia do podniesienia uprawnień (pkexec/kdesu).",
                         "uk": "Потрібні права root, але інструмент підвищення прав (pkexec/kdesu) не знайдено.",
                         "zh": "需要root权限但未找到权限提升工具(pkexec/kdesu)。",
                         "ja": "root権限が必要ですが、昇格ツール(pkexec/kdesu)が見つかりません。"},
    "working":          {"en": "Working…",      "ru": "Выполняется…",   "de": "Wird ausgeführt…",   "fr": "En cours…",      "es": "Procesando…",    "pt": "Processando…",   "pl": "Przetwarzanie…", "uk": "Виконується…",   "zh": "处理中…",    "ja": "処理中…"},
    "elev_title":       {"en": "Privilege Required",        "ru": "Требуются права",        "de": "Rechte erforderlich",        "fr": "Privilèges requis",          "es": "Se requieren privilegios",   "pt": "Privilégios necessários",    "pl": "Wymagane uprawnienia",       "uk": "Потрібні права",             "zh": "需要权限",       "ja": "権限が必要"},
    "elev_msg":         {"en": "Some paths require administrator privileges.\nThe application will be relaunched with elevated permissions.",
                         "ru": "Для некоторых путей требуются права администратора.\nПриложение будет перезапущено с повышенными правами.",
                         "de": "Einige Pfade erfordern Administratorrechte.\nDie Anwendung wird mit erhöhten Rechten neu gestartet.",
                         "fr": "Certains chemins nécessitent des privilèges administrateur.\nL'application sera relancée avec des droits élevés.",
                         "es": "Algunas rutas requieren privilegios de administrador.\nLa aplicación se relanzará con permisos elevados.",
                         "pt": "Alguns caminhos requerem privilégios de administrador.\nO aplicativo será reiniciado com permissões elevadas.",
                         "pl": "Niektóre ścieżki wymagają uprawnień administratora.\nAplikacja zostanie ponownie uruchomiona z podwyższonymi uprawnieniami.",
                         "uk": "Деякі шляхи потребують прав адміністратора.\nДодаток буде перезапущено з підвищеними правами.",
                         "zh": "某些路径需要管理员权限。\n应用程序将以提升的权限重新启动。",
                         "ja": "一部のパスには管理者権限が必要です。\nアプリケーションは昇格した権限で再起動されます。"},
    "dlg_file":         {"en": "Select File",       "ru": "Выберите файл",      "de": "Datei wählen",       "fr": "Sélectionner fichier",   "es": "Seleccionar archivo",    "pt": "Selecionar arquivo",     "pl": "Wybierz plik",           "uk": "Виберіть файл",          "zh": "选择文件",       "ja": "ファイルを選択"},
    "dlg_folder":       {"en": "Select Folder",     "ru": "Выберите папку",     "de": "Ordner wählen",      "fr": "Sélectionner dossier",   "es": "Seleccionar carpeta",    "pt": "Selecionar pasta",       "pl": "Wybierz folder",         "uk": "Виберіть теку",          "zh": "选择文件夹",     "ja": "フォルダを選択"},
    "dlg_dest":         {"en": "Select Destination","ru": "Выберите назначение","de": "Ziel wählen",        "fr": "Sélectionner destination","es": "Seleccionar destino",   "pt": "Selecionar destino",     "pl": "Wybierz cel",            "uk": "Виберіть призначення",   "zh": "选择目标",       "ja": "移動先を選択"},
    "success":          {"en": "Moved {n} item(s) to {dest}. Created {s} symlink(s).",
                         "ru": "Перемещено {n} элемент(ов) в {dest}. Создано {s} ссылок.",
                         "de": "{n} Element(e) nach {dest} verschoben. {s} Symlink(s) erstellt.",
                         "fr": "{n} élément(s) déplacé(s) vers {dest}. {s} lien(s) créé(s).",
                         "es": "{n} elemento(s) movido(s) a {dest}. {s} enlace(s) creado(s).",
                         "pt": "{n} item(ns) movido(s) para {dest}. {s} link(s) criado(s).",
                         "pl": "Przeniesiono {n} element(ów) do {dest}. Utworzono {s} dowiązanie(-a).",
                         "uk": "Переміщено {n} елемент(ів) до {dest}. Створено {s} посилань.",
                         "zh": "已将 {n} 个项目移动到 {dest}，创建了 {s} 个符号链接。",
                         "ja": "{n}個を{dest}に移動しました。シンボリックリンク{s}個を作成しました。"},
}


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
        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in LANGS:
            self.current_lang = "en"

        base_path = os.path.dirname(os.path.abspath(__file__))

        # Load custom font
        font_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        if os.path.exists(font_path):
            fid = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.app_title.setFont(QFont(families[0], 22, QFont.Weight.Bold))

        # Load stylesheet
        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            self.setStyleSheet(open(qss_path).read())

        # Load window icon
        icon_path = os.path.join(base_path, "equestria-os-relocator.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Language buttons
        self._lang_btns = {}
        for code in LANGS:
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self._change_lang(c))
            self.lang_row.addWidget(btn)
            self._lang_btns[code] = btn

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
        return STRINGS.get(key, {}).get(self.current_lang,
               STRINGS.get(key, {}).get("en", key))

    def _change_lang(self, lang):
        self.current_lang = lang
        for code, btn in self._lang_btns.items():
            btn.setProperty("active", "true" if code == lang else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
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
