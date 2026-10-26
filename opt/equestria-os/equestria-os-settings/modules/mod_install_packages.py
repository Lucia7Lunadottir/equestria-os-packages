"""Install Packages — browse and install Equestria OS packages."""

import json
import os
import subprocess
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from base_module import BaseModule
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt

# ---------------------------------------------------------------------------
# Inline styles (bypass Kvantum)
# ---------------------------------------------------------------------------

_BTN_ACTION = (
    "QPushButton{background:@surface1@;color:@text@;"
    "border-radius:6px;padding:5px 14px;font-size:12px;"
    "border:1px solid @surface2@;}"
    "QPushButton:hover{background:@surface2@;color:white;}"
    "QPushButton:disabled{background:@surface0@;color:@surface2@;}"
)
_BTN_INSTALL = (
    "QPushButton{background:@accent%35@;color:@accent_hover@;"
    "border-radius:6px;padding:5px 14px;font-size:12px;"
    "border:1px solid @accent%75@;}"
    "QPushButton:hover{background:@accent%55@;color:white;}"
    "QPushButton:disabled{background:@surface0@;color:@surface2@;}"
)
_BTN_REMOVE = (
    "QPushButton{background:@red%25@;color:@red@;"
    "border-radius:6px;padding:5px 14px;font-size:12px;"
    "border:1px solid @red%65@;}"
    "QPushButton:hover{background:@red%45@;color:white;}"
    "QPushButton:disabled{background:@surface0@;color:@surface2@;}"
)
_BTN_UPDATE = (
    "QPushButton{background:@yellow%25@;color:@yellow@;"
    "border-radius:6px;padding:5px 14px;font-size:12px;"
    "border:1px solid @yellow%65@;}"
    "QPushButton:hover{background:@yellow%45@;color:white;}"
    "QPushButton:disabled{background:@surface0@;color:@surface2@;}"
)
_BADGE_INSTALLED = (
    "QLabel{background:@green%25@;color:@green@;"
    "border:1px solid @green%65@;border-radius:5px;"
    "padding:2px 8px;font-size:11px;}"
)
_BADGE_MISSING = (
    "QLabel{background:@yellow%25@;color:@yellow@;"
    "border:1px solid @yellow%45@;border-radius:5px;"
    "padding:2px 8px;font-size:11px;}"
)
_BADGE_UPDATE = (
    "QLabel{background:@yellow%25@;color:@yellow@;"
    "border:1px solid @yellow%45@;border-radius:5px;"
    "padding:2px 8px;font-size:11px;}"
)
_BADGE_CHECKING = (
    "QLabel{background:@surface0@;color:@subtext@;"
    "border:1px solid @surface2@;border-radius:5px;"
    "padding:2px 8px;font-size:11px;}"
)
_SEARCH_STYLE = (
    "QLineEdit{background:@surface0@;color:@text@;"
    "border:1px solid @accent%75@;border-radius:6px;"
    "padding:5px 10px;font-size:13px;}"
    "QLineEdit:focus{border:1px solid @accent@;}"
)

# ---------------------------------------------------------------------------
# Package catalogue — loaded from packages.json next to this app
# ---------------------------------------------------------------------------

def _load_packages(base_path: str) -> list[tuple[str, str, str, str]]:
    json_path = os.path.join(base_path, "packages.json")
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        return [(e["pkg"], e["icon"], e["name_key"], e["desc_key"]) for e in data]
    except Exception as e:
        print(f"[install_packages] failed to load packages.json: {e}")
        return []


# ---------------------------------------------------------------------------
# Async checkers
# ---------------------------------------------------------------------------

class _BatchChecker(QObject):
    result = pyqtSignal(str, bool)   # pkg_name, is_installed

    def __init__(self, packages: list[str], parent=None):
        super().__init__(parent)
        self._packages = packages

    def run(self):
        for pkg in self._packages:
            try:
                r = subprocess.run(
                    ["pacman", "-Q", pkg],
                    capture_output=True, timeout=5
                )
                installed = r.returncode == 0
            except Exception:
                installed = False
            self.result.emit(pkg, installed)


class _UpdateChecker(QObject):
    """Runs `pacman -Qu` once and emits the set of package names with updates."""
    done = pyqtSignal(set)

    def run(self):
        try:
            r = subprocess.run(
                ["pacman", "-Qu"],
                capture_output=True, text=True, timeout=15
            )
            pkgs = {line.split()[0] for line in r.stdout.splitlines() if line.strip()}
        except Exception:
            pkgs = set()
        self.done.emit(pkgs)


# ---------------------------------------------------------------------------
# Single package card
# ---------------------------------------------------------------------------

class _PackageCard(QFrame):
    def __init__(self, pkg_name: str, icon: str, name_key: str, desc_key: str,
                 t_func, parent=None):
        super().__init__(parent)
        self._pkg = pkg_name
        self._icon = icon
        self._name_key = name_key
        self._desc_key = desc_key
        self._t = t_func
        self._installed: bool | None = None   # None = unknown
        self._has_update: bool = False

        self.setObjectName("InlineCard")

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)

        # Left: icon + name + pkg id
        info = QVBoxLayout()
        info.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._icon_lbl = QLabel(icon)
        kit_qt.style(self._icon_lbl, "font-size:18px;background:transparent;")
        self._name_lbl = QLabel()
        self._name_lbl.setObjectName("SectionTitle")
        kit_qt.style(self._name_lbl, 
            "QLabel{color:@text@;font-size:13px;"
            "font-weight:bold;background:transparent;}"
        )
        title_row.addWidget(self._icon_lbl)
        title_row.addWidget(self._name_lbl)
        title_row.addStretch()
        info.addLayout(title_row)

        self._desc_lbl = QLabel()
        self._desc_lbl.setObjectName("FieldHint")
        self._desc_lbl.setWordWrap(True)
        kit_qt.style(self._desc_lbl, 
            "QLabel{color:@subtext@;font-size:12px;background:transparent;}"
        )
        info.addWidget(self._desc_lbl)

        self._pkg_lbl = QLabel(pkg_name)
        kit_qt.style(self._pkg_lbl, 
            "QLabel{color:@subtext@;font-size:11px;"
            "font-family:monospace;background:transparent;}"
        )
        info.addWidget(self._pkg_lbl)

        row.addLayout(info, 1)

        # Right: badge + button
        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._badge = QLabel()
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedWidth(130)
        right.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignRight)

        self._btn = QPushButton()
        self._btn.setFixedWidth(130)
        self._btn.clicked.connect(self._on_action)
        right.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignRight)

        row.addLayout(right)

        self._retranslate()
        self._set_checking()

    # ── Public ────────────────────────────────────────────────────────────────

    def retranslate(self, t_func):
        self._t = t_func
        self._retranslate()

    def set_installed(self, installed: bool):
        self._installed = installed
        if not installed:
            self._has_update = False
        self._update_status()

    def set_update_available(self, has_update: bool):
        self._has_update = has_update
        if self._installed:
            self._update_status()

    def matches(self, query: str) -> bool:
        q = query.lower()
        return (
            q in self._pkg.lower()
            or q in self._name_lbl.text().lower()
            or q in self._desc_lbl.text().lower()
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _retranslate(self):
        self._name_lbl.setText(self._t(self._name_key))
        self._desc_lbl.setText(self._t(self._desc_key))
        if self._installed is None:
            self._set_checking()
        else:
            self._update_status()

    def _set_checking(self):
        self._badge.setText(self._t("install_pkgs.checking"))
        kit_qt.style(self._badge, _BADGE_CHECKING)
        self._btn.setText("…")
        kit_qt.style(self._btn, _BTN_ACTION)
        self._btn.setEnabled(False)

    def _update_status(self):
        if self._installed and self._has_update:
            self._badge.setText(self._t("install_pkgs.update_available"))
            kit_qt.style(self._badge, _BADGE_UPDATE)
            self._btn.setText(self._t("install_pkgs.update"))
            kit_qt.style(self._btn, _BTN_UPDATE)
        elif self._installed:
            self._badge.setText(self._t("install_pkgs.installed"))
            kit_qt.style(self._badge, _BADGE_INSTALLED)
            self._btn.setText(self._t("install_pkgs.remove"))
            kit_qt.style(self._btn, _BTN_REMOVE)
        else:
            self._badge.setText(self._t("install_pkgs.not_installed"))
            kit_qt.style(self._badge, _BADGE_MISSING)
            self._btn.setText(self._t("install_pkgs.install"))
            kit_qt.style(self._btn, _BTN_INSTALL)
        self._btn.setEnabled(True)

    def _on_action(self):
        import shutil
        if self._installed and self._has_update:
            cmd = ["yay", "-S", self._pkg]
        elif self._installed:
            cmd = ["yay", "-R", "--noconfirm", self._pkg]
        else:
            cmd = ["yay", "-S", self._pkg]

        for term in [["konsole", "-e"], ["xterm", "-e"], ["gnome-terminal", "--"]]:
            if shutil.which(term[0]):
                subprocess.Popen(term + cmd, start_new_session=True)
                QTimer.singleShot(8000, self._recheck)
                self._btn.setEnabled(False)
                return

    def _recheck(self):
        self._has_update = False
        self._set_checking()
        checker = _BatchChecker([self._pkg])
        checker.result.connect(lambda _, ok: self.set_installed(ok))
        self._checker = checker
        threading.Thread(target=checker.run, daemon=True).start()


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class InstallPackagesModule(BaseModule):
    module_id = "mod_install_packages"
    display_name_key = "module.install_pkgs.name"
    description_key = "module.install_pkgs.desc"
    category = "software"
    icon = "📥"
    sort_order = 5

    def build_widget(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("ContentPage")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("ContentPage")

        inner = QWidget()
        inner.setObjectName("ContentPage")
        self._main_layout = QVBoxLayout(inner)
        self._main_layout.setContentsMargins(40, 30, 40, 30)
        self._main_layout.setSpacing(16)

        self._title_lbl = QLabel(self.t(self.display_name_key))
        self._title_lbl.setObjectName("ModTitle")
        self._main_layout.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(self.t(self.description_key))
        self._desc_lbl.setObjectName("ModDesc")
        self._desc_lbl.setWordWrap(True)
        self._main_layout.addWidget(self._desc_lbl)

        # Search + Refresh row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        self._search = QLineEdit()
        self._search.setPlaceholderText(self.t("install_pkgs.search_placeholder"))
        kit_qt.style(self._search, _SEARCH_STYLE)
        self._search.setMaximumWidth(380)
        self._search.textChanged.connect(self._on_search)
        ctrl_row.addWidget(self._search)

        ctrl_row.addStretch()

        self._refresh_btn = QPushButton(self.t("install_pkgs.refresh"))
        self._refresh_btn.setObjectName("ActionBtn")
        kit_qt.style(self._refresh_btn, _BTN_ACTION)
        self._refresh_btn.clicked.connect(self._refresh_all)
        ctrl_row.addWidget(self._refresh_btn)

        self._main_layout.addLayout(ctrl_row)

        # Package cards
        self._cards: list[tuple[str, _PackageCard]] = []
        for pkg_name, icon, name_key, desc_key in _load_packages(self.base_path):
            card = _PackageCard(pkg_name, icon, name_key, desc_key, self.t)
            self._main_layout.addWidget(card)
            self._cards.append((pkg_name, card))

        self._main_layout.addStretch()

        scroll.setWidget(inner)
        wl.addWidget(scroll)
        return wrapper

    def on_shown(self):
        self._refresh_all()

    def apply_language(self):
        if not self._widget:
            return
        self._title_lbl.setText(self.t(self.display_name_key))
        self._desc_lbl.setText(self.t(self.description_key))
        self._search.setPlaceholderText(self.t("install_pkgs.search_placeholder"))
        self._refresh_btn.setText(self.t("install_pkgs.refresh"))
        for _, card in self._cards:
            card.retranslate(self.t)

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_btn.setEnabled(False)
        pkg_names = [p for p, _ in self._cards]

        # 1. Check install status for all packages
        self._checker = _BatchChecker(pkg_names)
        self._checker.result.connect(self._on_pkg_result)
        self._installed_set: set[str] = set()
        self._checker.result.connect(self._track_installed)
        threading.Thread(target=self._run_install_check, daemon=True).start()

    def _run_install_check(self):
        self._checker.run()
        # 2. After install check, run update check
        self._update_checker = _UpdateChecker()
        self._update_checker.done.connect(self._on_updates_result)
        self._update_checker.run()

    def _track_installed(self, pkg_name: str, installed: bool):
        if installed:
            self._installed_set.add(pkg_name)

    def _on_pkg_result(self, pkg_name: str, installed: bool):
        for name, card in self._cards:
            if name == pkg_name:
                card.set_installed(installed)
                break

    def _on_updates_result(self, pkgs_with_updates: set):
        for name, card in self._cards:
            if name in pkgs_with_updates:
                card.set_update_available(True)
        self._refresh_btn.setEnabled(True)

    def _on_search(self, text: str):
        q = text.strip()
        for _, card in self._cards:
            if not q or card.matches(q):
                card.show()
            else:
                card.hide()
