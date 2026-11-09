#!/usr/bin/env python3
"""Equestria Recorder — запись звука с микрофона в WAV и простая обрезка (PyQt6).

Точка входа; реализация — в пакете equestria_recorder_app/ (см. ARCHITECTURE.md).
"""
from equestria_recorder_app.app import main
from equestria_recorder_app.compat import __getattr__  # noqa: F401 — прежние имена модуля

if __name__ == "__main__":
    raise SystemExit(main())
