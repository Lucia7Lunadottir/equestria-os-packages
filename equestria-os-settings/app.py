import glob
import importlib.util
import inspect
import json
import os
import subprocess
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QStackedWidget, QStyledItemDelegate,
    QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from base_module import BaseModule

SUPPORTED_LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]

CATEGORIES_ORDER = ["system", "software", "appearance"]
CATEGORY_KEYS = {
    "system": "category.system",
    "software": "category.software",
    "appearance": "category.appearance",
}

_ITEM_TYPE_CATEGORY = 1001
_ITEM_TYPE_MODULE = 1002


# ---------------------------------------------------------------------------
# Sidebar delegate
# ---------------------------------------------------------------------------

class SidebarDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        item_type = index.data(Qt.ItemDataRole.UserRole + 1)
        painter.save()

        if item_type == _ITEM_TYPE_CATEGORY:
            painter.fillRect(option.rect, QColor(40, 38, 58))
            painter.setPen(QColor(140, 130, 170))
            font = QFont(option.font)
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            text = index.data(Qt.ItemDataRole.DisplayRole).upper()
            rect = option.rect.adjusted(12, 0, -4, 0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        else:
            is_selected = bool(option.state & option.state.State_Selected)
            if is_selected:
                painter.fillRect(option.rect, QColor(203, 166, 247))
                painter.setPen(QColor(30, 30, 46))
            elif bool(option.state & option.state.State_MouseOver):
                painter.fillRect(option.rect, QColor(50, 47, 72))
                painter.setPen(QColor(220, 215, 240))
            else:
                painter.fillRect(option.rect, QColor(30, 28, 46))
                painter.setPen(QColor(200, 195, 220))

            font = QFont(option.font)
            font.setPointSize(11)
            font.setBold(is_selected)
            painter.setFont(font)

            icon = index.data(Qt.ItemDataRole.UserRole + 2) or ""
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""

            icon_rect = option.rect.adjusted(16, 0, 0, 0)
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             f"{icon}  {text}")

        painter.restore()

    def sizeHint(self, option, index):
        item_type = index.data(Qt.ItemDataRole.UserRole + 1)
        if item_type == _ITEM_TYPE_CATEGORY:
            return __import__('PyQt6.QtCore', fromlist=['QSize']).QSize(220, 30)
        return __import__('PyQt6.QtCore', fromlist=['QSize']).QSize(220, 40)


# ---------------------------------------------------------------------------
# Not-installed widget
# ---------------------------------------------------------------------------

class NotInstalledWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentPage")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        self._icon_lbl = QLabel("📦")
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")

        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("ModTitle")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hint_lbl = QLabel()
        self._hint_lbl.setObjectName("ModDesc")
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_lbl.setWordWrap(True)

        self._install_btn = QPushButton()
        self._install_btn.setObjectName("LaunchBtn")
        self._install_btn.setFixedWidth(220)

        layout.addStretch()
        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._title_lbl)
        layout.addWidget(self._hint_lbl)
        layout.addWidget(self._install_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def configure(self, title: str, hint: str, install_btn_text: str, pkg_name: str):
        self._title_lbl.setText(title)
        self._hint_lbl.setText(hint)
        self._install_btn.setText(install_btn_text)
        try:
            self._install_btn.clicked.disconnect()
        except Exception:
            pass
        pkg = pkg_name
        self._install_btn.clicked.connect(lambda: self._install(pkg))

    def _install(self, pkg: str):
        import shutil
        for term in [["konsole", "-e"], ["xterm", "-e"], ["gnome-terminal", "--"]]:
            if shutil.which(term[0]):
                subprocess.Popen(term + ["yay", "-S", pkg], start_new_session=True)
                return


# ---------------------------------------------------------------------------
# Launch widget (for complex apps)
# ---------------------------------------------------------------------------

class _StatusFetcher(QObject):
    status_ready = pyqtSignal(str)

    def __init__(self, fetch_fn, parent=None):
        super().__init__(parent)
        self._fn = fetch_fn

    def run(self):
        try:
            result = self._fn()
        except Exception:
            result = ""
        self.status_ready.emit(result)


class LaunchWidget(QWidget):
    def __init__(self, icon: str, title_key: str, desc_key: str,
                 binary: str, t_func, status_fn=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentPage")
        self._t = t_func
        self._binary = binary
        self._title_key = title_key
        self._desc_key = desc_key
        self._status_fn = status_fn

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)
        layout.setContentsMargins(60, 40, 60, 40)

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 52px; background: transparent;")

        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("ModTitle")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._desc_lbl = QLabel()
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_lbl.setWordWrap(True)

        self._status_box = QFrame()
        self._status_box.setObjectName("StatusBox")
        status_layout = QHBoxLayout(self._status_box)
        status_layout.setContentsMargins(16, 8, 16, 8)
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("StatusText")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self._status_lbl)

        self._launch_btn = QPushButton()
        self._launch_btn.setObjectName("LaunchBtn")
        self._launch_btn.setFixedWidth(280)
        self._launch_btn.clicked.connect(self._launch)

        layout.addStretch()
        layout.addWidget(icon_lbl)
        layout.addWidget(self._title_lbl)
        layout.addWidget(self._desc_lbl)
        layout.addWidget(self._status_box)
        layout.addWidget(self._launch_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        self._retranslate()

    def _retranslate(self):
        title = self._t(self._title_key)
        self._title_lbl.setText(title)
        self._desc_lbl.setText(self._t(self._desc_key))
        self._launch_btn.setText(self._t("launch.open_btn").replace("{0}", title))
        if not self._status_fn:
            self._status_lbl.hide()
            self._status_box.hide()
        else:
            self._status_lbl.setText(self._t("launch.status_loading"))

    def retranslate(self):
        self._retranslate()

    def refresh_status(self):
        if not self._status_fn:
            return
        self._status_lbl.setText(self._t("launch.status_loading"))
        fetcher = _StatusFetcher(self._status_fn)
        fetcher.status_ready.connect(self._status_lbl.setText)
        thread = threading.Thread(target=fetcher.run, daemon=True)
        thread.start()
        # Keep reference so GC doesn't collect it
        self._fetcher = fetcher

    def _launch(self):
        subprocess.Popen([self._binary], start_new_session=True)


# ---------------------------------------------------------------------------
# Welcome page
# ---------------------------------------------------------------------------

class WelcomePage(QWidget):
    def __init__(self, t_func, parent=None):
        super().__init__(parent)
        self._t = t_func
        self.setObjectName("ContentPage")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel("⚙")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 64px; background: transparent;")

        self._hint = QLabel(self._t("welcome.hint"))
        self._hint.setObjectName("ModDesc")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        layout.addWidget(lbl)
        layout.addWidget(self._hint)
        layout.addStretch()

    def retranslate(self):
        self._hint.setText(self._t("welcome.hint"))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class SettingsWindow(QMainWindow):
    def __init__(self, base_path: str):
        super().__init__()
        self.base_path = base_path
        self.setObjectName("root")
        self.setWindowTitle("Equestria OS Settings")
        self.resize(1200, 720)

        # --- Load font ---
        font_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        fid = QFontDatabase.addApplicationFont(font_path)
        families = QFontDatabase.applicationFontFamilies(fid)
        self._eq_font_family = families[0] if families else "Sans Serif"

        # --- Load locales ---
        self.langs: dict[str, dict] = self._load_locales()
        self.current_lang = self._detect_lang()

        # --- Load QSS ---
        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, encoding="utf-8") as f:
                qss = f.read().replace("{{BASE_PATH}}", base_path.replace("\\", "/").replace(" ", "%20"))
            self.setStyleSheet(qss)

        # --- Discover modules ---
        self._modules: list[BaseModule] = self._discover_modules()

        # --- Build UI ---
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        splitter.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentStack")
        self._welcome_page = WelcomePage(self.t)
        self._stack.addWidget(self._welcome_page)
        self._not_installed_widget = NotInstalledWidget()
        self._stack.addWidget(self._not_installed_widget)
        splitter.addWidget(self._stack)

        splitter.setSizes([220, 980])
        root_layout.addWidget(splitter)

        self._current_module: BaseModule | None = None
        self._widget_map: dict[str, QWidget] = {}

        # Select first selectable item
        self._select_first()

    # --- Locales ---

    def _load_locales(self) -> dict:
        langs = {}
        locales_dir = os.path.join(self.base_path, "locales")
        for path in sorted(glob.glob(os.path.join(locales_dir, "*.json"))):
            code = os.path.basename(path).removesuffix(".json")
            try:
                with open(path, encoding="utf-8") as f:
                    langs[code] = json.load(f)
            except Exception as e:
                print(f"[settings] locale load failed: {path}: {e}")
        return langs

    def _detect_lang(self) -> str:
        for env in ("LANGUAGE", "LANG", "LC_ALL", "LC_MESSAGES"):
            code = (os.getenv(env) or "")[:2]
            if code in self.langs:
                return code
        return "en"

    def t(self, key: str) -> str:
        return (
            self.langs.get(self.current_lang, {}).get(key)
            or self.langs.get("en", {}).get(key, key)
        )

    # --- Module discovery ---

    def _discover_modules(self) -> list[BaseModule]:
        modules = []
        pattern = os.path.join(self.base_path, "modules", "mod_*.py")
        for path in sorted(glob.glob(pattern)):
            module_name = os.path.basename(path).removesuffix(".py")
            try:
                spec = importlib.util.spec_from_file_location(module_name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for _, cls in inspect.getmembers(mod, inspect.isclass):
                    if (issubclass(cls, BaseModule) and cls is not BaseModule
                            and cls.module_id):
                        instance = cls(self.t, self.base_path)
                        modules.append(instance)
                        break
            except Exception as e:
                print(f"[settings] failed to load module {path}: {e}")
        return modules

    # --- Header ---

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(54)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        title = QLabel(self.t("app.title"))
        title.setObjectName("AppTitle")
        f = QFont(self._eq_font_family)
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)
        self._app_title_lbl = title

        layout.addStretch()

        # Language buttons
        self._lang_btn_map: dict[str, QPushButton] = {}
        lang_layout = QHBoxLayout()
        lang_layout.setSpacing(4)
        for code in sorted(self.langs.keys()):
            btn = QPushButton(code.upper())
            btn.setObjectName("LangBtn")
            btn.setFixedSize(30, 24)
            btn.setProperty("active", code == self.current_lang)
            btn.clicked.connect(lambda _, c=code: self._apply_language(c))
            lang_layout.addWidget(btn)
            self._lang_btn_map[code] = btn
        layout.addLayout(lang_layout)

        layout.addSpacing(12)

        kde_btn = QPushButton(self.t("header.kde_btn"))
        kde_btn.setObjectName("KDESettingsBtn")
        kde_btn.clicked.connect(self._launch_kde_settings)
        layout.addWidget(kde_btn)
        self._kde_btn = kde_btn

        return header

    # --- Sidebar ---

    def _build_sidebar(self) -> QWidget:
        container = QWidget()
        container.setObjectName("Sidebar")
        container.setFixedWidth(220)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar_list = QListWidget()
        self._sidebar_list.setObjectName("SidebarList")
        self._sidebar_list.setItemDelegate(SidebarDelegate(self._sidebar_list))
        self._sidebar_list.setMouseTracking(True)
        self._sidebar_list.currentRowChanged.connect(self._on_sidebar_selected)

        # Group modules by category in defined order
        by_cat: dict[str, list[BaseModule]] = {c: [] for c in CATEGORIES_ORDER}
        for m in self._modules:
            cat = m.category if m.category in by_cat else "system"
            by_cat[cat].append(m)
        for cat in CATEGORIES_ORDER:
            by_cat[cat].sort(key=lambda m: m.sort_order)

        self._sidebar_row_to_module: dict[int, BaseModule | None] = {}
        row = 0
        for cat in CATEGORIES_ORDER:
            mods = by_cat[cat]
            if not mods:
                continue
            # Category header
            cat_item = QListWidgetItem(self.t(CATEGORY_KEYS[cat]))
            cat_item.setData(Qt.ItemDataRole.UserRole + 1, _ITEM_TYPE_CATEGORY)
            cat_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._sidebar_list.addItem(cat_item)
            self._sidebar_row_to_module[row] = None
            row += 1

            for m in mods:
                mod_item = QListWidgetItem(self.t(m.display_name_key))
                mod_item.setData(Qt.ItemDataRole.UserRole + 1, _ITEM_TYPE_MODULE)
                mod_item.setData(Qt.ItemDataRole.UserRole + 2, m.icon)
                mod_item.setData(Qt.ItemDataRole.UserRole, m)
                self._sidebar_list.addItem(mod_item)
                self._sidebar_row_to_module[row] = m
                row += 1

        layout.addWidget(self._sidebar_list)
        return container

    def _select_first(self):
        for i in range(self._sidebar_list.count()):
            item = self._sidebar_list.item(i)
            if item and (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                self._sidebar_list.setCurrentRow(i)
                break

    # --- Navigation ---

    def _on_sidebar_selected(self, row: int):
        module = self._sidebar_row_to_module.get(row)
        if module is None:
            return

        if self._current_module:
            self._current_module.on_hidden()

        if not module.is_available():
            self._not_installed_widget.configure(
                title=self.t(module.display_name_key),
                hint=self.t("launch.install_hint").replace("{0}", module.package_name or module.module_id),
                install_btn_text=self.t("launch.install_btn"),
                pkg_name=module.package_name or module.module_id,
            )
            self._stack.setCurrentWidget(self._not_installed_widget)
            self._current_module = None
            return

        # Build or retrieve cached widget
        if module.module_id not in self._widget_map:
            widget = module.get_widget()
            self._stack.addWidget(widget)
            self._widget_map[module.module_id] = widget

        self._stack.setCurrentWidget(self._widget_map[module.module_id])
        self._current_module = module
        module.on_shown()

    # --- Language ---

    def _apply_language(self, code: str):
        self.current_lang = code

        # Update lang button states
        for c, btn in self._lang_btn_map.items():
            btn.setProperty("active", c == code)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # Retranslate header
        self._app_title_lbl.setText(self.t("app.title"))
        self._kde_btn.setText(self.t("header.kde_btn"))
        self._welcome_page.retranslate()

        # Re-group modules for sidebar retranslation
        by_cat = {c: [] for c in CATEGORIES_ORDER}
        for m in self._modules:
            cat = m.category if m.category in by_cat else "system"
            by_cat[cat].append(m)
        for cat in CATEGORIES_ORDER:
            by_cat[cat].sort(key=lambda m: m.sort_order)

        row = 0
        for cat in CATEGORIES_ORDER:
            mods = by_cat[cat]
            if not mods:
                continue
            item = self._sidebar_list.item(row)
            if item:
                item.setText(self.t(CATEGORY_KEYS[cat]))
            row += 1
            for m in mods:
                item = self._sidebar_list.item(row)
                if item:
                    item.setText(self.t(m.display_name_key))
                row += 1

        # Retranslate modules (pass current_lang so embedded apps can forward it)
        for m in self._modules:
            m.current_lang = code
            m.apply_language()

    # --- KDE Settings ---

    def _launch_kde_settings(self):
        for binary in ["systemsettings", "systemsettings5", "kcontrol"]:
            import shutil
            if shutil.which(binary):
                subprocess.Popen([binary], start_new_session=True)
                return
