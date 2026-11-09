"""Application package; resolve the matching toolkit for source checkouts."""
from pathlib import Path
import sys

_local_kit = Path(__file__).resolve().parents[2] / "equestria-qt-kit"
if (_local_kit / "equestria_kit/live_i18n.py").is_file():
    sys.path.insert(0, str(_local_kit))
