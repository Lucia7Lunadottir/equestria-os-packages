"""Tests for asset_sync.add_missing. Run:  python3 -m unittest discover -s tests"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asset_sync  # noqa: E402


class AddMissing(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.src, self.dst = Path(tmp.name) / "pkg", Path(tmp.name) / "user"
        (self.src / "Rarity").mkdir(parents=True)
        (self.src / "Rarity" / "a.jpg").write_text("pkg")
        (self.src / "Canterlot").mkdir()
        (self.src / "Canterlot" / "b.jpg").write_text("new")
        (self.src / "icon.png").write_text("icon")
        (self.dst / "Rarity").mkdir(parents=True)
        (self.dst / "Rarity" / "a.jpg").write_text("mine")           # user's own copy
        (self.dst / "Rarity" / "extra.jpg").write_text("extra")

    def test_adds_only_what_is_missing_and_never_overwrites(self):
        added = asset_sync.add_missing(str(self.src), str(self.dst))
        self.assertEqual(sorted(added), ["Canterlot", "icon.png"])
        self.assertEqual((self.dst / "Canterlot" / "b.jpg").read_text(), "new")
        self.assertEqual((self.dst / "Rarity" / "a.jpg").read_text(), "mine")
        self.assertTrue((self.dst / "Rarity" / "extra.jpg").exists())

    def test_second_run_adds_nothing(self):
        asset_sync.add_missing(str(self.src), str(self.dst))
        self.assertEqual(asset_sync.add_missing(str(self.src), str(self.dst)), [])

    def test_missing_source_is_harmless(self):
        self.assertEqual(asset_sync.add_missing(str(self.src / "nope"), str(self.dst)), [])


if __name__ == "__main__":
    unittest.main()
