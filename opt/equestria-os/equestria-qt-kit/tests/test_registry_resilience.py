"""The theme registry must not lose themes because a read failed for a moment."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from equestria_kit import themes  # noqa: E402


class Source:
    def __init__(self, names, sticky=False):
        self.names, self.sticky, self.fail = list(names), sticky, False

    def load(self, fallback):
        if self.fail:
            raise OSError("disk hiccup")
        for n in self.names:
            yield themes.Theme.from_mapping(n, {"accent": "#123456"}, fallback)


class Resilience(unittest.TestCase):
    def test_a_sticky_source_that_suddenly_returns_nothing_keeps_its_last_good_themes(self):
        chars = Source(["Rarity", "Pinkie"], sticky=True)
        reg = themes.ThemeRegistry([themes.BuiltinThemes(), chars])
        self.assertIn("Rarity", reg.palettes)
        chars.names = []                                   # e.g. the files are being replaced by an upgrade
        reg.reload()
        self.assertIn("Rarity", reg.palettes)
        self.assertIn("Pinkie", reg.palettes)
        self.assertIn(themes.DEFAULT_THEME, reg.palettes)

    def test_a_failing_source_neither_raises_nor_takes_the_others_down(self):
        a, b = Source(["A"]), Source(["B"])
        reg = themes.ThemeRegistry([themes.BuiltinThemes(), a, b])
        a.fail = True
        reg.reload()                                       # must not raise
        self.assertIn("A", reg.palettes)                   # last good kept
        self.assertIn("B", reg.palettes)

    def test_a_normal_source_may_legitimately_become_empty(self):
        mine = Source(["My theme"])                        # the user deleted all of their own themes
        reg = themes.ThemeRegistry([themes.BuiltinThemes(), mine])
        mine.names = []
        reg.reload()
        self.assertNotIn("My theme", reg.palettes)

    def test_new_themes_still_appear(self):
        chars = Source(["Rarity"], sticky=True)
        reg = themes.ThemeRegistry([themes.BuiltinThemes(), chars])
        chars.names = ["Rarity", "Canterlot"]
        reg.reload()
        self.assertIn("Canterlot", reg.palettes)

    def test_character_themes_source_is_sticky(self):
        self.assertTrue(themes.CharacterThemes.sticky)


if __name__ == "__main__":
    unittest.main()
