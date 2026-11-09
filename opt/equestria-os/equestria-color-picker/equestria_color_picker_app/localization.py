"""Catalog and Qt text bindings; available languages come from files."""
from equestria_kit import live_i18n
from pathlib import Path

catalog = live_i18n.Catalog("equestria-color-picker", Path(__file__).resolve().parents[1] / "equestria_color_picker.py")
tr = catalog.tr
