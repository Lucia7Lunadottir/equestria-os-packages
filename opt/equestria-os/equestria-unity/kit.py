from pathlib import Path
import sys

APP_ID = "equestria-unity"
ROOT = Path(__file__).resolve().parent
checkout = ROOT.parent / "equestria-qt-kit"
if (checkout / "equestria_kit/live_i18n.py").is_file():
    sys.path.insert(0, str(checkout))

from equestria_kit import live_i18n, qt, themes
from equestria_kit.single_instance import SingleInstance

catalog = live_i18n.Catalog(APP_ID, __file__)
tr = catalog.tr
call = live_i18n.call



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
