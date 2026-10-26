"""Глобальные темы KDE для персонажей — пара «день/ночь» на каждого.

    Equestria-<id>        день: светлая схема Breeze с акцентом персонажа, курсор Vimix-white
    Equestria-<id>-Dark   ночь: тёмная схема Breeze с акцентом персонажа, курсор Vimix

KDE сам переключает пару по времени суток: переключатель записывает их в
kdeglobals [KDE] DefaultLightLookAndFeel / DefaultDarkLookAndFeel.

В теме только цвета, курсор и заставка. Иконки, шрифты, стиль окон и обои
сюда не входят: тему KDE переприменяет утром и вечером, и всё записанное
здесь перебивало бы выбор пользователя.

Один и тот же код работает в двух местах:
  • при сборке пакета — для встроенных персонажей, в $pkgdir/usr/share;
  • в переключателе — для своих персонажей, в ~/.local/share.

    python3 kde_laf.py --dest DIR/usr/share --characters characters.json [--icons DIR]
"""
from __future__ import annotations

import argparse
import configparser
import hashlib
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

VARIANTS = {  # вариант -> (базовая схема Breeze, курсор, суффикс id темы)
    "Light": ("BreezeLight.colors", "Vimix-white-cursors", ""),
    "Dark": ("BreezeDark.colors", "Vimix-cursors", "-Dark"),
}
SYSTEM_COLORS = Path("/usr/share/color-schemes")
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


def color_scheme(base_text: str, accent_hex: str, name: str) -> str:
    """Схема Breeze, где выделение и подсветка фокуса — цвет персонажа."""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str  # ключи KDE чувствительны к регистру
    cp.read_string(base_text)
    accent = _rgb(accent_hex)
    for sec in cp.sections():
        if not sec.startswith("Colors:"):
            continue
        for key in ("DecorationFocus", "DecorationHover"):
            if key in cp[sec]:
                cp[sec][key] = _fmt(accent)
    if cp.has_section("Colors:Selection"):
        sel = cp["Colors:Selection"]
        view = cp["Colors:View"] if cp.has_section("Colors:View") else {}
        bg = tuple(int(c) for c in view.get("BackgroundNormal", "255,255,255").split(",")[:3])
        sel["BackgroundNormal"] = _fmt(accent)
        sel["BackgroundAlternate"] = _fmt(_mix(accent, bg, 0.35))
        sel["DecorationFocus"] = _fmt(accent)
        sel["DecorationHover"] = _fmt(accent)
        on = _fmt(_on(accent))
        for key in ("ForegroundNormal", "ForegroundActive"):
            if key in sel:
                sel[key] = on
    if not cp.has_section("General"):
        cp.add_section("General")
    cp["General"]["Name"] = name
    cp["General"]["ColorScheme"] = name
    out = io.StringIO()
    out.write("# Equestria OS: цветовая схема Breeze (KDE) с акцентом персонажа.\n"
              "# SPDX-License-Identifier: LGPL-2.0-or-later\n\n")
    cp.write(out, space_around_delimiters=False)
    return out.getvalue()


def _defaults(variant: str, scheme: str) -> str:
    return (f"[kdeglobals][General]\nColorScheme={scheme}\n\n"
            f"[kcminputrc][Mouse]\ncursorTheme={VARIANTS[variant][1]}\n\n"
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
            "Version": "2.0",
        },
    }
    return json.dumps(meta, ensure_ascii=False, indent=4) + "\n"


def build(dest_share: Path, characters: list, icons: Path | None = None,
          colors_dir: Path = SYSTEM_COLORS) -> list[str]:
    """Создать цветовые схемы и глобальные темы. characters — словари с Id,
    DisplayName, AccentColor, IconPath. Возвращает id созданных тем."""
    dest_share = Path(dest_share)
    made = []
    for ch in characters:
        cid = str(ch.get("Id") or "").strip()
        if not cid:
            continue
        display = str(ch.get("DisplayName") or cid)
        accent = str(ch.get("AccentColor") or "#3daee9")
        icon = Path(icons, ch["IconPath"]) if icons and ch.get("IconPath") else None
        for variant, (base, _cursor, _sfx) in VARIANTS.items():
            scheme = scheme_name(cid, variant)
            cdir = dest_share / "color-schemes"
            cdir.mkdir(parents=True, exist_ok=True)
            (cdir / f"{scheme}.colors").write_text(
                color_scheme((colors_dir / base).read_text(encoding="utf-8"), accent, scheme), encoding="utf-8")
            pkg = dest_share / "plasma" / "look-and-feel" / laf_id(cid, variant)
            (pkg / "contents").mkdir(parents=True, exist_ok=True)
            (pkg / "metadata.json").write_text(_metadata(cid, display, variant), encoding="utf-8")
            (pkg / "contents" / "defaults").write_text(_defaults(variant, scheme), encoding="utf-8")
            if icon and icon.is_file():
                (pkg / "contents" / "previews").mkdir(exist_ok=True)
                shutil.copyfile(icon, pkg / "contents" / "previews" / "preview.png")
            made.append(laf_id(cid, variant))
    return made


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

    def _read(self, key: str) -> str:
        r = self._run(["kreadconfig6", "--file", "kdeglobals", "--group", "KDE", "--key", key],
                      capture_output=True, text=True)
        return (r.stdout or "").strip()

    def _write(self, key: str, value: str) -> None:
        # --notify: модуль автосмены KDE (lookandfeelautoswitcher) следит за изменениями
        self._run(["kwriteconfig6", "--file", "kdeglobals", "--group", "KDE", "--key", key, value, "--notify"],
                  capture_output=True)

    def pair(self) -> tuple[str, str]:
        return (self._read("DefaultLightLookAndFeel") or BREEZE_LIGHT,
                self._read("DefaultDarkLookAndFeel") or BREEZE_DARK)

    def is_dark_now(self) -> bool:
        """Сейчас активна ночная половина пары (так же решает виджет KDE)."""
        current = self._read("LookAndFeelPackage")
        return bool(current) and (current == self.pair()[1] or current.endswith("-Dark")
                                  or current == BREEZE_DARK)

    def mode(self) -> str:
        if self._read("AutomaticLookAndFeel").lower() == "true":
            return "auto"
        return "dark" if self.is_dark_now() else "light"

    def set_pair(self, light: str, dark: str) -> None:
        self._write("DefaultLightLookAndFeel", light)
        self._write("DefaultDarkLookAndFeel", dark)

    def apply(self, laf: str) -> None:
        # --keep-auto: без него команда выключила бы автоматическую смену
        self._run(["plasma-apply-lookandfeel", "--apply", laf, "--keep-auto"], capture_output=True)

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(mode)
        if mode == "auto":
            self._write("AutomaticLookAndFeel", "true")  # KDE сам применит тему для текущего времени
            return
        self._write("AutomaticLookAndFeel", "false")
        light, dark = self.pair()
        self.apply(dark if mode == "dark" else light)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", required=True, help="каталог share (например $pkgdir/usr/share)")
    ap.add_argument("--characters", required=True, help="characters.json")
    ap.add_argument("--icons", help="каталог, от которого отсчитываются IconPath")
    a = ap.parse_args()
    chars = json.loads(Path(a.characters).read_text(encoding="utf-8")).get("Characters", [])
    for i in build(Path(a.dest), chars, Path(a.icons) if a.icons else None):
        print(i)


if __name__ == "__main__":
    main()
