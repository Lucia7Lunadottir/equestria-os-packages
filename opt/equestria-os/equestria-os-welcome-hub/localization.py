"""Shared file-based translations for Welcome Hub."""
from pathlib import Path
import sys

_local_kit = Path(__file__).resolve().parent.parent / "equestria-qt-kit"
if (_local_kit / "equestria_kit/live_i18n.py").is_file():
    sys.path.insert(0, str(_local_kit))
from equestria_kit import live_i18n, qt as kit_qt

catalog = live_i18n.Catalog("equestria-os-welcome-hub", __file__)
