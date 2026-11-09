"""color-picker: formats."""
from __future__ import annotations

import time
from .color import try_render
from .localization import catalog, tr


BUILTIN = [
    ("formats.web", "#RRGGBB", "#{hex}"),
    ("formats.web", "#RRGGBBAA", "#{hexa}"),
    ("formats.web", "formats.rgb_if_possible", "#{hexs}"),
    ("formats.web", "formats.rrggbb_without", "{hex}"),
    ("formats.web", "rgb()", "rgb({r}, {g}, {b})"),
    ("formats.web", "rgba()", "rgba({r}, {g}, {b}, {af})"),
    ("formats.web", "formats.rgb_modern", "rgb({r} {g} {b} / {ap}%)"),
    ("formats.web", "hsl()", "hsl({h}, {s}%, {l}%)"),
    ("formats.web", "hsla()", "hsla({h}, {s}%, {l}%, {af})"),
    ("formats.web", "oklch()", "oklch({ol}% {oc} {oh})"),
    ("formats.web", "formats.css_variable", "--color: #{hex};"),
    ("formats.web", "Tailwind bg-[…]", "bg-[#{hex}]"),
    ("Unity", "Color (float)", "new Color({rf}f, {gf}f, {bf}f, {af}f)"),
    ("Unity", "Color32 (0–255)", "new Color32({r}, {g}, {b}, {a})"),
    ("Unity", "formats.color_linear", "new Color({lr}f, {lg}f, {lb}f, {af}f)"),
    ("Unity", "formats.hex_inspector_rrggbbaa", "{hexa}"),
    ("Unity", "ColorUtility.TryParseHtmlString", 'ColorUtility.TryParseHtmlString("#{hexa}", out Color color);'),
    ("Unity", "Color.HSVToRGB", "Color.HSVToRGB({hf}f, {sf}f, {vf}f)"),
    ("Unity", "Vector4", "new Vector4({rf}f, {gf}f, {bf}f, {af}f)"),
    ("Unity", "Rich Text", "<color=#{hexa}></color>"),
    ("Unity", "USS / UI Toolkit", "color: rgba({r}, {g}, {b}, {af});"),
    ("Unity", "Shader float4", "float4({rf}, {gf}, {bf}, {af})"),
    ("Unreal", "formats.flinearcolor_linear", "(R={lr},G={lg},B={lb},A={af})"),
    ("Unreal", "formats.flinearcolor_as_srgb", "(R={rf},G={gf},B={bf},A={af})"),
    ("Unreal", "FColor", "FColor({r}, {g}, {b}, {a})"),
    ("Unreal", "FLinearColor C++", "FLinearColor({lr}f, {lg}f, {lb}f, {af}f)"),
    ("Unreal", "formats.fcolor_from_hex", 'FColor::FromHex(TEXT("{hexa}"))'),
    ("Godot", "Color()", "Color({rf}, {gf}, {bf}, {af})"),
    ("Godot", "Color8()", "Color8({r}, {g}, {b}, {a})"),
    ("Godot", "formats.color_from_hex", 'Color("#{hexa}")'),
    ("Godot", "Color.from_hsv", "Color.from_hsv({hf}, {sf}, {vf}, {af})"),
    ("Qt / QML", "Qt.rgba()", "Qt.rgba({rf}, {gf}, {bf}, {af})"),
    ("Qt / QML", "QColor (0–255)", "QColor({r}, {g}, {b}, {a})"),
    ("Qt / QML", "QML #AARRGGBB", '"#{ahex}"'),
    ("Qt / QML", "QColor::fromRgbF", "QColor::fromRgbF({rf}, {gf}, {bf}, {af})"),
    ("Qt / QML", "QSS rgba()", "rgba({r}, {g}, {b}, {a})"),
    ("Android", "#AARRGGBB", "#{ahex}"),
    ("Android", "Color.argb()", "Color.argb({a}, {r}, {g}, {b})"),
    ("Android", "formats.xml_resource", '<color name="color">#{ahex}</color>'),
    ("Android", "Compose Color", "Color(0x{ahex})"),
    ("Android", "Color.parseColor", 'Color.parseColor("#{ahex}")'),
    ("Flutter", "Color(0xAARRGGBB)", "Color(0x{ahex})"),
    ("Flutter", "Color.fromARGB", "Color.fromARGB({a}, {r}, {g}, {b})"),
    ("Flutter", "Color.fromRGBO", "Color.fromRGBO({r}, {g}, {b}, {af})"),
    ("Apple", "UIColor", "UIColor(red: {rf}, green: {gf}, blue: {bf}, alpha: {af})"),
    ("Apple", "SwiftUI Color", "Color(red: {rf}, green: {gf}, blue: {bf}, opacity: {af})"),
    ("Apple", "NSColor", "NSColor(srgbRed: {rf}, green: {gf}, blue: {bf}, alpha: {af})"),
    ("Apple", "#colorLiteral", "#colorLiteral(red: {rf}, green: {gf}, blue: {bf}, alpha: {af})"),
    ("formats.code", "GLSL vec3", "vec3({rf}, {gf}, {bf})"),
    ("formats.code", "GLSL vec4", "vec4({rf}, {gf}, {bf}, {af})"),
    ("formats.code", "formats.float_array", "[{rf}, {gf}, {bf}, {af}]"),
    ("formats.code", "formats.tuple_0_255", "({r}, {g}, {b})"),
    ("formats.code", "formats.rgba_tuple_0_255", "({r}, {g}, {b}, {a})"),
    ("formats.code", "0xRRGGBB", "0x{hex}"),
    ("formats.code", "formats.integer", "{int}"),
    ("formats.code", "Java Color", "new Color({r}, {g}, {b})"),
    ("formats.code", "formats.ansi_escape_text", "\\x1b[38;2;{r};{g};{b}m"),
    ("formats.code", "LaTeX xcolor", "\\definecolor{{color}}{{RGB}}{{{r},{g},{b}}}"),
    ("formats.models", "RGB", "{r}, {g}, {b}"),
    ("formats.models", "HSL", "{h}°, {s}%, {l}%"),
    ("formats.models", "HSV", "{h}°, {sv}%, {v}%"),
    ("formats.models", "CMYK", "{c}%, {m}%, {y}%, {k}%"),
    ("formats.models", "Linear RGB", "{lr}, {lg}, {lb}"),
    ("formats.models", "OKLCH", "{ol}%, {oc}, {oh}°"),
]


MY = "formats.mine"


CATS = ["common.all"] + list(dict.fromkeys(c for c, _, _ in BUILTIN)) + [MY]


DEFAULT_PRIMARY = "formats.web_rrggbb"


HELP_FIELDS = (tr("formats.fields_0_255_0_1"))


class FormatBook:
    """Форматы копирования: встроенные + свои (cfg["customs"]) и основной (cfg["primary"]).
    Хранит всё прямо в словаре настроек — окну остаётся только сохранить его."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.formats: dict[str, tuple] = {}   # id -> (категория, название, шаблон, свой ли)

    def reload(self) -> None:
        self.formats = {f"{c}|{n}": (c, n, t, False) for c, n, t in BUILTIN}
        for cf in self.cfg["customs"]:
            self.formats[cf["id"]] = (MY, cf["name"], cf["tpl"], True)
        if self.cfg["primary"] not in self.formats:
            # Older releases saved translated category/name pairs as identifiers.
            previous = self.cfg["primary"]
            replacement = None
            for fid, (category, name, _template, custom) in self.formats.items():
                if custom:
                    continue
                for entries in catalog.translations.values():
                    legacy = f"{entries.get(category, category)}|{entries.get(name, name)}"
                    if previous == legacy or previous == entries.get(fid):
                        replacement = fid
                        break
                if replacement:
                    break
            self.cfg["primary"] = replacement or DEFAULT_PRIMARY

    @property
    def primary(self) -> str:
        return self.cfg["primary"]

    @primary.setter
    def primary(self, fid: str) -> None:
        self.cfg["primary"] = fid

    def matching(self, cat: str, query: str) -> list:
        """id форматов категории cat ("Все" — любой), где query есть в названии, категории или шаблоне."""
        q = query.strip().lower()
        out = []
        for fid, (c, n, t, _custom) in self.formats.items():
            if cat != "common.all" and c != cat:
                continue
            # искать по тому, что видно на экране: переведённые категория и название
            shown = (str(tr(c)), n if _custom else str(tr(n)))
            if q and q not in shown[1].lower() and q not in shown[0].lower() and q not in t.lower():
                continue
            out.append(fid)
        return out

    def render(self, fid: str, fl: dict):
        """Значение формата или None, если в шаблоне ошибка."""
        return try_render(self.formats[fid][2], fl)

    def save_custom(self, fid, name: str, tpl: str) -> str:
        """Изменить свой формат fid или (fid=None) добавить новый; возвращает его id."""
        if fid:
            for cf in self.cfg["customs"]:
                if cf["id"] == fid:
                    cf["name"], cf["tpl"] = name, tpl
        else:
            fid = f"custom|{int(time.time() * 1000)}"
            self.cfg["customs"].append({"id": fid, "name": name, "tpl": tpl})
        self.reload()
        return fid

    def delete_custom(self, fid: str) -> None:
        self.cfg["customs"] = [c for c in self.cfg["customs"] if c["id"] != fid]
        self.reload()
