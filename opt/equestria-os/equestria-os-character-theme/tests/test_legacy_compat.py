"""The compat characters.json for old readers must stay identical to what characters.d says."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "equestria-qt-kit"))

from equestria_kit.character_store import CharacterStore  # noqa: E402


class LegacyCompat(unittest.TestCase):
    def test_generated_file_equals_the_dropins_and_old_readers_see_every_character(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "characters.json"
            subprocess.run([sys.executable, str(ROOT / "tools" / "legacy_characters.py"), str(ROOT / "characters.d"), str(out)], check=True)
            legacy = json.loads(out.read_text(encoding="utf-8"))["Characters"]      # what an OLD reader would get
            new = CharacterStore(Path(tmp) / "user", ROOT).read()                    # what the new store reads from characters.d
            self.assertGreaterEqual(len(legacy), 8)
            self.assertEqual(legacy, new)
            self.assertEqual(legacy[0]["Id"], "canterlot")                           # first card stays first


if __name__ == "__main__":
    unittest.main()
