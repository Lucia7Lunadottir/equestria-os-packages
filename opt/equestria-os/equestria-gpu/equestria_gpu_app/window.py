"""gpu: window."""
from __future__ import annotations

import json
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import small_btn
from .localization import catalog, live_i18n, tr
from .panel import GpuPanel
from .paths import CONFIG
from .style import apply_theme


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.cfg = cfg
        self.theme = cfg["theme"]
        live_i18n.call(self.setWindowTitle, "Equestria GPU")
        self.setMinimumSize(980, 640)
        self.resize(1120, 760)
        self.panel = GpuPanel()
        theme_btn = small_btn(tr("window.theme"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        self.panel.buttons.addWidget(theme_btn)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.setContentsMargins(18, 8, 18, 0)
        header.addStretch()
        self.language_combo = catalog.selector(self)
        header.addWidget(self.language_combo)
        layout.addLayout(header)
        layout.addWidget(self.panel)
        self.setCentralWidget(central)

    # --- тема
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = self.cfg["theme"] = apply_theme(name)
        self.panel.rebuild()
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
