#!/usr/bin/env python3
"""Entry point for Equestria closer."""
from equestria_closer_app.app import main
from equestria_closer_app.compat import __getattr__

if __name__ == "__main__":
    raise SystemExit(main())
