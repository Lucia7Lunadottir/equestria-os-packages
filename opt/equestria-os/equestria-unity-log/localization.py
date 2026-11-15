"""Load Unity Log translations with the shared Equestria Qt kit."""
from pathlib import Path
import sys

_local_kit = Path(__file__).resolve().parent.parent / "equestria-qt-kit"
if (_local_kit / "equestria_kit/live_i18n.py").is_file():
    sys.path.insert(0, str(_local_kit))

from equestria_kit import live_i18n

APP_ID = "equestria-unity-log"
catalog = live_i18n.Catalog(APP_ID, __file__)
tr = catalog.tr
