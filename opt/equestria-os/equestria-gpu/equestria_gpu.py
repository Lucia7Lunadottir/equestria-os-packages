#!/usr/bin/env python3
"""Entry point for Equestria gpu."""
from equestria_gpu_app.app import main
from equestria_gpu_app.compat import __getattr__

if __name__ == "__main__":
    raise SystemExit(main())
