"""color-picker: color."""
from __future__ import annotations

import colorsys
import math
import re


def lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklch(lr: float, lg: float, lb: float):
    l = (0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb) ** (1 / 3)
    m = (0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb) ** (1 / 3)
    s = (0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    b = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    C = math.hypot(a, b)
    H = math.degrees(math.atan2(b, a)) % 360 if C > 1e-4 else 0.0
    return L, C, H


def fnum(x: float, p: int, trim: bool) -> str:
    s = f"{x:.{p}f}"
    if trim:
        s = s.rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def fields(r: int, g: int, b: int, A: int, p: int = 3, trim: bool = True, upper: bool = True) -> dict:
    rf, gf, bf, af = r / 255, g / 255, b / 255, A / 255
    f = lambda x: fnum(x, p, trim)
    hh, ll, sl = colorsys.rgb_to_hls(rf, gf, bf)
    hv, sv, vv = colorsys.rgb_to_hsv(rf, gf, bf)
    lr, lg, lb = lin(rf), lin(gf), lin(bf)
    k = 1 - max(rf, gf, bf)
    cmy = (0, 0, 0) if k >= 1 else [(1 - x - k) / (1 - k) for x in (rf, gf, bf)]
    L, C, H = oklch(lr, lg, lb)
    hx = f"{r:02x}{g:02x}{b:02x}"
    short = hx[0] + hx[2] + hx[4] if (hx[0] == hx[1] and hx[2] == hx[3] and hx[4] == hx[5]) else hx
    case = str.upper if upper else str.lower
    return dict(
        r=r, g=g, b=b, a=A, ap=round(af * 100),
        rf=f(rf), gf=f(gf), bf=f(bf), af=f(af),
        lr=f(lr), lg=f(lg), lb=f(lb),
        hex=case(hx), hexa=case(hx + f"{A:02x}"), ahex=case(f"{A:02x}" + hx), hexs=case(short),
        int=(r << 16) | (g << 8) | b,
        h=round(hh * 360) % 360, s=round(sl * 100), l=round(ll * 100),
        sv=round(sv * 100), v=round(vv * 100),
        hf=f(hv), sf=f(sv), vf=f(vv), lf=f(ll), slf=f(sl),
        c=round(cmy[0] * 100), m=round(cmy[1] * 100), y=round(cmy[2] * 100), k=round(k * 100),
        ol=f"{L * 100:.1f}", oc=f"{C:.4f}", oh=f"{H:.2f}",
    )


def try_render(tpl: str, fl: dict):
    try:
        return tpl.format_map(fl)
    except Exception:
        return None


def luminance(r: int, g: int, b: int) -> float:
    return 0.2126 * lin(r / 255) + 0.7152 * lin(g / 255) + 0.0722 * lin(b / 255)


def contrast(l1: float, l2: float) -> float:
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)


def grade(ratio: float) -> str:
    return "AAA" if ratio >= 7 else "AA" if ratio >= 4.5 else "AA Large" if ratio >= 3 else "✗"


def parse_hex(text: str):
    """RGB(A) по правилам CSS: 3/4/6/8 цифр. Возвращает (r,g,b,a|None) или None."""
    t = text.strip().lstrip("#")
    if t.lower().startswith("0x"):
        t = t[2:]
    if not re.fullmatch(r"[0-9a-fA-F]+", t) or len(t) not in (3, 4, 6, 8):
        return None
    if len(t) in (3, 4):
        t = "".join(ch * 2 for ch in t)
    v = [int(t[i:i + 2], 16) for i in range(0, len(t), 2)]
    return v[0], v[1], v[2], (v[3] if len(v) == 4 else None)


class ColorState:
    """Текущий цвет: HSV + альфа. Оттенок хранится отдельно, поэтому не теряется,
    когда цвет становится серым или чёрным (как в пипетках графических редакторов)."""

    def __init__(self):
        self.h, self.s, self.v, self.a = 0.0, 1.0, 1.0, 1.0

    def rgb(self):
        return tuple(round(x * 255) for x in colorsys.hsv_to_rgb(min(self.h, 0.9999), self.s, self.v))

    def alpha255(self) -> int:
        return round(self.a * 255)

    def hex8(self) -> str:
        r, g, b = self.rgb()
        return f"{r:02x}{g:02x}{b:02x}{self.alpha255():02x}"

    def set_rgb(self, r, g, b, a=None) -> None:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > 0 and v > 0:
            self.h = h
        self.s, self.v = s, v
        if a is not None:
            self.a = a / 255

    def load_hex(self, h8: str) -> None:
        p = parse_hex(h8)
        if p:
            self.set_rgb(p[0], p[1], p[2], 255 if p[3] is None else p[3])

    def fields(self, precision: int, trim: bool, upper: bool) -> dict:
        r, g, b = self.rgb()
        return fields(r, g, b, self.alpha255(), precision, trim, upper)
