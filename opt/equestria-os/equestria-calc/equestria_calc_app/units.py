"""calc: units."""
from __future__ import annotations




CATS = {
    "units.length": ([("units.mm", 1e-3), ("units.cm", 1e-2), ("units.m", 1), ("units.km", 1e3), ("units.inch", 0.0254),
               ("units.foot", 0.3048), ("units.yard", 0.9144), ("units.mile", 1609.344), ("units.nautical_mile", 1852)], 2, 3),
    "units.mass": ([("units.mg", 1e-6), ("units.g", 1e-3), ("units.kg", 1), ("units.t", 1e3), ("units.ounce", 0.028349523125),
               ("units.pound", 0.45359237), ("units.stone", 6.35029318)], 2, 5),
    "units.temperature": ([("°C", 0), ("°F", 0), ("K", 0)], 0, 1),
    "units.area": ([("units.mm_2", 1e-6), ("units.cm_2", 1e-4), ("units.m_2", 1), ("units.ha", 1e4), ("units.km_2", 1e6),
                 ("units.ft", 0.09290304), ("units.acre", 4046.8564224)], 2, 3),
    "units.volume": ([("units.ml", 1e-3), ("units.l", 1), ("units.m_3", 1e3), ("units.gallon_us", 3.785411784),
               ("units.pint_us", 0.473176473), ("units.cup_us", 0.2365882365),
               ("units.fluid_ounce", 0.0295735295625)], 1, 3),
    "units.speed": ([("units.m_s", 1), ("units.km_h", 1 / 3.6), ("units.mph", 0.44704), ("units.knot", 1852 / 3600),
                  ("units.ft_s", 0.3048)], 1, 2),
    "units.time": ([("units.ms", 1e-3), ("units.s", 1), ("units.min", 60), ("units.h", 3600), ("units.day", 86400),
               ("units.week", 604800), ("units.year", 31557600)], 2, 3),
    "units.data": ([("units.bit", 0.125), ("units.byte", 1), ("units.kb", 1e3), ("units.mb", 1e6), ("units.gb", 1e9), ("units.tb", 1e12),
                ("units.kib", 1024), ("units.mib", 1024 ** 2), ("units.gib", 1024 ** 3)], 3, 4),
}


def convert(cat: str, v: float, a: str, b: str) -> float:
    if cat == "units.temperature":
        c = {"°C": v, "°F": (v - 32) * 5 / 9, "K": v - 273.15}[a]
        return {"°C": c, "°F": c * 9 / 5 + 32, "K": c + 273.15}[b]
    u = dict(CATS[cat][0])
    return v * u[a] / u[b]
