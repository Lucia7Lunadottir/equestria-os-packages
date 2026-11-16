from pathlib import Path
from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import QComboBox
import sys

APP_ID = "equestria-unity"
VERSION = "1.2.0"  # keep in step with pkgver in PKGBUILD
ROOT = Path(__file__).resolve().parent
checkout = ROOT.parent / "equestria-qt-kit"
if (checkout / "equestria_kit/live_i18n.py").is_file():
    sys.path.insert(0, str(checkout))

from equestria_kit import live_i18n, qt, themes
from equestria_kit.single_instance import SingleInstance

catalog = live_i18n.Catalog(APP_ID, __file__)
tr = catalog.tr
call = live_i18n.call



class LanguageSelector(QComboBox):
    """Refresh installed language packs when the launcher settings list opens."""
    def __init__(self, parent, after):
        super().__init__(parent)
        self.after = after
        self.populate()
        call(self.setToolTip, catalog.library_text("kit.language"))
        self.activated.connect(self.choose)

    def populate(self):
        with QSignalBlocker(self):
            self.clear()
            for code in catalog.languages:
                self.addItem(catalog.language_name(code), code)
            self.setCurrentIndex(self.findData(catalog.lang))

    def showPopup(self):
        available = live_i18n.Catalog(APP_ID, __file__)
        if available.translations != catalog.translations:
            catalog.translations = available.translations
            catalog.languages = available.languages
            catalog.set_language(catalog.lang, persist=False)
            self.after()
        self.populate()
        super().showPopup()

    def choose(self, index):
        catalog.set_language(self.itemData(index))
        self.after()


class LauncherThemes:
    """Application-local palettes, persisted with the other launcher settings."""
    def __init__(self, colors):
        self.colors = colors
        themes.registry().add_source(self)

    def load(self, fallback):
        for name, colors in self.colors.items():
            yield themes.Theme.from_mapping(name, colors, fallback)

    def reload(self, colors):
        self.colors = colors
        themes.registry().reload()
