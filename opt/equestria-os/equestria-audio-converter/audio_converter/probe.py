"""Вопросы к ffprobe: длительность и частота дискретизации."""
from __future__ import annotations

import shutil
import subprocess


def _ffprobe(path: str, *args: str) -> str | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        r = subprocess.run([ffprobe, "-v", "error", *args, "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip().splitlines()[0]
    except Exception:
        return None


def probe_duration(path: str) -> float | None:
    try:
        v = float(_ffprobe(path, "-show_entries", "format=duration") or "")
        return v if v > 0 else None
    except ValueError:
        return None


def probe_sample_rate(path: str) -> int | None:
    try:
        v = int(_ffprobe(path, "-select_streams", "a:0", "-show_entries", "stream=sample_rate") or "")
        return v if v > 0 else None
    except ValueError:
        return None
