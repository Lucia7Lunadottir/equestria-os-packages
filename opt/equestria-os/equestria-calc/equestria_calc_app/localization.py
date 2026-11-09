"""Catalog and Qt text bindings; available languages come from files."""
from equestria_kit import live_i18n
from pathlib import Path

catalog = live_i18n.Catalog("equestria-calc", Path(__file__).resolve().parents[1] / "equestria_calc.py")
tr = catalog.tr
