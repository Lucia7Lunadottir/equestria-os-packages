"""
EmbeddedAppModule — loads an existing Equestria OS app and embeds its
QMainWindow directly into the settings panel, without opening a new window.

How it works
------------
1. The target app's lib dir is added to sys.path temporarily.
2. The app's main.py is loaded via importlib with a unique module name so it
   doesn't collide with other apps that share file names (ui_pkg, backend…).
3. Sub-modules that commonly share names across apps are stashed from
   sys.modules before loading and restored afterwards, preventing cross-app
   import pollution.
4. The main window class is instantiated (show() is never called).
5. Qt.WindowType.Widget is set so the window renders as an in-process widget
   without OS decorations.
6. The embedded app's own language selector UI is hidden (we control language
   from the settings panel header instead).
7. The window is returned and added to the QStackedWidget by the caller.

Language switching
------------------
apply_language() calls the embedded app's own retranslation method directly,
handling all the different signatures used across Equestria OS apps:

  change_lang(code)      — save-point, services-manager, package-manager
  set_language(code)     — task-panel-changer, character-theme
  _change_lang(code)     — disk-manager
  change_language(code)  — tutorial
  change_language()      — software-center (reads self.sender().property("lang"))
                           handled by clicking the matching hidden button
"""

import importlib.util
import inspect
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QLabel, QPushButton, QSizePolicy, QWidget

from base_module import BaseModule

# Module names that are reused across different apps — stash them before
# loading each app so they don't leak between embedded instances.
_COMMON_NAMES = [
    "ui_pkg", "ui_services", "ui_software", "ui_mirrors", "ui",
    "backend", "disk_backend", "models", "utils", "workers",
    "core", "privilege", "hooks", "screenshot", "plasma_utils",
    "auto_restore", "restore_system",
]

# Direct-call method names tried in order (all accept a single lang-code arg).
_LANG_METHOD_1ARG = ("change_lang", "set_language", "_change_lang")


def _load_app_module(lib_dir: str, main_file: str, unique_key: str):
    """
    Load an app module from lib_dir/main_file in isolation.

    Returns the loaded module object.
    """
    main_path = os.path.join(lib_dir, main_file)
    if not os.path.exists(main_path):
        raise FileNotFoundError(f"App main file not found: {main_path}")

    # 1. Stash conflicting modules that might shadow the app's own files
    stashed: dict = {}
    for name in _COMMON_NAMES:
        if name in sys.modules:
            stashed[name] = sys.modules.pop(name)

    # 2. Put the app's dir first on sys.path
    inserted = lib_dir not in sys.path
    if inserted:
        sys.path.insert(0, lib_dir)

    try:
        # 3. Load under a unique name so "main" from two apps don't collide
        spec = importlib.util.spec_from_file_location(
            f"_emb_{unique_key}", main_path
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"_emb_{unique_key}"] = mod
        spec.loader.exec_module(mod)

        # 4. Re-key any freshly loaded common modules under the unique prefix
        for name in _COMMON_NAMES:
            if name in sys.modules:
                sys.modules[f"_emb_{unique_key}_{name}"] = sys.modules.pop(name)

    finally:
        if inserted and lib_dir in sys.path:
            sys.path.remove(lib_dir)
        # Restore original common modules
        sys.modules.update(stashed)

    return mod


class EmbeddedAppModule(BaseModule):
    """
    Subclass this to embed an existing app into the settings panel.

    Required class attributes (in addition to BaseModule ones):
        lib_dir    — installed lib path, e.g. "/usr/lib/equestria-os-save-point"
        main_file  — entry file, usually "main.py"
        main_class — name of the QMainWindow subclass inside that file
    """

    lib_dir: str = ""
    main_file: str = "main.py"
    main_class: str = ""

    def build_widget(self) -> QWidget:
        lib = self.lib_dir
        if not lib or not os.path.isdir(lib):
            raise FileNotFoundError(f"Library directory not found: {lib!r}")

        mod = _load_app_module(lib, self.main_file, self.module_id)
        cls = getattr(mod, self.main_class)

        # Instantiate without showing
        self._win = cls()

        # Embed as an in-process widget (no OS window decorations)
        self._win.setWindowFlag(Qt.WindowType.Widget, True)

        # Apply the embedded app's own stylesheet.  Normally loaded via
        # app.setStyleSheet() in main(), but we never call main(), so we apply
        # it directly to the window widget instead.
        self._apply_embedded_style()

        # Ensure all QCheckBox widgets in the embedded app use the settings
        # app's custom SVG checkmark icons.  Appending same-specificity rules
        # after the app's own stylesheet means they win via cascade order.
        self._inject_checkmark_icons()

        # Remove the embedded app's own language selector so it doesn't
        # duplicate the language buttons already in the settings header.
        self._hide_lang_ui()

        return self._win

    # ── Style injection ───────────────────────────────────────────────────────

    def _apply_embedded_style(self) -> None:
        """
        Load the embedded app's own style.qss and apply it to the window.

        Normally the app's main() calls app.setStyleSheet(...), but since we
        never call main(), we apply the stylesheet directly to the window so
        the app's own dark theme and widget styles are preserved.

        If the app's __init__ already applied a stylesheet (with proper
        placeholder substitution), we skip this step to avoid overwriting it
        with the raw unsubstituted file content.
        """
        # App already applied its own correctly-substituted stylesheet
        if self._win.styleSheet():
            return

        qss_path = os.path.join(self.lib_dir, "style.qss")
        if not os.path.exists(qss_path):
            return
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                raw = f.read()

            # Substitute known placeholders so url() paths and fonts resolve
            base = self.lib_dir.replace("\\", "/").replace(" ", "%20")
            raw = raw.replace("{{BASE_PATH}}", base)

            # CHECKMARK_SVG_PATH — used by swap manager and others
            svg_path = os.path.join(self.lib_dir, "check_mark.svg").replace(" ", "%20")
            raw = raw.replace("{{CHECKMARK_SVG_PATH}}", svg_path)

            # TITLE_FONT — leave as sans-serif fallback if font not found
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

    # ── Checkmark icon injection ──────────────────────────────────────────────

    def _inject_checkmark_icons(self) -> None:
        """
        Append custom SVG checkmark rules to the embedded app's stylesheet so
        all QCheckBox widgets use the settings app's icon set.

        Strategy: for each QCheckBox found in the embedded window, generate
        rules with the SAME CSS specificity as any existing indicator rules
        (e.g. QCheckBox#Name::indicator) but placed LATER in the stylesheet.
        In Qt QSS, equal-specificity rules resolve by source order — the later
        rule wins.  This overrides patterns like ``image: url(none)`` without
        needing !important (unsupported in Qt QSS).
        """
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

        extra_parts: list[str] = []
        seen: set[str] = set()

        for cb in self._win.findChildren(QCheckBox):
            name = cb.objectName()
            selector = f"QCheckBox#{name}" if name else "QCheckBox"
            if selector in seen:
                continue
            seen.add(selector)
            extra_parts.append(f"""
{selector}::indicator {{
    width: 18px; height: 18px;
    image: url({u});
    background-color: transparent;
    border: none;
}}
{selector}::indicator:hover {{
    image: url({uh});
    background-color: transparent;
    border: none;
}}
{selector}::indicator:checked {{
    image: url({c});
    background-color: transparent;
    border: none;
}}""")

        if not extra_parts:
            return

        self._win.setStyleSheet(self._win.styleSheet() + "\n" + "\n".join(extra_parts))

    # ── Language UI hiding ────────────────────────────────────────────────────

    def _hide_lang_ui(self) -> None:
        """
        Hide (and collapse) every language-selector widget inside the embedded
        app so the user only sees the settings panel's own language buttons.

        Covers all patterns used across Equestria OS apps:
          • QWidget named lang_container on self.ui or the window itself
          • QPushButton with objectName "LangBtn"
          • QPushButton with property cssClass = "lang-button"
          • QPushButton with property lang = <code>  (software-center)
        """
        win = self._win
        central = win.centralWidget() if callable(getattr(win, "centralWidget", None)) else None

        def _collapse(widget: QWidget) -> None:
            widget.hide()
            widget.setMaximumSize(0, 0)
            widget.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
            )

        # 1. Try dedicated lang_container widget (task-panel-changer, character-theme)
        for holder in (win, getattr(win, "ui", None)):
            if holder is None:
                continue
            container = getattr(holder, "lang_container", None)
            if isinstance(container, QWidget):
                _collapse(container)

        # 2. Individual language buttons — covers any pattern not caught above
        for btn in win.findChildren(QPushButton):
            is_lang = (
                btn.objectName() == "LangBtn"
                or btn.property("cssClass") == "lang-button"
                or btn.property("lang") is not None
            )
            if not is_lang:
                continue

            parent = btn.parent()
            # Only collapse the parent widget if it looks like a dedicated
            # lang-selector container (no QLabel children → it's not a general
            # content widget like self.root in disk-manager).
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

    # ── Language switching ────────────────────────────────────────────────────

    def apply_language(self) -> None:
        """Forward language change to the embedded app via its retranslation method."""
        code = getattr(self, "current_lang", "en")
        if not getattr(self, "_win", None):
            return

        win = self._win

        # 1. Try single-argument methods (most apps)
        for name in _LANG_METHOD_1ARG:
            method = getattr(win, name, None)
            if callable(method):
                try:
                    method(code)
                except Exception:
                    pass
                return

        # 2. change_language — tutorial (1 arg) vs software-center (0 args)
        method = getattr(win, "change_language", None)
        if callable(method):
            try:
                sig = inspect.signature(method)
                # Count parameters that have no default (excluding 'self')
                required = [
                    p for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                ]
                if required:
                    method(code)
                else:
                    # software-center: relies on self.sender() to get the lang.
                    # Click the matching hidden button so the app's own logic runs.
                    for btn in win.findChildren(QPushButton):
                        if btn.property("lang") == code:
                            btn.click()
                            break
            except Exception:
                pass
            return

    def on_shown(self) -> None:
        pass  # app is already initialised and updates itself internally
