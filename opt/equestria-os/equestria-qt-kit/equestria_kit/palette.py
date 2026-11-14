# -*- coding: utf-8 -*-
"""
Цветовая арифметика палитр Equestria OS — БЕЗ Qt (чистый Python).

Зачем отдельный файл: одни и те же правила («как получить светлую палитру из
тёмной», «подкрасить цвет, чтобы его было читаемо») нужны и PyQt6-приложениям
(equestria_kit.qt), и генератору цветовых схем KDE (kde_laf.py переключателя тем),
который запускается при сборке пакета и при входе в сессию, когда Qt не нужен.
Поэтому правила живут здесь, а qt.py только вызывает их: у Dolphin и у приложений
Equestria один и тот же светлый/тёмный вариант одного персонажа.

Все цвета — строки '#rrggbb'.
"""
from __future__ import annotations

import colorsys

__all__ = ["DAY_PREFIX", "day_overrides", "hex_to_rgb", "rgb_to_hex", "is_hex", "luminance", "contrast", "mix", "readable",
           "is_dark", "light_variant", "dark_variant", "with_derived"]


# Правки ДНЕВНОЙ палитры пользователя лежат в палитре темы под ключами «day_<роль>»
# (например day_base). Так они доезжают до всех, кто берёт light_variant: и до приложений
# Equestria, и до цветовых схем KDE.
DAY_PREFIX = "day_"


def day_overrides(theme: dict) -> dict:
    """{роль: '#цвет'} — собственные цвета дня из палитры темы (пусто, если пользователь их не менял)."""
    return {k[len(DAY_PREFIX):]: v for k, v in theme.items()
            if k.startswith(DAY_PREFIX) and len(k) > len(DAY_PREFIX) and is_hex(v)}


def is_hex(v) -> bool:
    if not isinstance(v, str) or not v.startswith("#"):
        return False
    s = v[1:]
    return len(s) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in s)


def hex_to_rgb(h: str) -> tuple:
    """'#rgb' / '#rrggbb' / '#aarrggbb' (как у QColor) -> (r, g, b)."""
    s = h.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    elif len(s) == 8:
        s = s[2:]
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb[:3])


def luminance(h: str) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in hex_to_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """Контраст WCAG: 1 (одинаковые) … 21 (чёрное на белом). Для обычного текста нужно ≥ 4.5."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a: str, b: str, k: float) -> str:
    ca, cb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(tuple(x + (y - x) * k for x, y in zip(ca, cb)))


def _hsl(h: str) -> tuple:
    r, g, b = (c / 255 for c in hex_to_rgb(h))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return hue, sat, light


def _from_hsl(hue: float, sat: float, light: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return rgb_to_hex((r * 255, g * 255, b * 255))


def is_dark(h: str) -> bool:
    """Тёмный ли цвет (светлота HSL < 0.5 — так же решает QColor.lightnessF)."""
    return _hsl(h)[2] < 0.5


def readable(color: str, background: str, target: float = 4.5) -> str:
    """Тот же оттенок, осветлённый (на тёмном фоне) или затемнённый (на светлом)
    до контраста ≥ target. Если цвет уже читаем — возвращается как есть."""
    if contrast(color, background) >= target:
        return color
    hue, sat, light = _hsl(color)
    dark_bg = is_dark(background)
    cand = color
    for _ in range(40):
        light = min(1.0, light + 0.025) if dark_bg else max(0.0, light - 0.025)
        cand = _from_hsl(hue, sat, light)
        if contrast(cand, background) >= target:
            return cand
    return cand


# Светлота ролей светлой палитры: порядок «глубины» как в тёмной (mantle/crust темнее base).
# День: области просмотра (base) почти белые, чтобы текст и значки читались чисто, а цвет
# персонажа проявляется в «рамке» — окне, боковых панелях и заголовке (mantle/crust).
# Раньше всё было почти белым, а в пробной версии — тонировано целиком и выглядело как плёнка.
_LIGHT_LEVELS = {"base": .972, "mantle": .925, "crust": .880,
                 "surface0": .955, "surface1": .875, "surface2": .790}
# …и тёмной (для светлых пользовательских палитр: ночная половина пары).
_DARK_LEVELS = {"base": .115, "mantle": .090, "crust": .060,
                "surface0": .160, "surface1": .205, "surface2": .290}


def light_variant(theme: dict) -> dict:
    """Светлая палитра из тёмной палитры персонажа: тот же оттенок фона (чуть тонированный),
    тёмный текст, акцент и статусы того же оттенка, но затемнённые до читаемого контраста.
    Цвета, которые пользователь задал для дня сам (ключи day_*), ставятся поверх."""
    hue, tint, _ = _hsl(theme["base"])
    # у тёмных фонов насыщенность низкая — на светлом она бы исчезла, поэтому слегка усиливаем
    tint = max(.28, min(tint * 1.3, .50))
    out = {k: _from_hsl(hue, tint, lvl) for k, lvl in _LIGHT_LEVELS.items()}
    # текст почти нейтральный: цветной текст на цветном фоне и давал «плёнку»
    out["text"] = _from_hsl(hue, min(tint, .10), .13)
    out["subtext"] = _from_hsl(hue, min(tint, .10), .34)
    for key in ("accent", "accent2", "green", "red", "yellow"):
        if key in theme:
            out[key] = readable(theme[key], out["base"], 3.2)
    out.update(day_overrides(theme))    # выбранные пользователем цвета дня важнее выведенных
    return out


def dark_variant(theme: dict) -> dict:
    """Тёмная палитра из светлой (зеркало light_variant): нужна, когда пользователь
    сделал светлую тему — ночная половина пары получает тёмные поверхности того же оттенка."""
    hue, tint, _ = _hsl(theme["base"])
    tint = min(tint, .30)
    out = {k: _from_hsl(hue, tint, lvl) for k, lvl in _DARK_LEVELS.items()}
    out["text"] = _from_hsl(hue, min(tint, .30), .93)
    out["subtext"] = _from_hsl(hue, min(tint, .25), .72)
    for key in ("accent", "accent2", "green", "red", "yellow"):
        if key in theme:
            out[key] = readable(theme[key], out["base"], 3.2)
    return out


def with_derived(theme: dict) -> dict:
    """Копия палитры с производными ролями, которых в файле темы может не быть
    (accent2 — как в equestria_kit.qt.derived_colors)."""
    out = dict(theme)
    if "accent2" not in out:
        out["accent2"] = mix(out["accent"], out["text"], .40)
    return out
