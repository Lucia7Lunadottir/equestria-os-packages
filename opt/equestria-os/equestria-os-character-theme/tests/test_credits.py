"""Every picture of the theme must have an entry in credits.json (run: python3 -m unittest discover -s tests)."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Credits(unittest.TestCase):
    def test_every_image_has_a_credits_entry_and_no_ghosts(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "credits.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "run: python3 tools/credits.py\n" + r.stdout)

    def test_published_statuses_are_known(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import credits
        for rel, entry in credits.load().items():
            self.assertIn(entry.get("status"), credits.STATUSES, rel)


class Sync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import credits
        cls.credits = credits

    def entry(self, **kw):
        e = {"author": None, "source": None, "source_url": None, "license": None, "status": "unknown", "note": "", "md5": "aaa"}
        e.update(kw)
        return e

    def test_rename_keeps_the_data(self):
        data = {"Wallpapers/X/old name.jpg": self.entry(author="Someone", license="CC-BY", status="free", note="найдено 23.11")}
        out, added, ghosts, renamed = self.credits.sync(data, {"Wallpapers/X/new name.jpg": "aaa"})
        self.assertEqual(renamed, [("Wallpapers/X/old name.jpg", "Wallpapers/X/new name.jpg")])
        self.assertEqual((added, ghosts), ([], []))
        kept = out["Wallpapers/X/new name.jpg"]
        self.assertEqual((kept["author"], kept["license"], kept["status"], kept["note"]), ("Someone", "CC-BY", "free", "найдено 23.11"))

    def test_author_comes_from_the_file_name(self):
        out, added, *_ = self.credits.sync({}, {"Wallpapers/X/Hasbro Rarity.png": "bbb", "Wallpapers/X/SambaNeko Rarity 0.jpg": "ccc"})
        self.assertEqual(out["Wallpapers/X/Hasbro Rarity.png"]["status"], "proprietary")
        self.assertEqual(out["Wallpapers/X/SambaNeko Rarity 0.jpg"]["author"], "SambaNeko")
        self.assertEqual(out["Wallpapers/X/SambaNeko Rarity 0.jpg"]["status"], "personal")   # personal use only, not redistribution

    def test_a_name_never_overrides_what_was_filled_in(self):
        data = {"Wallpapers/X/Hasbro Rarity.png": self.entry(author="Другой автор", status="permission")}
        out, *_ = self.credits.sync(data, {"Wallpapers/X/Hasbro Rarity.png": "aaa"})
        self.assertEqual((out["Wallpapers/X/Hasbro Rarity.png"]["author"], out["Wallpapers/X/Hasbro Rarity.png"]["status"]),
                         ("Другой автор", "permission"))

    def test_any_author_in_the_name_is_recognised_by_the_convention(self):
        out, *_ = self.credits.sync({}, {"Wallpapers/X/uotapo SunsetShimmer.jpg": "a", "Wallpapers/X/peakpx (7).jpg": "b",
                                         "Wallpapers/X/Sunset Shimmer 1.jpg": "c", "Wallpapers/X/slide-8.jpg": "d"})
        self.assertEqual(out["Wallpapers/X/uotapo SunsetShimmer.jpg"]["author"], "uotapo")
        for old in ("peakpx (7).jpg", "Sunset Shimmer 1.jpg", "slide-8.jpg"):
            self.assertIsNone(out["Wallpapers/X/" + old]["author"], old)

    def test_stray_line_breaks_in_a_name_do_not_break_the_author(self):
        info = self.credits.author_from_name("\nSan4ouzzz Applejack.jpg")
        self.assertEqual(info["author"], "San4ouzzz")
        self.assertEqual(self.credits.author_from_name("AndoAnimalia\nTwilightSparkle.jpg")["author"], "AndoAnimalia")

    def test_deleted_file_loses_its_entry_and_a_new_file_gets_one(self):
        data = {"Wallpapers/X/gone.jpg": self.entry(md5="old")}
        out, added, ghosts, renamed = self.credits.sync(data, {"Wallpapers/X/new.jpg": "new"})
        self.assertEqual((added, ghosts, renamed), (["Wallpapers/X/new.jpg"], ["Wallpapers/X/gone.jpg"], []))
        self.assertEqual(out["Wallpapers/X/new.jpg"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
