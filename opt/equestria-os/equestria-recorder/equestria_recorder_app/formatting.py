"""Время записи в виде текста."""
from __future__ import annotations


def fmt_time(sec: float) -> str:
    """Длительность: «MM:SS» или «Ч:MM:SS»."""
    s = int(sec)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_t(sec: float) -> str:
    """Точная отметка для обрезки: «MM:SS.d»."""
    return f"{int(sec // 60):02d}:{sec % 60:04.1f}"
