"""Громкость сигнала: пик, децибелы, положение на индикаторе."""
from __future__ import annotations

import math
from array import array

FULL_SCALE = 32768
CLIP_PEAK = 32700   # выше — перегрузка


def peak_of(samples: array) -> int:
    return max(max(samples), -min(samples)) if samples else 0


def peak_db(peak: int) -> float | None:
    """Пик в дБ относительно полной шкалы; None — тишина (−∞)."""
    return 20 * math.log10(peak / FULL_SCALE) if peak else None


def to_level(peak: int) -> float:
    """Пик (0..32768) -> 0..1 по шкале -60..0 дБ."""
    db = 20 * math.log10(max(peak, 1) / FULL_SCALE)
    return max(0.0, min(1.0, (db + 60) / 60))
