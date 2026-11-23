"""Apps that are already running keep the OLD kit in memory and read the OLD file layout.

After a kit/package upgrade they must still see every character (otherwise they lose all their colours).
`old_characters` is the reading algorithm of equestria-qt-kit 1.5, kept here unchanged as the contract.
Run:  python3 -m unittest discover -s tests"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from equestria_kit.character_store import CharacterStore  # noqa: E402


def old_characters(user_dir: Path, system_json: Path) -> list:
    """equestria-qt-kit 1.5: user characters.json, else the system characters.json, else nothing."""
    for path in (Path(user_dir) / "characters.json", Path(system_json)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            chars = data.get("Characters") if isinstance(data, dict) else None
            if isinstance(chars, list):
                return [c for c in chars if isinstance(c, dict)]
        except (OSError, ValueError):
            continue
    return []


CHARS = [{"Id": "a", "DisplayName": "A", "AccentColor": "#111111"}, {"Id": "b", "DisplayName": "B", "AccentColor": "#222222"}]


class OldReaderContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.user, self.system = Path(tmp.name) / "user", Path(tmp.name) / "system"
        (self.system / "characters.d").mkdir(parents=True)
        self.user.mkdir()
        for n, c in enumerate(CHARS, 1):
            (self.system / "characters.d" / f"{n * 10}-{c['Id']}.json").write_text(json.dumps(c))

    def test_package_layout_with_the_compat_file_is_readable_by_old_and_new_readers_alike(self):
        (self.system / "characters.json").write_text(json.dumps({"Characters": CHARS}))     # what the theme package ships
        old = old_characters(self.user, self.system / "characters.json")
        new = CharacterStore(self.user, self.system).read()
        self.assertEqual([c["Id"] for c in old], ["a", "b"])
        self.assertEqual(old, new)

    def test_after_the_user_data_was_converted_old_readers_still_see_the_characters(self):
        (self.system / "characters.json").write_text(json.dumps({"Characters": CHARS}))
        (self.user / "characters.json").write_text(json.dumps({"Characters": CHARS}))
        store = CharacterStore(self.user, self.system)
        store.migrate_legacy()                                  # the user's old file is renamed away
        self.assertFalse((self.user / "characters.json").exists())
        self.assertEqual([c["Id"] for c in old_characters(self.user, self.system / "characters.json")], ["a", "b"])

    def test_the_compat_path_is_part_of_the_contract(self):
        from equestria_kit import themes
        self.assertEqual(themes.CHARACTER_SYSTEM_JSON.name, "characters.json")


if __name__ == "__main__":
    unittest.main()
