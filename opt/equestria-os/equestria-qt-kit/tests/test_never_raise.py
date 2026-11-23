"""The kit must never raise because of missing or broken user data: apps fall back instead of dying."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from equestria_kit.character_store import CharacterStore  # noqa: E402


class BrokenData(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.user, self.system = Path(tmp.name) / "user", Path(tmp.name) / "system"
        for p in (self.user / "characters.d", self.system / "characters.d"):
            p.mkdir(parents=True)

    def test_garbage_in_every_place_gives_an_empty_or_partial_list_not_an_exception(self):
        (self.system / "characters.d" / "10-a.json").write_text(json.dumps({"Id": "a", "AccentColor": "#111111"}))
        (self.system / "characters.d" / "20-bad.json").write_bytes(b"\xff\xfe\x00garbage")
        (self.system / "characters.d" / "30-list.json").write_text("[1, 2, 3]")
        (self.system / "characters.d" / "40-noid.json").write_text(json.dumps({"AccentColor": "#222222"}))
        (self.system / "characters.json").write_text("not json at all")
        (self.user / "characters.json").write_text(json.dumps({"Characters": "nope"}))
        (self.user / "characters.d" / "a.json").write_text(json.dumps({"Id": "a", "AccentColor": None}))
        store = CharacterStore(self.user, self.system)
        got = store.read()
        self.assertEqual([c["Id"] for c in got], ["a"])
        store.signature()

    def test_unreadable_folders_do_not_raise(self):
        (self.system / "characters.d" / "10-a.json").write_text(json.dumps({"Id": "a"}))
        os.chmod(self.system / "characters.d", 0)
        self.addCleanup(lambda: os.chmod(self.system / "characters.d", 0o755))
        if os.access(self.system / "characters.d", os.R_OK):
            self.skipTest("running with rights that ignore permissions (root)")
        self.assertEqual(CharacterStore(self.user, self.system).read(), [])

    def test_missing_directories(self):
        self.assertEqual(CharacterStore(self.user / "nope", self.system / "nope").read(), [])

    def test_theme_registry_survives_garbage(self):
        from equestria_kit import themes
        (self.user / "characters.json").write_text("{broken")
        registry = themes.ThemeRegistry([themes.BuiltinThemes(), themes.CharacterThemes(self.user, self.system / "characters.json")])
        registry.reload()
        self.assertIn(themes.DEFAULT_THEME, registry.palettes)     # the fallback theme is always there


if __name__ == "__main__":
    unittest.main()
