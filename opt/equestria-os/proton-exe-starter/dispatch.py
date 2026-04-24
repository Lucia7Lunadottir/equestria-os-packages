"""
Equestria OS Proton Starter — unified entry point.

The same binary is installed under three names and dispatches based on argv[0]:
  equestria-proton-settings  → main.py   (settings / app manager)
  equestria-proton-run       → launcher.py (runs a .exe via Proton)
  equestria-proton-cleaner   → cleaner.py  (cleans Proton cache)
"""
import sys
import os

_name = os.path.basename(sys.argv[0])

if "run" in _name or "launcher" in _name:
    import launcher as _mod
elif "cleaner" in _name:
    import cleaner as _mod
else:
    import main as _mod

# Execute the module's __main__ block
if hasattr(_mod, "__file__"):
    import runpy
    runpy.run_module(_mod.__name__, run_name="__main__", alter_sys=True)
