"""Глобальные темы KDE для персонажей — пара «день/ночь» на каждого.

    Equestria-<id>        день: светлая схема персонажа, курсор Vimix-white
    Equestria-<id>-Dark   ночь: тёмная схема персонажа, курсор Vimix

Цветовая схема (.colors) теперь ПОЛНАЯ: фон окон, область просмотра (файлы в Dolphin,
списки, поля ввода), кнопки, заголовки, подсказки, текст, выделение, ссылки и статусы.
Все цвета берутся из той же палитры персонажа, что красит приложения Equestria
(equestria_kit.themes.character_palette), — отдельной копии палитр здесь нет.
Акцент выделения — AccentColor персонажа (как и раньше); днём может быть свой — AccentColorDay.
Свои цвета дня — поле UiPaletteDay (правки поверх дня, выведенного из ночной палитры).

KDE сам переключает пару по времени суток: переключатель записывает их в
kdeglobals [KDE] DefaultLightLookAndFeel / DefaultDarkLookAndFeel.

В теме только цвета, курсор, заставка и Plasma-стиль панели (EquestriaPanel-Light/
-Dark: цвет панели днём и ночью задаёт equestria-os-task-panel-changer). Иконки, шрифты, стиль окон и обои
сюда не входят: тему KDE переприменяет утром и вечером, и всё записанное
здесь перебивало бы выбор пользователя.

Что где лежит (чтобы обновления ничего не затирали):
  • исходные настройки пользователя — characters.json (поля UiPalette / UiPaletteDay — только его правки ночи / дня);
  • сгенерированное — ~/.local/share/color-schemes/Equestria*.colors и
    ~/.local/share/plasma/look-and-feel/Equestria-*; это можно удалять и пересобирать:
    StalePairRefresher сам сравнивает их с тем, что получится сейчас, и пересобирает.
Файлы пишутся атомарно (временный файл + замена) и перед записью проверяются.

Один и тот же код работает в двух местах:
  • при сборке пакета — для встроенных персонажей, в $pkgdir/usr/share;
  • в переключателе — для своих персонажей, в ~/.local/share.

    python3 kde_laf.py --dest DIR/usr/share --characters characters.json [--icons DIR]
    python3 kde_laf.py --report --characters characters.json     # проверка контраста
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from equestria_kit import palette as kit_palette, themes as kit_themes
    from equestria_kit.character_store import CharacterStore
except ImportError:  # запуск из исходников: пакет equestria-qt-kit лежит рядом
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
    from equestria_kit import palette as kit_palette, themes as kit_themes
    from equestria_kit.character_store import CharacterStore

VARIANTS = {  # вариант -> (устар.: базовая схема Breeze, курсор, суффикс id темы)
    "Light": ("BreezeLight.colors", "Vimix-white-cursors", ""),
    "Dark": ("BreezeDark.colors", "Vimix-cursors", "-Dark"),
}
# Plasma-стиль панели для каждой половины пары. Свой цвет панели в них пишет
# equestria-os-task-panel-changer (в ~/.local); базовые версии без своего фона
# (выглядят как Breeze) ставит этот пакет — см. panel_styles(). Ссылаться на
# несуществующий стиль нельзя: Plasma тогда ломает цвета экрана блокировки.
PANEL_STYLES = {"Light": "EquestriaPanel-Light", "Dark": "EquestriaPanel-Dark"}
SYSTEM_COLORS = Path("/usr/share/color-schemes")   # устарело: схемы больше не строятся на основе Breeze
SPLASH = "Equestria-OS"


def safe_id(cid: str) -> str:
    """Id персонажа -> часть имени файла. Свои персонажи могут называться как
    угодно («Моя пони»): лишние символы убираются, а чтобы два таких имени не
    совпали, добавляется короткий хеш исходного имени."""
    clean = re.sub(r"[^A-Za-z0-9_-]", "", cid)
    if clean == cid and clean:
        return clean
    return f"{clean or 'character'}-{hashlib.sha1(cid.encode('utf-8')).hexdigest()[:6]}"


def laf_id(cid: str, variant: str) -> str:
    return f"Equestria-{safe_id(cid)}{VARIANTS[variant][2]}"


def scheme_name(cid: str, variant: str) -> str:
    s = safe_id(cid)
    return f"Equestria{s[:1].upper()}{s[1:]}{variant}"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return 61, 174, 233  # акцент Breeze


def _luminance(rgb) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _fmt(rgb) -> str:
    return ",".join(str(c) for c in rgb)


def _on(rgb) -> tuple[int, int, int]:
    """Цвет текста на заливке акцентом: белый или почти чёрный — что контрастнее."""
    lum, dark = _luminance(rgb), (35, 38, 41)
    on_white = 1.05 / (lum + 0.05)
    on_dark = (lum + 0.05) / (_luminance(dark) + 0.05)
    return (255, 255, 255) if on_white >= on_dark else dark


# ── Цветовая схема из палитры персонажа ─────────────────────────────────────
SCHEME_FORMAT = 3          # версия формата сгенерированных .colors; записывается в первую строку файла
FORMAT_MARK = "# Equestria-Scheme-Format:"
MIN_TEXT_CONTRAST = 4.5    # WCAG AA для обычного текста

_WHITE, _INK = "#ffffff", "#232629"   # текст на заливке акцентом: белый или тёмный (цвет как у Breeze)

GROUP_KEYS = ("BackgroundAlternate", "BackgroundNormal", "DecorationFocus", "DecorationHover",
              "ForegroundActive", "ForegroundInactive", "ForegroundLink", "ForegroundNegative",
              "ForegroundNeutral", "ForegroundNormal", "ForegroundPositive", "ForegroundVisited")
# Порядок групп — как в схемах Breeze
SCHEME_GROUPS = ("Button", "Complementary", "Header", "Header][Inactive", "Selection", "Tooltip", "View", "Window")

# Эффекты отключённых/неактивных элементов — те же значения, что в Breeze (KDE считает их сам)
_EFFECTS = """[ColorEffects:Disabled]
Color=56,56,56
ColorAmount=0
ColorEffect=0
ContrastAmount=0.65
ContrastEffect=1
IntensityAmount=0.1
IntensityEffect=2

[ColorEffects:Inactive]
ChangeSelectionColor=true
Color=112,111,110
ColorAmount=0.025
ColorEffect=2
ContrastAmount=0.1
ContrastEffect=2
Enable=false
IntensityAmount=0
IntensityEffect=0
"""


def _hex(rgb) -> str:
    return kit_palette.rgb_to_hex(rgb)


def _accent_hex(accent) -> str:
    return _hex(_rgb(str(accent or "#3daee9")))


def on_color(fill: str) -> str:
    """Текст на заливке: белый или почти чёрный — что контрастнее."""
    return _WHITE if kit_palette.contrast(_WHITE, fill) >= kit_palette.contrast(_INK, fill) else _INK


def selection_background(accent: str) -> str:
    """Заливка выделения: сам акцент персонажа, а если на нём нельзя прочитать текст
    (контраст < 4.5) — минимально затемнённый/осветлённый тот же оттенок."""
    def best(bg):
        return max(kit_palette.contrast(bg, _WHITE), kit_palette.contrast(bg, _INK))
    if best(accent) >= MIN_TEXT_CONTRAST:
        return accent
    for i in range(1, 101):
        for target in ("#000000", "#ffffff"):
            cand = kit_palette.mix(accent, target, i / 100)
            if best(cand) >= MIN_TEXT_CONTRAST:
                return cand
    return accent


def variant_palettes(pal: dict) -> dict:
    """Палитра персонажа -> {"Light": …, "Dark": …}. Встроенные палитры тёмные: день из них
    выводится (equestria_kit.palette.light_variant, как у приложений Equestria). Если
    пользователь сделал СВЕТЛУЮ тему, она остаётся днём как есть, а ночь выводится из неё."""
    if kit_palette.is_dark(pal["base"]):
        dark, light = pal, kit_palette.light_variant(pal)    # свои цвета дня (day_*) ставятся внутри
    else:
        light, dark = pal, kit_palette.dark_variant(pal)
        light = {**light, **kit_palette.day_overrides(pal)}
    return {"Light": kit_palette.with_derived(light), "Dark": kit_palette.with_derived(dark)}


# Прежние заводские акценты встроенных персонажей, которые выглядели плохо (оливковый у Флаттершай
# красил папки и выделение в грязно-зелёный). Если у пользователя всё ещё стоит именно такой —
# берётся новый; любой свой выбранный цвет не трогается.
LEGACY_ACCENTS = {("fluttershy", "#6c8223"): "#e481ae"}


def migrated_accent(char_id, accent) -> str:
    return LEGACY_ACCENTS.get((str(char_id or "").strip(), str(accent or "").strip().lower()), accent)


def accent_for(character: dict, variant: str) -> str:
    """Акцент выделения половины пары: у дня может быть свой (AccentColorDay), иначе общий AccentColor."""
    if variant == "Light":
        day = str(character.get("AccentColorDay") or "").strip()
        if day:
            return day
    return migrated_accent(character.get("Id"), character.get("AccentColor"))


def _legible(color: str, *backgrounds: str) -> str:
    for bg in backgrounds:
        color = kit_palette.readable(color, bg, MIN_TEXT_CONTRAST)
    return color


def _group(pal: dict, accent: str, bg: str, alt: str) -> dict:
    """Одна группа Colors:* — фон bg/alt и текст, читаемый на обоих."""
    link = pal.get("accent2_text") or pal["accent2"]
    fallback = kit_themes.fallback_colors()
    return {
        "BackgroundNormal": bg, "BackgroundAlternate": alt,
        "DecorationFocus": accent, "DecorationHover": accent,
        "ForegroundNormal": _legible(pal["text"], bg, alt),
        "ForegroundInactive": _legible(pal["subtext"], bg, alt),
        "ForegroundActive": _legible(accent, bg, alt),
        "ForegroundLink": _legible(link, bg, alt),
        "ForegroundVisited": _legible(kit_palette.mix(link, pal["subtext"], .5), bg, alt),
        "ForegroundNegative": _legible(pal.get("red", fallback["red"]), bg, alt),
        "ForegroundNeutral": _legible(pal.get("yellow", fallback["yellow"]), bg, alt),
        "ForegroundPositive": _legible(pal.get("green", fallback["green"]), bg, alt),
    }


def _selection(accent: str, view_bg: str) -> dict:
    fill = selection_background(accent)
    on = on_color(fill)
    alt = fill
    for k in (.35, .25, .15, .05, 0):      # «полосатая» строка выделения тоже должна читаться
        alt = kit_palette.mix(fill, view_bg, k)
        if kit_palette.contrast(on, alt) >= MIN_TEXT_CONTRAST:
            break
    out = {"BackgroundNormal": fill, "BackgroundAlternate": alt,
           "DecorationFocus": accent, "DecorationHover": accent}
    for key in GROUP_KEYS:
        if key.startswith("Foreground"):
            out[key] = on
    return out


def kde_roles(pal: dict, accent: str, dark_pal: dict | None = None) -> dict:
    """Роли KDE для одной половины пары. pal — палитра ЭТОЙ половины (см. variant_palettes),
    accent — AccentColor персонажа, dark_pal — тёмная палитра (для группы Complementary,
    она в KDE всегда тёмная: экран блокировки, окно выхода). Возвращает {группа: {ключ: '#hex'}}.

    Соответствие палитре персонажа (ночью / днём):
        Window  (окна, боковые панели)      base       / mantle   — как у Breeze: днём окно чуть темнее области просмотра
        View    (файлы, списки, поля ввода) mantle     / base
        Button  (кнопки)                    surface0   / base
        Tooltip (подсказки)                 surface1   / base
        Header  (заголовок окна, панели)    crust      / crust
        Selection                           AccentColor (с поправкой на читаемость текста)
        Complementary                       тёмная палитра (base)"""
    pal = kit_palette.with_derived(pal)
    accent = _accent_hex(accent)
    dark = kit_palette.is_dark(pal["base"])
    p = pal
    if dark:
        window, view, button, tip = (p["base"], p["mantle"]), (p["mantle"], p["base"]), \
            (p["surface0"], p["surface1"]), (p["surface1"], p["surface2"])
        header, header_off = (p["crust"], p["mantle"]), (p["mantle"], p["base"])
    else:
        window, view, button, tip = (p["mantle"], p["crust"]), (p["base"], p["mantle"]), \
            (p["base"], p["mantle"]), (p["base"], p["mantle"])
        header, header_off = (p["crust"], p["surface1"]), (p["mantle"], p["crust"])
    dp = kit_palette.with_derived(dark_pal or p)
    roles = {
        "Window": _group(p, accent, *window),
        "View": _group(p, accent, *view),
        "Button": _group(p, accent, *button),
        "Tooltip": _group(p, accent, *tip),
        "Header": _group(p, accent, *header),
        "Header][Inactive": _group(p, accent, *header_off),
        "Complementary": _group(dp, accent, dp["base"], dp["mantle"]),
        "Selection": _selection(accent, view[0]),
    }
    h, hi = roles["Header"], roles["Header][Inactive"]
    roles["WM"] = {"activeBackground": h["BackgroundNormal"], "activeBlend": h["ForegroundNormal"],
                   "activeForeground": h["ForegroundNormal"],
                   "inactiveBackground": hi["BackgroundNormal"], "inactiveBlend": hi["ForegroundInactive"],
                   "inactiveForeground": hi["ForegroundInactive"]}
    return roles


# Общая настройка стиля (не персонажа): «Фоны как в KDE». Лежит рядом с characters.json пользователя,
# поэтому её видят и переключатель, и автозапуск пересборки при входе в сессию.
SETTINGS_FILE = Path.home() / ".local" / "share" / "EquestriaOS" / "Themes" / "settings.json"


def kde_backgrounds(path: Path | None = None) -> bool:
    try:
        return bool(json.loads(Path(path or SETTINGS_FILE).read_text(encoding="utf-8")).get("kde_backgrounds"))
    except (OSError, ValueError, AttributeError):
        return False


def set_kde_backgrounds(on: bool, path: Path | None = None) -> None:
    path = Path(path or SETTINGS_FILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    data["kde_backgrounds"] = bool(on)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(data, indent=2))


_BREEZE_FILES = {"Light": "BreezeLight.colors", "Dark": "BreezeDark.colors"}
_BREEZE_CACHE: dict = {}


def _breeze_roles(variant: str, search=None) -> dict | None:
    """Группы Colors:* из настоящей схемы Breeze (как у KDE по умолчанию), либо None, если её нет."""
    import configparser
    key = (variant, str(search or SYSTEM_COLORS))
    if key in _BREEZE_CACHE:
        return _BREEZE_CACHE[key]
    roles = None
    path = Path(search or SYSTEM_COLORS) / _BREEZE_FILES[variant]
    try:
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        cp.optionxform = str
        cp.read_string(path.read_text(encoding="utf-8"))
        roles = {}
        for g in ("Button", "Complementary", "Header", "Header][Inactive", "Tooltip", "View", "Window"):
            sect = cp[f"Colors:{g}"]
            roles[g] = {k2: _hex(tuple(int(x) for x in sect[k2].split(",")[:3])) for k2 in GROUP_KEYS}
    except (OSError, KeyError, ValueError, configparser.Error):
        roles = None
    _BREEZE_CACHE[key] = roles
    return roles


def character_roles(character: dict, variant: str) -> dict:
    """Роли KDE одной половины пары персонажа — ЕДИНАЯ точка для схемы, проверки и предпросмотра.
    Если включена общая настройка «Фоны как в KDE» (kde_backgrounds), окна, списки, кнопки, подсказки
    и заголовки берутся из обычного Breeze (цвета фонов не меняются), а от персонажа остаются
    акцент и выделение. Если файла Breeze нет — используются цвета персонажа."""
    pals = variant_palettes(kit_themes.character_palette(character))
    accent = accent_for(character, variant)
    roles = kde_roles(pals[variant], accent, pals["Dark"])
    if kde_backgrounds():
        breeze = _breeze_roles(variant)
        if breeze:
            acc = _accent_hex(accent)
            for g, vals in breeze.items():
                roles[g] = {**vals, "DecorationFocus": acc, "DecorationHover": acc}
            h, hi = roles["Header"], roles["Header][Inactive"]
            roles["WM"] = {"activeBackground": h["BackgroundNormal"], "activeBlend": h["ForegroundNormal"],
                           "activeForeground": h["ForegroundNormal"],
                           "inactiveBackground": hi["BackgroundNormal"], "inactiveBlend": hi["ForegroundInactive"],
                           "inactiveForeground": hi["ForegroundInactive"]}
    return roles


def _rgb_text(hex_color: str) -> str:
    return _fmt(kit_palette.hex_to_rgb(hex_color))


def render_scheme(roles: dict, name: str) -> str:
    """Роли -> текст .colors (формат KDE: INI, цвета «r,g,b»). Порядок и набор ключей фиксированы,
    поэтому одинаковая палитра всегда даёт одинаковый файл (на этом держится проверка устаревших тем)."""
    out = [f"{FORMAT_MARK} {SCHEME_FORMAT}",
           "# Equestria OS: цветовая схема персонажа. Создаётся автоматически из палитры персонажа —",
           "# правьте цвета в «Теме персонажа» (редактор палитры), а не этот файл: он будет пересобран.",
           "# SPDX-License-Identifier: LGPL-2.0-or-later", "", _EFFECTS.rstrip("\n"), ""]
    for group in SCHEME_GROUPS:
        out.append(f"[Colors:{group}]" if "][" not in group else f"[Colors:{group}]")
        for key in GROUP_KEYS:
            out.append(f"{key}={_rgb_text(roles[group][key])}")
        out.append("")
    out += ["[General]", f"ColorScheme={name}", f"Name={name}", "shadeSortColumn=true", "",
            "[KDE]", "contrast=4", "", "[WM]"]
    for key in ("activeBackground", "activeBlend", "activeForeground",
                "inactiveBackground", "inactiveBlend", "inactiveForeground"):
        out.append(f"{key}={_rgb_text(roles['WM'][key])}")
    return "\n".join(out) + "\n"


def scheme_text(character: dict, variant: str) -> str:
    """Текст цветовой схемы одной половины пары персонажа (словарь из characters.json)."""
    cid = str(character.get("Id") or "").strip()
    return render_scheme(character_roles(character, variant), scheme_name(cid, variant))


def validate_scheme(text: str) -> list[str]:
    """Проверка сгенерированной схемы ДО записи на диск. Пустой список — всё в порядке."""
    import configparser
    problems = []
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read_string(text)
    except configparser.Error as e:
        return [f"файл не разбирается: {e}"]
    need = [f"Colors:{g}" for g in SCHEME_GROUPS] + ["ColorEffects:Disabled", "ColorEffects:Inactive",
                                                      "General", "KDE", "WM"]
    for sec in need:
        if not cp.has_section(sec):
            problems.append(f"нет раздела [{sec}]")
    for g in SCHEME_GROUPS:
        sec = f"Colors:{g}"
        if not cp.has_section(sec):
            continue
        for key in GROUP_KEYS:
            val = cp[sec].get(key)
            if val is None:
                problems.append(f"[{sec}] нет ключа {key}")
                continue
            try:
                parts = [int(x) for x in val.split(",")]
                if len(parts) != 3 or any(not 0 <= x <= 255 for x in parts):
                    raise ValueError
            except ValueError:
                problems.append(f"[{sec}] {key}={val!r} — не цвет «r,g,b»")
    if cp.has_section("General") and not cp["General"].get("Name"):
        problems.append("[General] нет Name")
    return problems


def scheme_format_of(text: str) -> int:
    """Версия формата сгенерированной схемы (0 — старая, без отметки)."""
    m = re.match(re.escape(FORMAT_MARK) + r"\s*(\d+)", text)
    return int(m.group(1)) if m else 0


def palette_warnings(pal: dict) -> list[tuple]:
    """Где цвета палитры плохо читаются: [(что, на чём, контраст)]. Схема KDE сама подтягивает
    текст до читаемого, но пользователю полезно знать, что выбранный цвет будет изменён."""
    out = []
    for fg, bgs in (("text", ("base", "mantle", "surface0")), ("subtext", ("base", "mantle", "surface0"))):
        for bg in bgs:
            if fg in pal and bg in pal:
                ratio = kit_palette.contrast(pal[fg], pal[bg])
                if ratio < MIN_TEXT_CONTRAST:
                    out.append((fg, bg, round(ratio, 1)))
    return out


# ── Атомарная запись ────────────────────────────────────────────────────────
def write_atomic(path: Path, text: str) -> bool:
    """Записать файл целиком или не трогать: сначала временный файл рядом, потом замена.
    Обрыв (нет места, выключили питание) оставляет прежний файл целым. True — файл изменился."""
    path = Path(path)
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return True


def _defaults(variant: str, scheme: str) -> str:
    return (f"[kdeglobals][General]\nColorScheme={scheme}\n\n"
            f"[kcminputrc][Mouse]\ncursorTheme={VARIANTS[variant][1]}\n\n"
            f"[plasmarc][Theme]\nname={PANEL_STYLES[variant]}\n\n"
            f"[ksplashrc][KSplash]\nEngine=KSplashQML\nTheme={SPLASH}\n")


def _metadata(cid: str, display: str, variant: str) -> str:
    day = variant == "Light"
    meta = {
        "KPackageStructure": "Plasma/LookAndFeel",
        "KPlugin": {
            "Id": laf_id(cid, variant),
            "Name": f"Equestria — {display}" + ("" if day else " (Dark)"),
            "Name[ru]": f"Equestria — {display}" + ("" if day else " (ночь)"),
            "Description": f"{display}: {'day' if day else 'night'}",
            "Description[ru]": f"{display}: {'день' if day else 'ночь'}",
            "Icon": "preferences-desktop-theme-global",
            "Authors": [{"Name": "Equestria OS"}],
            "Version": "3.0",
        },
    }
    return json.dumps(meta, ensure_ascii=False, indent=4) + "\n"


def build(dest_share: Path, characters: list, icons: Path | None = None,
          colors_dir: Path = SYSTEM_COLORS) -> list[str]:
    """Создать цветовые схемы и глобальные темы. characters — словари с Id,
    DisplayName, AccentColor, IconPath (и, если есть, UiPalette, UiPaletteDay, AccentColorDay, KonsoleTheme).
    Возвращает id созданных тем. colors_dir оставлен для совместимости и не используется.

    Каждая схема проверяется до записи; не прошедшая проверку не пишется, а прежний
    рабочий файл остаётся как был (ошибка уходит в stderr)."""
    dest_share = Path(dest_share)
    made = []
    for ch in characters:
        cid = str(ch.get("Id") or "").strip()
        if not cid:
            continue
        display = str(ch.get("DisplayName") or cid)
        icon = Path(icons, ch["IconPath"]) if icons and ch.get("IconPath") else None
        for variant in VARIANTS:
            scheme = scheme_name(cid, variant)
            try:
                text = scheme_text(ch, variant)
            except Exception as e:  # noqa: BLE001 — битый персонаж не должен останавливать сборку остальных
                print(f"[kde_laf] {cid}/{variant}: схема не построена ({e}); прежняя остаётся", file=sys.stderr)
                continue
            problems = validate_scheme(text)
            if problems:
                print(f"[kde_laf] {cid}/{variant}: схема не прошла проверку ({'; '.join(problems[:3])}); "
                      "прежняя остаётся", file=sys.stderr)
                continue
            write_atomic(dest_share / "color-schemes" / f"{scheme}.colors", text)
            pkg = dest_share / "plasma" / "look-and-feel" / laf_id(cid, variant)
            write_atomic(pkg / "metadata.json", _metadata(cid, display, variant))
            write_atomic(pkg / "contents" / "defaults", _defaults(variant, scheme))
            if icon and icon.is_file():
                (pkg / "contents" / "previews").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(icon, pkg / "contents" / "previews" / "preview.png")
            made.append(laf_id(cid, variant))
    return made


class StalePairRefresher:
    """Пересобирает пары в ~/.local, которые не совпадают с тем, что получилось бы сейчас.

    Копия в ~/.local перекрывает тему из /usr/share с тем же id, поэтому после
    обновления пакета KDE продолжает брать старые файлы. Так было с парами до 2.1.0
    (без [plasmarc][Theme] автосмена дня и ночи не меняла стиль панели), а в 2.2.0
    схемы стали полными (формат 3).

    Пара устарела, если defaults ИЛИ цветовая схема отличаются от свежесобранных. Сравнение
    идёт по содержимому, а не по номеру версии: так подхватываются и новый формат, и
    новые палитры (обновился equestria-qt-kit), и правки персонажа. Выбор цветов
    пользователя при этом не теряется — он хранится в characters.json (UiPalette),
    а не в сгенерированных файлах."""

    def __init__(self, dest_share: Path, icons: Path | None = None, colors_dir: Path = SYSTEM_COLORS):
        self.dest_share, self.icons, self.colors_dir = Path(dest_share), icons, colors_dir

    def _is_stale(self, ch: dict, variant: str) -> bool:
        cid = str(ch["Id"]).strip()
        defaults = self.dest_share / "plasma" / "look-and-feel" / laf_id(cid, variant) / "contents" / "defaults"
        try:
            defaults_ok = defaults.read_text(encoding="utf-8") == _defaults(variant, scheme_name(cid, variant))
        except OSError:
            return False  # пары нет — собирать нечего, её соберёт применение персонажа
        scheme_file = self.dest_share / "color-schemes" / f"{scheme_name(cid, variant)}.colors"
        try:
            scheme_ok = scheme_file.read_text(encoding="utf-8") == scheme_text(ch, variant)
        except OSError:
            scheme_ok = False  # схему стёрли или не создавали — пересобрать
        except Exception:  # noqa: BLE001 — не получится построить и при пересборке: не трогаем
            return False
        return not (defaults_ok and scheme_ok)

    def refresh(self, characters: list) -> list[str]:
        """Возвращает id пересобранных тем."""
        stale = [ch for ch in characters
                 if str(ch.get("Id") or "").strip()
                 and any(self._is_stale(ch, v) for v in VARIANTS)]
        return build(self.dest_share, stale, self.icons, self.colors_dir) if stale else []


def panel_styles(dest_share: Path) -> list[str]:
    """Базовые Plasma-стили панели (только metadata: всё берётся из Breeze).
    Ставятся пакетом в /usr/share, чтобы глобальные темы всегда ссылались на
    существующий стиль. X-Plasma-API — как у Breeze: с другим ключом Plasma
    перестаёт брать набор цветов Complementary (экран блокировки, окно выхода)."""
    made = []
    for variant, style_id in PANEL_STYLES.items():
        pkg = Path(dest_share) / "plasma" / "desktoptheme" / style_id
        pkg.mkdir(parents=True, exist_ok=True)
        meta = {
            "KPlugin": {"Id": style_id, "Name": f"Equestria Panel ({'day' if variant == 'Light' else 'night'})",
                        "Authors": [{"Name": "Equestria OS"}], "Version": "2.0"},
            "X-Plasma-API": "5.0",
            "fallbackPackage": "default",
        }
        (pkg / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
        made.append(style_id)
    return made


def expected_window_bg(character: dict, variant: str) -> str:
    """Какой фон окна («r,g,b») должен оказаться в kdeglobals после применения схемы."""
    return _rgb_text(character_roles(character, variant)["Window"]["BackgroundNormal"])


def apply_half(day_night: "DayNight", character: dict, variant: str) -> bool:
    """Применить одну половину пары персонажа и проверить цвета (см. DayNight.apply_verified)."""
    cid = str(character.get("Id") or "").strip()
    other = "Light" if variant == "Dark" else "Dark"
    return day_night.apply_verified(laf_id(cid, variant), scheme_name(cid, variant),
                                    expected_window_bg(character, variant), scheme_name(cid, other))


MODES = ("auto", "light", "dark")
BREEZE_LIGHT, BREEZE_DARK = "org.kde.breeze.desktop", "org.kde.breezedark.desktop"


class DayNight:
    """Режим «Авто / Светлая / Тёмная» на тех же ключах kdeglobals [KDE], что у
    самого KDE («Параметры → Глобальная тема» и виджет «Яркость и цвет»), —
    поэтому все три места всегда показывают одно и то же.

      Авто              AutomaticLookAndFeel=true: KDE сам меняет пару по времени суток
      Светлая / Тёмная  автоматика выключена, применена нужная половина пары
    Тумблер «Тёмный режим» в виджете KDE автоматику не выключает — он временно
    перебивает расписание до следующей смены дня и ночи."""

    def __init__(self, run=subprocess.run):
        self._run = run

    def _read(self, key: str, group: str = "KDE") -> str:
        r = self._run(["kreadconfig6", "--file", "kdeglobals", "--group", group, "--key", key],
                      capture_output=True, text=True)
        return (r.stdout or "").strip()

    def _write(self, key: str, value: str) -> None:
        # --notify: модуль автосмены KDE (lookandfeelautoswitcher) следит за изменениями
        self._run(["kwriteconfig6", "--file", "kdeglobals", "--group", "KDE", "--key", key, value, "--notify"],
                  capture_output=True)

    def pair(self) -> tuple[str, str]:
        return (self._read("DefaultLightLookAndFeel") or BREEZE_LIGHT,
                self._read("DefaultDarkLookAndFeel") or BREEZE_DARK)

    def current(self) -> str:
        """Id применённой сейчас глобальной темы."""
        return self._read("LookAndFeelPackage")

    def is_dark_now(self) -> bool:
        """Сейчас активна ночная половина пары (так же решает виджет KDE)."""
        current = self.current()
        return bool(current) and (current == self.pair()[1] or current.endswith("-Dark")
                                  or current == BREEZE_DARK)

    def mode(self) -> str:
        if self._read("AutomaticLookAndFeel").lower() == "true":
            return "auto"
        return "dark" if self.is_dark_now() else "light"

    def set_pair(self, light: str, dark: str) -> None:
        self._write("DefaultLightLookAndFeel", light)
        self._write("DefaultDarkLookAndFeel", dark)

    def apply(self, laf: str) -> bool:
        """Применить глобальную тему. False — KDE отказался (тогда прежняя остаётся как была)."""
        # --keep-auto: без него команда выключила бы автоматическую смену
        r = self._run(["plasma-apply-lookandfeel", "--apply", laf, "--keep-auto"], capture_output=True)
        return getattr(r, "returncode", 0) == 0

    # --- цветовая схема: проверка, что цвета и правда сменились
    def scheme_in_effect(self, scheme: str, window_bg: str) -> bool:
        """KDE действует по нужной схеме: имя совпало и фон окна в kdeglobals — как в нашем файле."""
        if self._read("ColorScheme", "General") != scheme:
            return False
        have = "".join(self._read("BackgroundNormal", "Colors:Window").split())
        return have == "".join(window_bg.split())

    def apply_scheme(self, scheme: str) -> None:
        """Штатная команда KDE для цветовой схемы."""
        self._run(["plasma-apply-colorscheme", scheme], capture_output=True)

    def ensure_scheme(self, scheme: str, window_bg: str, other: str | None = None) -> bool:
        """Довести цвета до нужной схемы. Если файл схемы поменялся, а имя осталось тем же,
        KDE мог посчитать её «уже применённой» и ничего не обновить — тогда переключаем
        через соседнюю схему и обратно. Возвращает, получилось ли."""
        if self.scheme_in_effect(scheme, window_bg):
            return True
        self.apply_scheme(scheme)
        if self.scheme_in_effect(scheme, window_bg):
            return True
        if other:
            self.apply_scheme(other)
            self.apply_scheme(scheme)
        return self.scheme_in_effect(scheme, window_bg)

    def apply_verified(self, laf: str, scheme: str, window_bg: str, other: str | None = None) -> bool:
        """Применить половину пары и убедиться, что цвета сменились. False — только если
        сам KDE отказался применять тему; невозможность проверить цвета не откатывает выбор."""
        if not self.apply(laf):
            return False
        if not self.ensure_scheme(scheme, window_bg, other):
            print(f"[kde_laf] тема {laf} применена, но цвета в kdeglobals не совпали со схемой {scheme}",
                  file=sys.stderr)
        return True

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(mode)
        if mode == "auto":
            self._write("AutomaticLookAndFeel", "true")  # KDE сам применит тему для текущего времени
            return
        self._write("AutomaticLookAndFeel", "false")
        light, dark = self.pair()
        self.apply(dark if mode == "dark" else light)


def refresh_user_themes(day_night: DayNight | None = None, home: Path | None = None) -> list[str]:
    """Пересобрать устаревшие пары в ~/.local (см. StalePairRefresher).

    Вызывается при входе в сессию (автозапуск --refresh-user) и при запуске
    переключателя: KDE меняет день/ночь сам, и ждать, пока кто-то откроет
    переключатель, нельзя. Если устаревшей была активная тема — она
    применяется заново, чтобы стиль панели совпал уже сейчас."""
    day_night = day_night or DayNight()
    share = (home or Path.home()) / ".local" / "share"
    themes = share / "EquestriaOS" / "Themes"
    characters = [c for c in CharacterStore(themes, Path(__file__).resolve().parent).read() if isinstance(c, dict)]
    rebuilt = StalePairRefresher(share, themes).refresh(characters)
    current = day_night.current()
    if current in rebuilt:
        for ch in characters:
            for variant in VARIANTS:
                if laf_id(str(ch.get("Id") or "").strip(), variant) == current:
                    apply_half(day_night, ch, variant)
    return rebuilt


def report(characters: list) -> int:
    """Проверка без записи: схема каждого персонажа проходит validate_scheme, текст читаем.
    Возвращает 0, если всё в порядке (для сборки и тестов)."""
    bad = 0
    for ch in characters:
        for variant in VARIANTS:
            text = scheme_text(ch, variant)
            problems = validate_scheme(text)
            roles = character_roles(ch, variant)
            worst = min(kit_palette.contrast(g[k], g[b])
                        for g in roles.values() if "ForegroundNormal" in g
                        for k in ("ForegroundNormal", "ForegroundInactive")
                        for b in ("BackgroundNormal", "BackgroundAlternate"))
            flag = "OK " if not problems and worst >= MIN_TEXT_CONTRAST else "!! "
            bad += flag == "!! "
            print(f"{flag}{ch.get('Id'):<12} {variant:<5} худший контраст текста {worst:4.1f}:1 {'; '.join(problems)}")
    return 1 if bad else 0


def _roles_args(ch: dict, variant: str) -> tuple:
    pals = variant_palettes(kit_themes.character_palette(ch))
    return pals[variant], accent_for(ch, variant), pals["Dark"]


def load_characters_arg(path: str) -> list:
    """Персонажи для сборки: каталог characters.d (файл на персонажа, порядок по имени) или старый общий файл."""
    p = Path(path)
    if p.is_dir():
        entries = []
        for f in sorted(p.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("Id"):
                entries.append(data)
        return entries
    return json.loads(p.read_text(encoding="utf-8")).get("Characters", [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh-user", action="store_true",
                    help="пересобрать устаревшие темы в ~/.local (автозапуск сессии)")
    ap.add_argument("--dest", help="каталог share (например $pkgdir/usr/share)")
    ap.add_argument("--characters", help="characters.d (каталог с файлами персонажей) или старый characters.json")
    ap.add_argument("--icons", help="каталог, от которого отсчитываются IconPath")
    ap.add_argument("--panel-styles", action="store_true", help="ещё и базовые стили панели (для пакета)")
    ap.add_argument("--report", action="store_true",
                    help="ничего не записывать: проверить схемы персонажей и показать контраст текста")
    a = ap.parse_args()
    if a.report:
        if not a.characters:
            ap.error("для --report нужен --characters")
        sys.exit(report(load_characters_arg(a.characters)))
    if a.refresh_user:
        for i in refresh_user_themes():
            print(i)
        return
    if not a.dest or not a.characters:
        ap.error("нужны --dest и --characters (или --refresh-user)")
    if a.panel_styles:
        for i in panel_styles(Path(a.dest)):
            print(i)
    chars = load_characters_arg(a.characters)
    for i in build(Path(a.dest), chars, Path(a.icons) if a.icons else None):
        print(i)


if __name__ == "__main__":
    main()
