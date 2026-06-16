"""
EmbeddedAppModule — loads an existing Equestria OS app and embeds its
QMainWindow directly into the settings panel, without opening a new window.

How it works
------------
Uses a transparent sys.meta_path redirection hook to isolate colliding internal 
module names (backend, ui_pkg, etc.) under unique prefixed names permanently.
This ensures background threads never lose access to their parent modules.
"""

import importlib.util
import inspect
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QLabel, QPushButton, QSizePolicy, QWidget

from base_module import BaseModule

# Module names that are reused across different apps
_COMMON_NAMES = [
    "ui_pkg", "ui_services", "ui_software", "ui_mirrors", "ui",
    "backend", "disk_backend", "models", "utils", "workers",
    "core", "privilege", "hooks", "screenshot", "plasma_utils",
    "auto_restore", "restore_system",
    "settings", "settings_dialog",
]

_LANG_METHOD_1ARG = ("change_lang", "set_language", "_change_lang")


class EmbeddedAppRedirectHook:
    """Transparently intercepts and isolates multi-app colliding module imports."""
    def __init__(self, lib_dir, unique_key):
        self.lib_dir = os.path.abspath(lib_dir)
        self.unique_key = unique_key

    def find_spec(self, fullname, path, target=None):
        if fullname in _COMMON_NAMES:
            frame = inspect.currentframe()
            is_from_app = False
            while frame:
                filename = frame.f_code.co_filename
                if filename:
                    abs_filename = os.path.abspath(filename)
                    if abs_filename.startswith(self.lib_dir):
                        is_from_app = True
                        break
                frame = frame.f_back

            if is_from_app:
                redirected_name = f"_emb_{self.unique_key}_{fullname}"
                if redirected_name in sys.modules:
                    return sys.modules[redirected_name].__spec__
                
                target_file = os.path.join(self.lib_dir, f"{fullname}.py")
                if os.path.exists(target_file):
                    return importlib.util.spec_from_file_location(redirected_name, target_file)
        return None


def _load_app_module(lib_dir: str, main_file: str, unique_key: str):
    """Load an app module securely using the meta_path redirection hook."""
    main_path = os.path.join(lib_dir, main_file)
    if not os.path.exists(main_path):
        raise FileNotFoundError(f"App main file not found: {main_path}")

    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    # Register our meta path isolation hook permanently for this module
    hook_exists = any(
        isinstance(h, EmbeddedAppRedirectHook) and h.unique_key == unique_key 
        for h in sys.meta_path
    )
    if not hook_exists:
        sys.meta_path.insert(0, EmbeddedAppRedirectHook(lib_dir, unique_key))

    redirected_main = f"_emb_{unique_key}_main"
    if redirected_main in sys.modules:
        return sys.modules[redirected_main]

    spec = importlib.util.spec_from_file_location(redirected_main, main_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[redirected_main] = mod
    spec.loader.exec_module(mod)
    return mod


class EmbeddedAppModule(BaseModule):
    lib_dir: str = ""
    main_file: str = "main.py"
    main_class: str = ""

    def is_available(self) -> bool:
        """Returns False if the target directory in /opt does not exist."""
        if not self.lib_dir or not os.path.isdir(self.lib_dir):
            return False
        return super().is_available()

    def build_widget(self) -> QWidget:
        lib = self.lib_dir
        if not lib or not os.path.isdir(lib):
            raise FileNotFoundError(f"Library directory not found: {lib!r}")

        mod = _load_app_module(lib, self.main_file, self.module_id)
        cls = getattr(mod, self.main_class)

        self._win = cls()
        self._win.setWindowFlag(Qt.WindowType.Widget, True)

        self._apply_embedded_style()
        self._inject_checkmark_icons()
        self._hide_lang_ui()

        from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout
        self._win.setMinimumSize(0, 0)
        self._win.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        container = QWidget()
        container.setObjectName("ContentPage")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._win)
        return container

    def _apply_embedded_style(self) -> None:
        if self._win.styleSheet():
            return

        qss_path = os.path.join(self.lib_dir, "style.qss")
        if not os.path.exists(qss_path):
            return
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                raw = f.read()

            base = self.lib_dir.replace("\\", "/").replace(" ", "%20")
            raw = raw.replace("{{BASE_PATH}}", base)

            svg_path = os.path.join(self.lib_dir, "check_mark.svg").replace(" ", "%20")
            raw = raw.replace("{{CHECKMARK_SVG_PATH}}", svg_path)

            font_path = os.path.join(self.lib_dir, "equestria_cyrillic.ttf")
            title_font = "sans-serif"
            if os.path.exists(font_path):
                from PyQt6.QtGui import QFontDatabase
                fid = QFontDatabase.addApplicationFont(font_path)
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    title_font = families[0]
            raw = raw.replace("{{TITLE_FONT}}", f'"{title_font}"')

            self._win.setStyleSheet(raw)
        except OSError:
            pass

    def _inject_checkmark_icons(self) -> None:
        settings_dir = os.path.dirname(os.path.abspath(__file__))
        icons_dir = os.path.join(settings_dir, "icons")
        cb_u  = os.path.join(icons_dir, "cb_unchecked.svg")
        cb_uh = os.path.join(icons_dir, "cb_unchecked_hover.svg")
        cb_c  = os.path.join(icons_dir, "cb_checked.svg")

        if not os.path.exists(cb_c):
            return

        def _q(p: str) -> str:
            return p.replace("\\", "/").replace(" ", "%20")

        u, uh, c = _q(cb_u), _q(cb_uh), _q(cb_c)

        checkboxes = self._win.findChildren(QCheckBox)
        if not checkboxes:
            return

        win_append = ""
        for cb in checkboxes:
            obj = cb.objectName()
            prefix = f"QCheckBox#{obj}" if obj else "QCheckBox"
            win_append += (
                f"{prefix}::indicator{{width:18px;height:18px;"
                f"image:url({u});background-color:transparent;border:none;}}"
                f"{prefix}::indicator:hover{{image:url({uh});"
                f"background-color:transparent;border:none;}}"
                f"{prefix}::indicator:checked{{image:url({c});"
                f"background-color:transparent;border:none;}}"
            )
            cb.setStyleSheet(cb.styleSheet() + win_append)

        self._win.setStyleSheet(self._win.styleSheet() + win_append)

    def _hide_lang_ui(self) -> None:
        win = self._win
        central = win.centralWidget() if callable(getattr(win, "centralWidget", None)) else None

        def _collapse(widget: QWidget) -> None:
            widget.hide()
            widget.setMaximumSize(0, 0)
            widget.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
            )

        for holder in (win, getattr(win, "ui", None)):
            if holder is None:
                continue
            container = getattr(holder, "lang_container", None)
            if isinstance(container, QWidget):
                _collapse(container)

        for btn in win.findChildren(QPushButton):
            is_lang = (
                btn.objectName() == "LangBtn"
                or btn.property("cssClass") == "lang-button"
                or btn.property("lang") is not None
            )
            if not is_lang:
                continue

            parent = btn.parent()
            if (
                parent is not None
                and parent is not win
                and parent is not central
                and isinstance(parent, QWidget)
                and not parent.findChildren(QLabel)
            ):
                _collapse(parent)
            else:
                _collapse(btn)

    def apply_language(self) -> None:
        code = getattr(self, "current_lang", "en")
        if not getattr(self, "_win", None):
            return

        win = self._win

        for name in _LANG_METHOD_1ARG:
            method = getattr(win, name, None)
            if callable(method):
                try:
                    method(code)
                except Exception:
                    pass
                return

        method = getattr(win, "change_language", None)
        if callable(method):
            try:
                sig = inspect.signature(method)
                required = [
                    p for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                ]
                if required:
                    method(code)
                else:
                    for btn in win.findChildren(QPushButton):
                        if btn.property("lang") == code:
                            btn.click()
                            break
            except Exception:
                pass
            return

    def on_shown(self) -> None:
        pass