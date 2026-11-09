"""calc: window."""
from __future__ import annotations

import json
from PyQt6.QtGui import QAction, QGuiApplication, QKeySequence
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QMenu, QStackedWidget, QVBoxLayout, QWidget
from equestria_kit import qt as kit_qt
from .converter_page import ConverterPage
from .date_page import DatePage
from .expression_page import ExprPage
from .localization import catalog, live_i18n, tr
from .paths import CONFIG
from .programmer_page import ProgPage
from .style import apply_theme
from .widgets import mk


MODES = [(tr("window.standard"), lambda: ExprPage(False)), (tr("window.scientific"), lambda: ExprPage(True)),
         (tr("window.programmer"), ProgPage), (tr("window.converter"), ConverterPage), (tr("window.dates"), DatePage)]


class MainWindow(QMainWindow):
    def __init__(self, theme: str, mode: int):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.theme = theme
        self.mode = 0
        live_i18n.call(self.setWindowTitle, "Equestria Calc")
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 18)
        root.setSpacing(8)
        top = QHBoxLayout()
        self.mode_btn = mk("", "small", expand=False)
        self.mode_btn.clicked.connect(self._mode_menu)
        theme_btn = mk(tr("window.theme"), "small", expand=False)
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(self.mode_btn)
        top.addStretch()
        self.language_combo = catalog.selector(self, self._language_changed)
        top.addWidget(self.language_combo)
        top.addWidget(theme_btn)
        root.addLayout(top)
        self.stack = QStackedWidget()
        self.pages = [make() for _, make in MODES]
        for p in self.pages:
            self.stack.addWidget(p)
        root.addWidget(self.stack, 1)
        self.set_mode(mode if 0 <= mode < len(MODES) else 0)

    def set_mode(self, i: int) -> None:
        self.mode = i
        page = self.pages[i]
        self.stack.setCurrentIndex(i)
        live_i18n.call(self.mode_btn.setText, live_i18n.format_text('☰  {0}', MODES[i][0]))
        self.setMinimumSize(*page.minimum)
        self.resize(*page.pref)
        self.setFocus()
        self._save()

    def _language_changed(self) -> None:
        live_i18n.call(self.mode_btn.setText, live_i18n.format_text('☰  {0}', MODES[self.mode][0]))
        self.pages[4]._update()

    def _mode_menu(self) -> None:
        menu = QMenu(self)
        for i, (name, _) in enumerate(MODES):
            act = live_i18n.call(QAction, ("● " if i == self.mode else "   ") + name, self)
            act.triggered.connect(lambda _=False, k=i: self.set_mode(k))
            live_i18n.call(menu.addAction, act)
        menu.exec(self.mode_btn.mapToGlobal(self.mode_btn.rect().bottomLeft()))

    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self._save()

    def _save(self) -> None:
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps({"theme": self.theme, "mode": self.mode}), encoding="utf-8")
        except OSError:
            pass

    def keyPressEvent(self, e) -> None:
        page = self.pages[self.mode]
        if e.matches(QKeySequence.StandardKey.Copy):
            text = page.copy_text()
            if text:
                live_i18n.call(QGuiApplication.clipboard().setText, text)
        elif not page.key(e):
            super().keyPressEvent(e)
