#!/usr/bin/env python3
"""Entry point for Equestria color-picker."""
from equestria_color_picker_app.app import main
from equestria_color_picker_app.compat import __getattr__

if __name__ == "__main__":
    raise SystemExit(main())
