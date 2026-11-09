#!/usr/bin/env python3
"""Entry point for Equestria clock."""
from equestria_clock_app.app import main
from equestria_clock_app.compat import __getattr__

if __name__ == "__main__":
    raise SystemExit(main())
