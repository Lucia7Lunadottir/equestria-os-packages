import sys, os, re, time, subprocess, threading, shutil, shlex
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QComboBox
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui_pkg import Ui_PackageManager, PackageRow

# Программы, ставящиеся через `curl ... | sh/bash`, не оставляют записи ни в
# pacman, ни в pip — единственный след — их собственная папка в $HOME.
# Каждая запись: уникальный маркер (иначе рискуем принять чужую папку за эту
# программу) и способ удаления — официальный самостоятельный uninstaller,
# если он есть и безопасно неинтерактивен, иначе прямое удаление папки
# (это ровно то, что официальная документация советует делать вручную).
CURL_INSTALLS = [
    {
        "id": "rustup",
        "name": "Rust (rustup)",
        "desc": "Rust toolchain installer and version manager",
        "icon": "text-x-rust",
        "marker": "~/.rustup",
        "official_bin": "~/.cargo/bin/rustup",
        "official_cmd": "~/.cargo/bin/rustup self uninstall -y",
        "remove_paths": ["~/.rustup", "~/.cargo"],
        # rustup сам чистит за собой строку в shell rc — отдельного предупреждения не нужно
        "rc_severity": "none",
    },
    {
        "id": "nvm",
        "name": "Node Version Manager (nvm)",
        "desc": "Manages multiple installed Node.js versions",
        "icon": "nodejs",
        "marker": "~/.nvm",
        "remove_paths": ["~/.nvm"],
        "rc_hint": 'export NVM_DIR="$HOME/.nvm"\n[ -s "$NVM_DIR/nvm.sh" ] && \\. "$NVM_DIR/nvm.sh"\n[ -s "$NVM_DIR/bash_completion" ] && \\. "$NVM_DIR/bash_completion"',
        # Строки защищены проверкой [ -s file ] — после удаления папки просто ничего не делают
        "rc_severity": "cosmetic",
    },
    {
        "id": "oh-my-zsh",
        "name": "Oh My Zsh",
        "desc": "Framework for managing Zsh configuration",
        "icon": "utilities-terminal",
        "marker": "~/.oh-my-zsh",
        "remove_paths": ["~/.oh-my-zsh"],
        "rc_hint": 'export ZSH="$HOME/.oh-my-zsh"\nZSH_THEME="..."\nplugins=(...)\nsource $ZSH/oh-my-zsh.sh',
        # source $ZSH/oh-my-zsh.sh больше не найдёт файл — zsh стартует с ошибкой
        # и без темы/плагинов/алиасов, откатываясь к голому шеллу
        "rc_severity": "breaks",
    },
    {
        "id": "volta",
        "name": "Volta",
        "desc": "JavaScript tool manager (Node, npm, Yarn)",
        "icon": "nodejs",
        "marker": "~/.volta",
        "remove_paths": ["~/.volta"],
        "rc_hint": 'export VOLTA_HOME="$HOME/.volta"\nexport PATH="$VOLTA_HOME/bin:$PATH"',
        "rc_severity": "cosmetic",
    },
    {
        "id": "deno",
        "name": "Deno",
        "desc": "Secure runtime for JavaScript and TypeScript",
        "icon": "utilities-terminal",
        "marker": "~/.deno",
        "remove_paths": ["~/.deno"],
        "rc_hint": 'export DENO_INSTALL="$HOME/.deno"\nexport PATH="$DENO_INSTALL/bin:$PATH"',
        "rc_severity": "cosmetic",
    },
    {
        "id": "pyenv",
        "name": "pyenv",
        "desc": "Simple Python version management",
        "icon": "text-x-python",
        "marker": "~/.pyenv",
        "remove_paths": ["~/.pyenv"],
        "rc_hint": 'export PYENV_ROOT="$HOME/.pyenv"\nexport PATH="$PYENV_ROOT/bin:$PATH"\neval "$(pyenv init -)"',
        # eval "$(pyenv init -)" будет падать с ошибкой "command not found"
        # при каждом запуске шелла, пока строку не убрать вручную
        "rc_severity": "breaks",
    },
]

# Файлы, которые реально может править пользовательский шелл. Fish не входит —
# у него другой синтаксис и другое расположение конфига, шаблоны ниже не подойдут.
RC_FILES = ["~/.bashrc", "~/.zshrc", "~/.profile"]

# Только строго специфичные для каждого инсталлятора шаблоны — ни один паттерн
# не должен совпасть со строкой, которую пользователь мог написать сам по
# другому поводу (иначе автоудаление снесёт что-то чужое).
RC_LINE_PATTERNS = {
    "nvm": [
        re.compile(r'^\s*export\s+NVM_DIR='),
        re.compile(r'NVM_DIR.*nvm\.sh'),
        re.compile(r'NVM_DIR.*bash_completion'),
    ],
    "volta": [
        re.compile(r'^\s*export\s+VOLTA_HOME='),
        re.compile(r'VOLTA_HOME.*PATH|PATH.*VOLTA_HOME'),
    ],
    "deno": [
        re.compile(r'^\s*export\s+DENO_INSTALL='),
        re.compile(r'DENO_INSTALL.*PATH|PATH.*DENO_INSTALL'),
    ],
    "pyenv": [
        re.compile(r'^\s*export\s+PYENV_ROOT='),
        re.compile(r'PYENV_ROOT.*PATH|PATH.*PYENV_ROOT'),
        re.compile(r'eval\s+"\$\(pyenv init'),
    ],
    "oh-my-zsh": [
        re.compile(r'^\s*export\s+ZSH=.*oh-my-zsh'),
        re.compile(r'^\s*ZSH_THEME='),
        re.compile(r'^\s*plugins=\('),
        re.compile(r'source\s+["\']?\$ZSH/oh-my-zsh\.sh'),
    ],
}

class PackageData:
    def __init__(self, name, source, app_id=None, description="", icon_name=None):
        self.name = name
        self.source = source
        self.app_id = app_id  # used for Flatpak uninstall
        self.description = description
        self.icon_name = icon_name
        self.category = "Drivers" if any(x in name.lower() for x in ["nvidia", "vulkan", "firmware"]) else "Software"

class main_app(QMainWindow, Ui_PackageManager):
    # Мета-пакеты pip: сам pacman ничего не знает про пакеты, поставленные
    # через них, поэтому их удаление не ломает зависимости, но осиротит
    # всё, что стоит через `pip install --user` — нужно явное подтверждение
    PIP_META_PKGS = {"python-pip", "python-pipx"}

    uninstall_finished = pyqtSignal(bool, str)
    fetch_finished = pyqtSignal(list)
    leftovers_found = pyqtSignal(str, list)
    pip_conflict_found = pyqtSignal(str, list)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.uninstall_finished.connect(self.on_uninstall_finished)
        self.fetch_finished.connect(self.on_fetch_finished)
        self.leftovers_found.connect(self.on_leftovers_found)
        self.pip_conflict_found.connect(self.on_pip_conflict_found)

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
            "cat.pip": {"en": "Pip", "ru": "Pip", "de": "Pip", "fr": "Pip", "es": "Pip", "pt": "Pip", "pl": "Pip", "uk": "Pip", "zh": "Pip", "ja": "Pip"},
            "cat.curl": {"en": "Curl", "ru": "Curl", "de": "Curl", "fr": "Curl", "es": "Curl", "pt": "Curl", "pl": "Curl", "uk": "Curl", "zh": "Curl", "ja": "Curl"},
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
            "btn.ok": {"en": "OK", "ru": "Понятно", "de": "OK", "fr": "OK", "es": "OK", "pt": "OK", "pl": "OK", "uk": "Гаразд", "zh": "好的", "ja": "OK"},
            "modal.rc_title": {
                "en": "⚠ One more thing", "ru": "⚠ Ещё кое-что", "de": "⚠ Noch etwas", "fr": "⚠ Encore une chose",
                "es": "⚠ Una cosa más", "pt": "⚠ Mais uma coisa", "pl": "⚠ Jeszcze jedno", "uk": "⚠ Ще дещо",
                "zh": "⚠ 还有一件事", "ja": "⚠ もう一つ"
            },
            "modal.rc_breaks": {
                "en": "These lines were found in your shell config and will now show errors every time you open a terminal:",
                "ru": "В конфиге шелла найдены такие строки — теперь они будут выдавать ошибку при каждом открытии терминала:",
                "de": "Diese Zeilen wurden in Ihrer Shell-Konfiguration gefunden und zeigen nun bei jedem Öffnen eines Terminals Fehler an:",
                "fr": "Ces lignes ont été trouvées dans votre config shell et afficheront désormais une erreur à chaque ouverture d'un terminal :",
                "es": "Se encontraron estas líneas en tu configuración de shell y ahora mostrarán errores cada vez que abras una terminal:",
                "pt": "Estas linhas foram encontradas na configuração do shell e agora mostrarão erros toda vez que você abrir um terminal:",
                "pl": "W konfiguracji powłoki znaleziono te linie — teraz będą pokazywać błąd przy każdym otwarciu terminala:",
                "uk": "У конфігурації шелла знайдено такі рядки — тепер вони видаватимуть помилку щоразу під час відкриття термінала:",
                "zh": "在你的 shell 配置文件中发现了这些代码行，现在每次打开终端都会报错：",
                "ja": "シェル設定ファイルに次の行が見つかりました。今後、ターミナルを開くたびにエラーが表示されます:"
            },
            "modal.rc_cosmetic": {
                "en": "These unused lines were found in your shell config. They won't cause errors, but you can remove them if you want a clean file:",
                "ru": "В конфиге шелла найдены такие неиспользуемые строки. Ошибок они не вызовут, но можно удалить их для чистоты:",
                "de": "Diese ungenutzten Zeilen wurden in Ihrer Shell-Konfiguration gefunden. Sie verursachen keine Fehler, können aber bei Bedarf entfernt werden:",
                "fr": "Ces lignes inutilisées ont été trouvées dans votre config shell. Elles ne causeront pas d'erreur, mais vous pouvez les supprimer si vous voulez un fichier propre :",
                "es": "Se encontraron estas líneas sin usar en tu configuración de shell. No causarán errores, pero puedes eliminarlas si quieres un archivo limpio:",
                "pt": "Estas linhas não usadas foram encontradas na configuração do shell. Elas não causarão erros, mas você pode removê-las se quiser um arquivo limpo:",
                "pl": "W konfiguracji powłoki znaleziono te nieużywane linie. Nie spowodują błędów, ale możesz je usunąć dla porządku:",
                "uk": "У конфігурації шелла знайдено ці невикористовувані рядки. Помилок вони не спричинять, але їх можна прибрати для охайності:",
                "zh": "在你的 shell 配置文件中发现了这些未使用的代码行。它们不会导致错误，但如果想让文件更整洁，可以删除：",
                "ja": "シェル設定ファイルに次の未使用の行が見つかりました。エラーは起きませんが、きれいにしたい場合は削除できます:"
            },
            "modal.rc_none_found": {
                "en": "No matching lines were found in ~/.bashrc, ~/.zshrc or ~/.profile — either you already cleaned them up, or you use a different shell (e.g. fish), in which case check its config manually.",
                "ru": "В ~/.bashrc, ~/.zshrc и ~/.profile подходящих строк не нашлось — либо ты уже их убрала, либо используешь другой шелл (например fish), тогда проверь его конфиг вручную.",
                "de": "In ~/.bashrc, ~/.zshrc oder ~/.profile wurden keine passenden Zeilen gefunden — entweder haben Sie diese bereits entfernt, oder Sie verwenden eine andere Shell (z. B. fish), dann prüfen Sie deren Konfiguration manuell.",
                "fr": "Aucune ligne correspondante trouvée dans ~/.bashrc, ~/.zshrc ou ~/.profile — soit vous les avez déjà supprimées, soit vous utilisez un autre shell (par ex. fish), auquel cas vérifiez sa config manuellement.",
                "es": "No se encontraron líneas coincidentes en ~/.bashrc, ~/.zshrc o ~/.profile — o ya las eliminaste, o usas otro shell (p. ej. fish), en cuyo caso revisa su configuración manualmente.",
                "pt": "Nenhuma linha correspondente foi encontrada em ~/.bashrc, ~/.zshrc ou ~/.profile — ou você já as removeu, ou usa outro shell (ex.: fish), nesse caso verifique a configuração manualmente.",
                "pl": "W ~/.bashrc, ~/.zshrc ani ~/.profile nie znaleziono pasujących linii — albo już je usunęłaś, albo używasz innej powłoki (np. fish) — wtedy sprawdź jej konfigurację ręcznie.",
                "uk": "У ~/.bashrc, ~/.zshrc та ~/.profile відповідних рядків не знайдено — або ти вже їх прибрала, або використовуєш інший шелл (наприклад fish), тоді перевір його конфіг вручну.",
                "zh": "在 ~/.bashrc、~/.zshrc 或 ~/.profile 中未找到匹配的代码行——可能你已经清理过了，或者你使用的是其他 shell（例如 fish），请手动检查其配置。",
                "ja": "~/.bashrc、~/.zshrc、~/.profile に該当する行は見つかりませんでした。すでに削除済みか、fish など別のシェルを使用している場合は、そちらの設定を手動で確認してください。"
            },
            "btn.rc_auto": {
                "en": "Remove automatically", "ru": "Убрать автоматически", "de": "Automatisch entfernen",
                "fr": "Supprimer automatiquement", "es": "Eliminar automáticamente", "pt": "Remover automaticamente",
                "pl": "Usuń automatycznie", "uk": "Прибрати автоматично", "zh": "自动删除", "ja": "自動的に削除"
            },
            "modal.rc_done": {
                "en": "Done. A backup of the original file was saved next to it (.bak) before editing:",
                "ru": "Готово. Перед изменением рядом с файлом сохранена резервная копия (.bak):",
                "de": "Fertig. Vor der Bearbeitung wurde eine Sicherungskopie der Originaldatei daneben gespeichert (.bak):",
                "fr": "Terminé. Une sauvegarde du fichier original a été enregistrée à côté (.bak) avant modification :",
                "es": "Listo. Se guardó una copia de seguridad del archivo original junto a él (.bak) antes de editar:",
                "pt": "Pronto. Um backup do arquivo original foi salvo ao lado dele (.bak) antes da edição:",
                "pl": "Gotowe. Przed edycją zapisano kopię zapasową oryginalnego pliku obok niego (.bak):",
                "uk": "Готово. Перед зміною поруч із файлом збережено резервну копію (.bak):",
                "zh": "完成。编辑前已在原文件旁保存了备份（.bak）：",
                "ja": "完了しました。編集前に元のファイルのバックアップ（.bak）を同じ場所に保存しました:"
            },
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
            },
            "modal.pip_conflict": {
                "en": "⚠ These packages were installed via pip and will be orphaned: {0}",
                "ru": "⚠ Эти пакеты установлены через pip и осиротеют: {0}",
                "de": "⚠ Diese Pakete wurden über pip installiert und werden verwaist: {0}",
                "fr": "⚠ Ces paquets ont été installés via pip et deviendront orphelins : {0}",
                "es": "⚠ Estos paquetes se instalaron con pip y quedarán huérfanos: {0}",
                "pt": "⚠ Esses pacotes foram instalados via pip e ficarão órfãos: {0}",
                "pl": "⚠ Te pakiety zostały zainstalowane przez pip i zostaną osierocone: {0}",
                "uk": "⚠ Ці пакети встановлені через pip і залишаться осиротілими: {0}",
                "zh": "⚠ 以下软件包是通过 pip 安装的，删除后将变成孤立文件：{0}",
                "ja": "⚠ これらは pip でインストールされたパッケージで、削除後は孤立します: {0}"
            },
            "chk.pip_ack": {
                "en": "I understand these will stop receiving updates",
                "ru": "Я понимаю, что они перестанут обновляться",
                "de": "Mir ist bewusst, dass diese keine Updates mehr erhalten",
                "fr": "Je comprends qu'ils ne recevront plus de mises à jour",
                "es": "Entiendo que dejarán de recibir actualizaciones",
                "pt": "Entendo que eles deixarão de receber atualizações",
                "pl": "Rozumiem, że przestaną otrzymywać aktualizacje",
                "uk": "Я розумію, що вони перестануть оновлюватись",
                "zh": "我知道这些软件包将不再收到更新",
                "ja": "これらは今後アップデートされなくなることを理解しました"
            }
        }

        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in self.langs_db["cat.all"]: self.current_lang = "en"

        self.all_packages = []
        self.pkg_to_delete = None
        self.leftover_paths = []
        self.leftover_size = 0
        self._rc_entry = None
        self._rc_found = None

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
        self.chk_pip_ack.switch.toggled.connect(self.btn_confirm_delete.setEnabled)
        self.btn_rc_auto.clicked.connect(self.on_rc_auto_clicked)

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
            self.t("cat.aur"), "Flatpak", "Snap", self.t("cat.pip"), self.t("cat.curl")
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
                r3 = subprocess.run(["flatpak", "list", "--app",
                                      "--columns=name,application,description"],
                                     capture_output=True, text=True)
                if r3.returncode == 0:
                    for l in r3.stdout.splitlines():
                        parts = l.split("\t")
                        if len(parts) >= 2:
                            desc = parts[2].strip() if len(parts) >= 3 else ""
                            pkgs.append(PackageData(parts[0].strip(), "flatpak",
                                                     app_id=parts[1].strip(),
                                                     description=desc, icon_name=parts[1].strip()))
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

            pip_names = []
            try:
                r5 = subprocess.run(["pip", "list", "--user", "--format=freeze"],
                                     capture_output=True, text=True)
                if r5.returncode == 0:
                    for l in r5.stdout.splitlines():
                        if "==" in l:
                            name = l.split("==")[0].strip()
                            pip_names.append(name)
                            pkgs.append(PackageData(name, "pip", icon_name="text-x-python"))
            except FileNotFoundError:
                pass

            for entry in CURL_INSTALLS:
                if os.path.isdir(os.path.expanduser(entry["marker"])):
                    pkgs.append(PackageData(entry["name"], "curl", app_id=entry["id"],
                                             description=entry.get("desc", ""),
                                             icon_name=entry.get("icon")))

            # --- Описания и иконки (pkgdesc от pacman/AUR — то же, что даёт PKGBUILD,
            # но взятое из уже установленного пакета, а не из исходников) ---
            self._enrich_pacman(pkgs)
            self._enrich_pip(pkgs, pip_names)

            self.fetch_finished.emit(pkgs)

        threading.Thread(target=_fetch, daemon=True).start()

    @staticmethod
    def _enrich_pacman(pkgs):
        targets = {p.name: p for p in pkgs if p.source in ("pacman", "aur")}
        if not targets:
            return
        env = dict(os.environ, LC_ALL="C")

        try:
            r = subprocess.run(["pacman", "-Qi"], capture_output=True, text=True, env=env)
            name = None
            for line in r.stdout.splitlines():
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if key == "Name":
                    name = val
                elif key == "Description" and name in targets:
                    targets[name].description = val
        except FileNotFoundError:
            pass

        try:
            desktop_dir = "/usr/share/applications"
            files = [os.path.join(desktop_dir, f) for f in os.listdir(desktop_dir)
                     if f.endswith(".desktop")]
            if files:
                r = subprocess.run(["pacman", "-Qo"] + files, capture_output=True,
                                    text=True, env=env)
                path_to_pkg = {}
                for line in r.stdout.splitlines():
                    if " is owned by " not in line:
                        continue
                    path_part, rest = line.split(" is owned by ", 1)
                    path_to_pkg[path_part.strip()] = rest.split()[0]
                for path, pkgname in path_to_pkg.items():
                    if pkgname not in targets or targets[pkgname].icon_name:
                        continue
                    try:
                        with open(path, "r", errors="ignore") as fh:
                            for l in fh:
                                if l.startswith("Icon="):
                                    targets[pkgname].icon_name = l.split("=", 1)[1].strip()
                                    break
                    except OSError:
                        pass
        except OSError:
            pass

    @staticmethod
    def _enrich_pip(pkgs, pip_names):
        if not pip_names:
            return
        targets = {p.name: p for p in pkgs if p.source == "pip"}
        try:
            r = subprocess.run(["pip", "show"] + pip_names, capture_output=True, text=True)
            name = None
            for line in r.stdout.splitlines():
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Summary:") and name in targets:
                    targets[name].description = line.split(":", 1)[1].strip()
        except FileNotFoundError:
            pass

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
                             (cat == "Snap" and pkg.source == "snap") or
                             (cat == self.t("cat.pip") and pkg.source == "pip") or
                             (cat == self.t("cat.curl") and pkg.source == "curl"))

                widget.setVisible(text_match and cat_match)

    def show_confirm(self, pkg):
        self.pkg_to_delete = pkg
        self.leftover_paths = []
        self.leftover_size = 0
        self.modal_text.setText(self.t("modal.confirm").format(pkg.name))

        self.chk_delete_data.setChecked(False)
        self.chk_delete_data.hide()
        self.modal_paths.hide()

        self.chk_pip_ack.setChecked(False)
        self.chk_pip_ack.hide()

        self.btn_rc_auto.hide()
        self._rc_entry = None
        self._rc_found = None

        # show_rc_notice подменяет текст кнопки cancel на "OK" — возвращаем как было
        self.btn_confirm_cancel.setText(self.t("btn.cancel"))
        self.btn_confirm_delete.setText(self.t("btn.delete"))

        self.btn_confirm_delete.show()
        self.btn_confirm_cancel.show()

        if pkg.source == "pacman" and pkg.name in self.PIP_META_PKGS:
            self.btn_confirm_delete.setEnabled(False)
            threading.Thread(target=self.scan_pip_conflict, args=(pkg,), daemon=True).start()
        elif pkg.source == "curl":
            # Вся программа и так живёт в одной известной папке — отдельно
            # сканировать домашнюю папку на "хвосты" незачем
            self.btn_confirm_delete.setEnabled(True)
        else:
            self.btn_confirm_delete.setEnabled(True)
            threading.Thread(target=self.scan_leftovers, args=(pkg,), daemon=True).start()

        self.modal_overlay.show()
        self.modal_overlay.raise_()

    def scan_pip_conflict(self, pkg):
        names = []
        try:
            r = subprocess.run(["pip", "list", "--user", "--format=freeze"],
                                capture_output=True, text=True)
            if r.returncode == 0:
                names = [l.split("==")[0].strip() for l in r.stdout.splitlines() if "==" in l]
        except FileNotFoundError:
            pass
        self.pip_conflict_found.emit(pkg.name, names)

    def on_pip_conflict_found(self, pkg_name, names):
        if not self.pkg_to_delete or self.pkg_to_delete.name != pkg_name:
            return
        if not names:
            self.btn_confirm_delete.setEnabled(True)
            return
        self.modal_paths.setText(self.t("modal.pip_conflict").format(", ".join(names)))
        self.modal_paths.show()
        self.chk_pip_ack.setText(self.t("chk.pip_ack"))
        self.chk_pip_ack.show()
        self.btn_confirm_delete.setEnabled(self.chk_pip_ack.isChecked())

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
        self.chk_pip_ack.hide()

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
        elif self.pkg_to_delete.source == "pip":
            # Пользовательские pip-пакеты живут в ~/.local — root не нужен
            cmd = f"pip uninstall -y {shlex.quote(pkg_name)}"
            leftovers = []
        elif self.pkg_to_delete.source == "curl":
            entry = next((e for e in CURL_INSTALLS if e["id"] == self.pkg_to_delete.app_id), None)
            official_bin = os.path.expanduser(entry.get("official_bin", "")) if entry else ""
            if entry and official_bin and os.path.isfile(official_bin):
                cmd = entry["official_cmd"]
            elif entry:
                paths = " ".join(shlex.quote(os.path.expanduser(p)) for p in entry["remove_paths"])
                cmd = f"rm -rf {paths}"
            else:
                cmd = "true"
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
        rc_entry = None
        if (success and self.pkg_to_delete and self.pkg_to_delete.name == pkg_name
                and self.pkg_to_delete.source == "curl"):
            entry = next((e for e in CURL_INSTALLS if e["id"] == self.pkg_to_delete.app_id), None)
            if entry and entry.get("rc_severity", "none") != "none":
                rc_entry = entry

        self.modal_overlay.hide()
        self.btn_confirm_delete.show()
        self.btn_confirm_cancel.show()

        if success:
            self.all_packages = [p for p in self.all_packages if p.name != pkg_name]
            self.build_list()

        if rc_entry:
            self.show_rc_notice(rc_entry)

    @staticmethod
    def scan_rc_lines(entry_id):
        """Ищет реально существующие строки — не шаблон, а то, что правда лежит
        в файлах пользователя, чтобы не предлагать удалить то, чего там нет,
        и не гадать вместо показа фактов."""
        patterns = RC_LINE_PATTERNS.get(entry_id, [])
        found = {}
        for rc in RC_FILES:
            path = os.path.expanduser(rc)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", errors="ignore") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            matches = [l.rstrip("\n") for l in lines if any(p.search(l) for p in patterns)]
            if matches:
                found[path] = matches
        return found

    @staticmethod
    def remove_rc_lines(entry_id, found):
        patterns = RC_LINE_PATTERNS.get(entry_id, [])
        for path in found:
            try:
                with open(path, "r", errors="ignore") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            backup = f"{path}.bak-{time.strftime('%Y%m%d%H%M%S')}"
            try:
                shutil.copy2(path, backup)
                kept = [l for l in lines if not any(p.search(l) for p in patterns)]
                with open(path, "w") as fh:
                    fh.writelines(kept)
            except OSError:
                pass

    def show_rc_notice(self, entry):
        self._rc_entry = entry
        self._rc_found = self.scan_rc_lines(entry["id"])

        self.modal_title.setText(self.t("modal.rc_title"))
        self.chk_delete_data.hide()
        self.chk_pip_ack.hide()
        self.btn_confirm_delete.hide()
        self.btn_confirm_cancel.setText(self.t("btn.ok"))
        self.btn_confirm_cancel.show()

        if self._rc_found:
            key = "modal.rc_breaks" if entry["rc_severity"] == "breaks" else "modal.rc_cosmetic"
            self.modal_text.setText(self.t(key))

            home = os.path.expanduser("~")
            self.modal_paths.setText("\n".join(
                f"{path.replace(home, '~', 1)}:\n" + "\n".join(f"  {l}" for l in lns)
                for path, lns in self._rc_found.items()
            ))
            self.modal_paths.show()

            self.btn_rc_auto.setText(self.t("btn.rc_auto"))
            self.btn_rc_auto.show()
        else:
            self.modal_text.setText(self.t("modal.rc_none_found"))
            self.modal_paths.hide()
            self.btn_rc_auto.hide()

        self.modal_overlay.show()
        self.modal_overlay.raise_()

    def on_rc_auto_clicked(self):
        if not self._rc_found or not self._rc_entry:
            return
        self.remove_rc_lines(self._rc_entry["id"], self._rc_found)

        home = os.path.expanduser("~")
        self.modal_text.setText(self.t("modal.rc_done"))
        self.modal_paths.setText("\n".join(p.replace(home, "~", 1) + ".bak-*" for p in self._rc_found))
        self.btn_rc_auto.hide()
        self._rc_found = None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = main_app()
    win.show()
    sys.exit(app.exec())
