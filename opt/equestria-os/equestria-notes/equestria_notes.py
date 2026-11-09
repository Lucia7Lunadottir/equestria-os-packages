#!/usr/bin/env python3
"""Entry point for Equestria notes."""
from equestria_notes_app.app import main
from equestria_notes_app.compat import __getattr__

if __name__ == "__main__":
    raise SystemExit(main())
