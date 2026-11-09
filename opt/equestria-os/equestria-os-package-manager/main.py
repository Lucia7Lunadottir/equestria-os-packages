import sys, os, re, time, subprocess, threading, shutil, shlex, json
import importlib.metadata as importlib_metadata
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QComboBox
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui_pkg import Ui_PackageManager, PackageRow
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit import live_i18n
from equestria_kit.widgets import font_families

# Переводы лежат в locales/<язык>.json рядом с программой (ключ -> текст)
CATALOG = live_i18n.Catalog("equestria-os-package-manager", __file__)

# .deb/.rpm поставленные через equestria-installer (foreign_bridge.py) — не
# трогают базу pacman, свой манифест с полным списком файлов на пакет
FOREIGN_MANIFEST_DIR = "/var/lib/equestria-installer/foreign"
FOREIGN_BRIDGE = "/usr/lib/equestria-installer/foreign_bridge.py"

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
        self.size_bytes = 0  # installed size, filled in by refresh_packages(); 0 = unknown
        self.size_text = ""  # localized display string, filled in by render_page()


_BINARY_SIZE_UNITS = {"B": 1, "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3, "TIB": 1024 ** 4}
_DECIMAL_SIZE_UNITS = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4}


def _parse_size(text, units):
    """"12.34 MiB" / "12.34 MB" -> bytes. Used to turn pacman's (binary, MiB)
    and flatpak's (decimal, MB) own human-readable size output back into a
    plain byte count, so every source can be redisplayed through the same
    fmt_size() regardless of which tool originally reported it."""
    parts = text.split()
    if len(parts) != 2:
        return 0
    try:
        value = float(parts[0])
    except ValueError:
        return 0
    multiplier = units.get(parts[1].upper())
    return int(value * multiplier) if multiplier else 0

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
            families = font_families(f_path)
            if families:
                self.title_label.setFont(QFont(families[0], 28, QFont.Weight.Bold))
                self.modal_title.setFont(QFont(families[0], 22, QFont.Weight.Bold))

        q_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(q_path): kit_qt.style(self, open(q_path, "r").read())

        icon_path = os.path.join(self.base_path, "equestria-os-package-manager.png")
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))

        QApplication.setDesktopFileName("equestria-os-package-manager")


        self.current_lang = CATALOG.lang or "en"

        self.all_packages = []
        self.filtered_packages = []
        self.current_page = 1
        self.items_per_page = 50
        self.pkg_to_delete = None
        self.leftover_paths = []
        self.leftover_size = 0
        self._rc_entry = None
        self._rc_found = None

        self.setup_logic()
        self.apply_localization()
        self.refresh_packages()

    def t(self, key):
        return str(CATALOG.tr(key))

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
        self.btn_prev_page.clicked.connect(self.go_prev_page)
        self.btn_next_page.clicked.connect(self.go_next_page)

        self.btn_confirm_cancel.clicked.connect(self.modal_overlay.hide)
        self.btn_confirm_delete.clicked.connect(self.execute_uninstall)
        self.chk_pip_ack.switch.toggled.connect(self.btn_confirm_delete.setEnabled)
        self.btn_rc_auto.clicked.connect(self.on_rc_auto_clicked)

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
            lambda i: self.change_lang(self.lang_combo.itemData(i)))
        self.lang_layout.addWidget(self.lang_combo)

    def resizeEvent(self, event):
        self.modal_overlay.resize(event.size())
        super().resizeEvent(event)

    def change_lang(self, lang):
        self.current_lang = CATALOG.set_language(lang) or lang  # ещё и сохраняет выбор
        idx = self.lang_combo.findData(lang)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
        self.apply_localization()

    def apply_localization(self):
        title = self.t("ui.title")
        self.title_label.setText(title)
        self.setWindowTitle(title)

        self.loading_lbl.setText(self.t("ui.loading"))
        self.modal_title.setText(self.t("modal.title"))

        self.category_dropdown.blockSignals(True)
        self.category_dropdown.clear()

        self.category_dropdown.addItems([
            self.t("cat.all"), self.t("cat.software"), self.t("cat.drivers"),
            self.t("cat.aur"), "Flatpak", "Snap", self.t("cat.pip"), self.t("cat.curl"),
            self.t("cat.foreign")
        ])
        self.category_dropdown.blockSignals(False)

        self.btn_confirm_cancel.setText(self.t("btn.cancel"))
        self.btn_confirm_delete.setText(self.t("btn.delete"))
        if self.chk_delete_data.isVisible():
            self.chk_delete_data.setText(self.t("modal.data").format(self.fmt_size(self.leftover_size)))

        self.btn_prev_page.setText(self.t("ui.prev_page"))
        self.btn_next_page.setText(self.t("ui.next_page"))

        # apply_filters() re-renders the current page from scratch (fresh
        # rows with the new language's texts), so there's no separate old
        # widgets to relabel here.
        self.apply_filters()

    @staticmethod
    def _fetch_pacman():
        r = subprocess.run(["pacman", "-Qnq"], capture_output=True, text=True)
        return [PackageData(l.strip(), "pacman") for l in r.stdout.splitlines()]

    @staticmethod
    def _fetch_aur():
        r = subprocess.run(["yay", "-Qmq"], capture_output=True, text=True)
        return [PackageData(l.strip(), "aur") for l in r.stdout.splitlines()]

    @staticmethod
    def _fetch_flatpak():
        out = []
        try:
            # LC_ALL=C: the "size" column comes back as a plain, English
            # "12.5 MB" — locale-independent and parseable by _parse_size.
            r = subprocess.run(["flatpak", "list", "--app",
                                 "--columns=name,application,description,size"],
                                capture_output=True, text=True,
                                env={**os.environ, "LC_ALL": "C"})
            if r.returncode == 0:
                for l in r.stdout.splitlines():
                    parts = l.split("\t")
                    if len(parts) >= 2:
                        desc = parts[2].strip() if len(parts) >= 3 else ""
                        pkg = PackageData(parts[0].strip(), "flatpak",
                                           app_id=parts[1].strip(),
                                           description=desc, icon_name=parts[1].strip())
                        if len(parts) >= 4:
                            pkg.size_bytes = _parse_size(parts[3].strip(), _DECIMAL_SIZE_UNITS)
                        out.append(pkg)
        except FileNotFoundError:
            pass
        return out

    @staticmethod
    def _fetch_snap():
        out = []
        try:
            r = subprocess.run(["snap", "list"], capture_output=True, text=True)
            if r.returncode == 0:
                for l in r.stdout.splitlines()[1:]:
                    parts = l.split()
                    if parts:
                        pkg = PackageData(parts[0], "snap")
                        try:
                            du = subprocess.run(["du", "-sb", f"/snap/{parts[0]}/current"],
                                                 capture_output=True, text=True)
                            if du.returncode == 0:
                                pkg.size_bytes = int(du.stdout.split()[0])
                        except (OSError, ValueError, IndexError):
                            pass
                        out.append(pkg)
        except FileNotFoundError:
            pass
        return out

    @staticmethod
    def _fetch_pip_list():
        names, out = [], []
        try:
            r = subprocess.run(["pip", "list", "--user", "--format=freeze"],
                                capture_output=True, text=True)
            if r.returncode == 0:
                for l in r.stdout.splitlines():
                    if "==" in l:
                        name = l.split("==")[0].strip()
                        names.append(name)
                        out.append(PackageData(name, "pip", icon_name="text-x-python"))
        except FileNotFoundError:
            pass
        return names, out

    def refresh_packages(self):
        def _fetch():
            pkgs = []

            # pacman/AUR/flatpak/snap/pip listings don't depend on each
            # other — running them concurrently instead of one after another
            # cuts wall-clock time to roughly the slowest single call instead
            # of their sum (this loop used to take several seconds on a
            # system with a couple thousand installed packages).
            with ThreadPoolExecutor(max_workers=5) as pool:
                f_pacman = pool.submit(self._fetch_pacman)
                f_aur = pool.submit(self._fetch_aur)
                f_flatpak = pool.submit(self._fetch_flatpak)
                f_snap = pool.submit(self._fetch_snap)
                f_pip = pool.submit(self._fetch_pip_list)

                pkgs += f_pacman.result()
                pkgs += f_aur.result()
                pkgs += f_flatpak.result()
                pkgs += f_snap.result()
                pip_names, pip_pkgs = f_pip.result()
                pkgs += pip_pkgs

            for entry in CURL_INSTALLS:
                if os.path.isdir(os.path.expanduser(entry["marker"])):
                    pkg = PackageData(entry["name"], "curl", app_id=entry["id"],
                                       description=entry.get("desc", ""),
                                       icon_name=entry.get("icon"))
                    pkg.size_bytes = sum(self._path_size(os.path.expanduser(p))
                                          for p in entry.get("remove_paths", []))
                    pkgs.append(pkg)

            if os.path.isdir(FOREIGN_MANIFEST_DIR):
                for fname in os.listdir(FOREIGN_MANIFEST_DIR):
                    if not fname.endswith(".json"):
                        continue
                    try:
                        with open(os.path.join(FOREIGN_MANIFEST_DIR, fname)) as fh:
                            manifest = json.load(fh)
                        pkg = PackageData(
                            manifest["name"], manifest.get("format", "deb"),
                            description=f"v{manifest.get('version', '?')} • "
                                        f"{len(manifest.get('files', []))} files")
                        total = 0
                        for f in manifest.get("files", []):
                            try:
                                total += os.lstat(f).st_size
                            except OSError:
                                pass
                        pkg.size_bytes = total
                        pkg.icon_name = self._foreign_pkg_icon(manifest.get("files", []))
                        pkgs.append(pkg)
                    except (OSError, json.JSONDecodeError, KeyError):
                        pass

            # --- Описания и иконки (pkgdesc от pacman/AUR — то же, что даёт PKGBUILD,
            # но взятое из уже установленного пакета, а не из исходников) ---
            # Each enricher only writes to its own subset of pkgs (pacman/aur
            # vs pip entries), so running them concurrently is safe.
            with ThreadPoolExecutor(max_workers=2) as pool:
                f1 = pool.submit(self._enrich_pacman, pkgs)
                f2 = pool.submit(self._enrich_pip, pkgs, pip_names)
                f1.result()
                f2.result()

            self.fetch_finished.emit(pkgs)

        threading.Thread(target=_fetch, daemon=True).start()

    @staticmethod
    def _foreign_pkg_icon(files):
        """Same idea as _enrich_pacman's icon lookup, but for .deb/.rpm
        packages: they never go through pacman, so there's no "-Qo" owner
        query to use — instead read Icon= straight out of whichever
        .desktop file the manifest says this package installed."""
        for f in files:
            if not f.endswith(".desktop"):
                continue
            try:
                with open(f, "r", errors="ignore") as fh:
                    for line in fh:
                        if line.startswith("Icon="):
                            return line.split("=", 1)[1].strip()
            except OSError:
                pass
        return None

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
                elif key == "Installed Size" and name in targets:
                    targets[name].size_bytes = _parse_size(val, _BINARY_SIZE_UNITS)
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
        # importlib.metadata reads the same installed dist-info/RECORD files
        # `pip show -f` would parse from text, but in-process — no subprocess
        # spawn, no output to parse. Measured ~5x faster for ~50 packages
        # (dominated by stat()-ing each package's files either way) than
        # shelling out to `pip show -f`, which was doubling this app's
        # startup fetch time.
        if not pip_names:
            return
        targets = {p.name: p for p in pkgs if p.source == "pip"}
        for name in pip_names:
            if name not in targets:
                continue
            try:
                dist = importlib_metadata.distribution(name)
            except importlib_metadata.PackageNotFoundError:
                continue

            summary = dist.metadata.get("Summary")
            if summary:
                targets[name].description = summary

            total = 0
            for f in (dist.files or []):
                try:
                    total += os.lstat(str(dist.locate_file(f))).st_size
                except OSError:
                    pass
            targets[name].size_bytes = total

    def on_fetch_finished(self, pkgs):
        self.loading_lbl.hide()
        self.scroll_area.show()
        self.pagination_widget.show()
        self.all_packages = pkgs
        self.apply_filters()

    def apply_filters(self):
        """Recomputes which packages match the search/category filters and
        jumps back to page 1 of the results. Rendering itself is
        render_page()'s job — a system can easily have 1000+ installed
        packages across pacman/AUR/flatpak/pip/etc, and building a widget
        per package on every keystroke is exactly what used to make this
        list slow to load and janky to filter."""
        query = self.search_field.text().lower()
        cat = self.category_dropdown.currentText()

        def matches(pkg):
            text_match = not query or query in pkg.name.lower()
            cat_match = (cat == self.t("cat.all") or
                         (cat == self.t("cat.software") and pkg.category == "Software") or
                         (cat == self.t("cat.drivers") and pkg.category == "Drivers") or
                         (cat == self.t("cat.aur") and pkg.source == "aur") or
                         (cat == "Flatpak" and pkg.source == "flatpak") or
                         (cat == "Snap" and pkg.source == "snap") or
                         (cat == self.t("cat.pip") and pkg.source == "pip") or
                         (cat == self.t("cat.curl") and pkg.source == "curl") or
                         (cat == self.t("cat.foreign") and pkg.source in ("deb", "rpm")))
            return text_match and cat_match

        self.filtered_packages = [p for p in self.all_packages if matches(p)]
        self.current_page = 1
        self.render_page()

    def render_page(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        total = len(self.filtered_packages)
        pages = max(1, (total + self.items_per_page - 1) // self.items_per_page)
        self.current_page = min(max(self.current_page, 1), pages)
        start = (self.current_page - 1) * self.items_per_page

        for pkg in self.filtered_packages[start:start + self.items_per_page]:
            pkg.size_text = self.fmt_size(pkg.size_bytes) if pkg.size_bytes else ""
            row = PackageRow(pkg, self.t("btn.delete"), self.show_confirm)
            self.list_layout.addWidget(row)

        self.lbl_page_info.setText(
            self.t("ui.page_info")
                .replace("{0}", str(self.current_page))
                .replace("{1}", str(pages))
                .replace("{2}", str(total)))
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < pages)

    def go_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.render_page()
            self.scroll_area.verticalScrollBar().setValue(0)

    def go_next_page(self):
        pages = max(1, (len(self.filtered_packages) + self.items_per_page - 1) // self.items_per_page)
        if self.current_page < pages:
            self.current_page += 1
            self.render_page()
            self.scroll_area.verticalScrollBar().setValue(0)

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
        elif self.pkg_to_delete.source in ("deb", "rpm"):
            cmd = f"pkexec python3 {shlex.quote(FOREIGN_BRIDGE)} uninstall {shlex.quote(pkg_name)}"
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
            self.apply_filters()

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
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    win = main_app()
    win.show()
    sys.exit(app.exec())
