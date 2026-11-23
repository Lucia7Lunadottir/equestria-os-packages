"""Public-interface lock: everything the apps actually use must still exist (see STABILITY.md).

api_surface.json is produced by tools/api_surface.py from the sources of all apps."""

import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
SURFACE = json.loads((KIT / "api_surface.json").read_text(encoding="utf-8"))


class ApiSurface(unittest.TestCase):
    def test_every_name_used_by_an_app_still_exists(self):
        missing = []
        for module, names in SURFACE.items():
            try:
                mod = importlib.import_module(module)
            except Exception as e:   # a module that cannot even be imported
                missing.append(f"{module}: import failed ({e})")
                continue
            for name in names:
                if not hasattr(mod, name):
                    try:
                        importlib.import_module(f"{module}.{name}")      # a submodule is fine too
                    except Exception:
                        missing.append(f"{module}.{name}")
        self.assertEqual(missing, [], "apps use these names, but the kit no longer provides them")

    def test_no_app_uses_something_that_is_not_locked_yet(self):
        r = subprocess.run([sys.executable, str(KIT / "tools" / "api_surface.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
