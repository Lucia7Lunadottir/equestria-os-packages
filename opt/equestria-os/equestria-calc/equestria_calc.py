#!/usr/bin/env python3
"""Entry point for Equestria calc."""
from equestria_calc_app.app import main
from equestria_calc_app.compat import __getattr__

if __name__ == "__main__":
    raise SystemExit(main())
