#!/usr/bin/env python3
"""Entry point for Equestria calendar."""
from equestria_calendar_app.app import main
from equestria_calendar_app.compat import __getattr__

if __name__ == "__main__":
    raise SystemExit(main())
