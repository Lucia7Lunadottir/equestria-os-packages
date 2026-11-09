"""Общая библиотека Equestria OS (equestria-qt-kit): темы персонажей и переводы на 10 языков."""
from __future__ import annotations

import sys
from pathlib import Path

# Prefer the matching library when running from a source checkout.
_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "equestria-qt-kit", _ROOT / "equestria-packages" / "opt" / "equestria-os" / "equestria-qt-kit"):
    if (_p / "equestria_kit" / "live_i18n.py").is_file():
        sys.path.insert(0, str(_p))
        break

from equestria_kit import live_i18n
from equestria_kit import qt as kit_qt

_catalog = live_i18n.Catalog("equestria-unreal", __file__)
LANGUAGES = tuple((code, _catalog.translations[code].get("_language_name") or code)
                  for code in _catalog.languages)
tr = _catalog.tr


def set_language(code: str) -> str:
    return _catalog.set_language(code)
