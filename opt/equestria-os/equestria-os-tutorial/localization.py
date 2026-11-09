"""Shared file-based catalog and live Qt bindings."""
from pathlib import Path
import sys

# Source checkout; installed packages use the system equestria_kit.
_source_kit = Path(__file__).resolve().parent.parent / "equestria-qt-kit"
if (_source_kit / "equestria_kit" / "live_i18n.py").is_file():
    sys.path.insert(0, str(_source_kit))
from equestria_kit import live_i18n

catalog = live_i18n.Catalog("equestria-os-tutorial", __file__)
tr = catalog.tr
call = live_i18n.call
