"""Модель редактора палитры персонажа — БЕЗ Qt (поэтому её можно проверять тестами).

Дневная палитра по умолчанию выводится из ночной автоматически. Чтобы цвета дня можно было
выбрать самому, их правки лежат отдельно — в поле "UiPaletteDay" (и "AccentColorDay" для акцента
выделения): они накладываются поверх выведенного дня и одинаково действуют и в приложениях
Equestria, и в схеме KDE (Dolphin, Kate…).

Палитра персонажа не копируется в отдельный файл: цвета берутся из общего источника
(equestria_kit.themes.character_palette), а в characters.json, в поле "UiPalette", хранятся
только ПРАВКИ пользователя — те цвета, что отличаются от стандартных. Из этого:
  • у встроенного персонажа без правок поле пустое, и после обновления пакета он получает
    свежие стандартные цвета;
  • правки не теряются при перестройке тем и обновлениях;
  • «Сбросить цвета» — просто очистить UiPalette.

Все функции работают со словарём персонажа (как в characters.json)."""
from __future__ import annotations

import json
from pathlib import Path

import kde_laf

kit_themes, kit_palette = kde_laf.kit_themes, kde_laf.kit_palette

# Поля редактора. «@Имя» — поле самого персонажа (а не роль палитры).
# Простое — всегда на виду; «Дополнительно» — под кнопкой, чтобы не пугать лишним.
GROUPS = (
    ("surfaces", ("base", "mantle", "crust", "surface0")),
    ("text", ("text", "subtext")),
    ("accent", ("@AccentColor", "accent2")),
)
ADVANCED = ("accent", "surface1", "surface2", "green", "red", "yellow", "@HoverColor")

# То же для дня. Акцент выделения у дня свой (@AccentColorDay; пусто — как ночной).
# Цвет наведения (@HoverColor) у ночи и дня общий, поэтому в дневном наборе его нет.
GROUPS_DAY = (
    ("surfaces", ("base", "mantle", "crust", "surface0")),
    ("text", ("text", "subtext")),
    ("accent", ("@AccentColorDay", "accent2")),
)
ADVANCED_DAY = ("accent", "surface1", "surface2", "green", "red", "yellow")

NIGHT, DAY = "Dark", "Light"     # как варианты в kde_laf

EDITABLE = ("base", "mantle", "crust", "surface0", "surface1", "surface2",
            "text", "subtext", "accent", "accent2", "green", "red", "yellow")

# Тексты по умолчанию (ru, en). Переводы из locales/*.json (ключи pal.*) важнее:
# так редактор работает и там, где новых ключей в каталоге ещё нет.
TEXTS = {
    "pal.title": ("Цвета интерфейса", "Interface colors"),
    "pal.hint": ("Эти цвета получают и приложения Equestria, и Dolphin, Kate и другие программы KDE. "
                 "Ночные и дневные цвета выбираются отдельно. Пока вы не меняли день, он считается "
                 "из ночной палитры автоматически.",
                 "Equestria apps and KDE apps (Dolphin, Kate…) both use these colors. "
                 "Night and day colors are set separately. Until you change the day colors, "
                 "they are derived from the night palette automatically."),
    "pal.mode_tip": ("Какую половину пары менять: ночь или день.",
                     "Which half of the pair you are editing: night or day."),
    "pal.day_auto": ("День, пока не тронут, считается из ночи. Любой выбранный здесь цвет остаётся как есть.",
                     "Day is derived from night until you touch it. Any color you pick here is kept as is."),
    "pal.kde_bg": ("Фоны как в KDE", "KDE-style backgrounds"),
    "pal.kde_bg_tip": ("Для всего стиля: окна, списки, кнопки и заголовки — как в обычной теме KDE (Breeze). "
                       "От персонажа остаются акцент и выделение. Ваши цвета фонов не удаляются.",
                       "For the whole style: windows, lists, buttons and title bars look like the regular KDE "
                       "theme (Breeze). Only the character's accent and selection remain. Your background colors are kept."),
    "pal.reset_day": ("Вернуть цвета дня", "Restore day colors"),
    "pal.reset_day_tip": ("Убирает ваши правки только дневных цветов: день снова считается из ночи.",
                          "Discards only your day color edits: day is derived from night again."),
    "pal.grp_surfaces": ("Фоны", "Backgrounds"),
    "pal.grp_text": ("Текст", "Text"),
    "pal.grp_accent": ("Акценты", "Accents"),
    "pal.base": ("Фон окна и боковых панелей", "Window & sidebar background"),
    "pal.mantle": ("Фон областей просмотра", "View background (files, lists)"),
    "pal.crust": ("Заголовок и панели инструментов", "Title bar & toolbars"),
    "pal.surface0": ("Кнопки и карточки", "Buttons & cards"),
    "pal.text": ("Основной текст", "Main text"),
    "pal.subtext": ("Второстепенный текст", "Secondary text"),
    "pal.@AccentColor": ("Акцент и выделение", "Accent & selection"),
    "pal.@AccentColorDay": ("Акцент и выделение (день)", "Accent & selection (day)"),
    "pal.accent2": ("Второй акцент (ссылки)", "Second accent (links)"),
    "pal.accent": ("Акцент приложений Equestria", "Equestria apps accent"),
    "pal.surface1": ("Подсказки, наведение", "Tooltips, hover"),
    "pal.surface2": ("Выключенные элементы", "Disabled elements"),
    "pal.green": ("Успех", "Success"),
    "pal.red": ("Ошибка", "Error"),
    "pal.yellow": ("Предупреждение", "Warning"),
    "pal.@HoverColor": ("Цвет при наведении", "Hover color"),
    "pal.more": ("Дополнительно", "More colors"),
    "pal.less": ("Скрыть дополнительные", "Hide more colors"),
    "pal.reset": ("Вернуть стандартные цвета", "Restore default colors"),
    "pal.reset_tip": ("Отменяет ваши правки цветов этого персонажа (после «Сохранить» — применится).",
                      "Discards your color edits for this character (applied on Save)."),
    "pal.night": ("Ночь", "Night"),
    "pal.day": ("День", "Day"),
    "pal.warn": ("Низкий контраст: {0} на фоне «{1}» — {2}:1. KDE подправит цвет текста, чтобы его можно было читать.",
                 "Low contrast: {0} on “{1}” is {2}:1. KDE will adjust the text color so it stays readable."),
    "pal.pick": ("Выберите цвет", "Pick a color"),
}


def text(key: str, tr=None, lang: str = "en") -> str:
    """Текст интерфейса: перевод из каталога, а если его нет — встроенный."""
    if tr is not None:
        got = str(tr(key))
        if got and got != key:
            return got
    ru, en = TEXTS.get(key, (key, key))
    return ru if str(lang).lower().startswith("ru") else en


def clean(own) -> dict:
    """Оставить в UiPalette только известные роли с настоящими цветами (файл мог прийти извне)."""
    return kit_themes.clean_ui_palette(own)


def clean_color(v) -> str:
    """Один цвет ('#rrggbb') или пустая строка, если это не цвет."""
    return v.lower() if isinstance(v, str) and kit_palette.is_hex(v) else ""


def _with_no_overrides(ch: dict) -> dict:
    return {**ch, "UiPalette": {}, "UiPaletteDay": {}}


def baseline(ch: dict) -> dict:
    """Стандартные цвета персонажа (ночь) — без правок пользователя."""
    return kit_palette.with_derived(kit_themes.character_palette(_with_no_overrides(ch), overrides=False))


def effective(ch: dict) -> dict:
    """Цвета персонажа с учётом правок — ровно то, что получают приложения и схемы KDE.
    Свои цвета дня лежат внутри под ключами day_* (их разбирает kde_laf.variant_palettes)."""
    return kit_palette.with_derived(kit_themes.character_palette(ch))


def day_effective(ch: dict) -> dict:
    """Дневная палитра как она получится: выведенная из ночи + свои цвета дня."""
    return kde_laf.variant_palettes(effective(ch))[DAY]


def day_baseline(ch: dict) -> dict:
    """День без СВОИХ цветов дня (но с учётом правок ночи, из которой он выводится)."""
    return kde_laf.variant_palettes(effective({**ch, "UiPaletteDay": {}}))[DAY]


def _own_key(variant: str) -> str:
    return "UiPaletteDay" if variant == DAY else "UiPalette"


def value(ch: dict, key: str, variant: str = NIGHT) -> str:
    """Текущий цвет поля редактора ('#rrggbb') для ночи или дня."""
    if key.startswith("@"):
        if key == "@AccentColorDay":
            return str(ch.get("AccentColorDay") or ch.get("AccentColor") or "#ffffff")
        return str(ch.get(key[1:]) or "#ffffff")
    pal = day_effective(ch) if variant == DAY else effective(ch)
    return pal.get(key, "#ffffff")


def set_value(ch: dict, key: str, color: str, variant: str = NIGHT) -> None:
    """Записать цвет поля. Цвет, совпавший со стандартным (для дня — с выведенным), правкой не считается."""
    color = color.lower()
    if key.startswith("@"):
        if key == "@AccentColorDay":
            # цвет, совпавший с ночным акцентом, — это «как ночью»: отдельный не храним
            ch["AccentColorDay"] = "" if color == str(ch.get("AccentColor") or "").lower() else color
        else:
            ch[key[1:]] = color
        return
    name = _own_key(variant)
    own = ch.get(name)
    if not isinstance(own, dict):
        own = ch[name] = {}
    base = day_baseline(ch) if variant == DAY else baseline(ch)
    if color == base.get(key, "").lower():
        own.pop(key, None)
    else:
        own[key] = color


def has_edits(ch: dict, variant: str | None = None) -> bool:
    night = bool(clean(ch.get("UiPalette")))
    day = bool(clean(ch.get("UiPaletteDay"))) or bool(str(ch.get("AccentColorDay") or "").strip())
    return night if variant == NIGHT else day if variant == DAY else (night or day)


def reset_day(ch: dict) -> None:
    """Убрать только свои цвета дня: он снова выводится из ночи."""
    ch["UiPaletteDay"] = {}
    ch["AccentColorDay"] = ""


def system_character(char_id: str, system_json: Path) -> dict | None:
    """Заводская версия встроенного персонажа (из пакета), если он там есть."""
    try:
        data = json.loads(Path(system_json).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for c in data.get("Characters", []) if isinstance(data, dict) else []:
        if isinstance(c, dict) and c.get("Id") == char_id:
            return c
    return None


def freeze(ch: dict, new_id: str) -> dict:
    """UiPalette для КОПИИ персонажа под другим Id. У встроенных персонажей палитра
    «спроектирована» и привязана к Id; копия иначе получила бы выведенную, другую.
    Возвращает правки, которые делают копию точно такой же, как исходник."""
    want = effective(ch)
    base = baseline({**ch, "Id": new_id})
    return {k: v for k, v in want.items()
            if (k in EDITABLE or k.endswith("_text")) and str(v).lower() != str(base.get(k, "")).lower()}


def freeze_day(ch: dict, new_id: str, new_night: dict) -> dict:
    """UiPaletteDay для копии: правки дня, которых не хватает копии (с уже готовой ночью
    new_night из freeze), чтобы её день совпал с днём исходника."""
    want = day_effective(ch)
    copy = {**ch, "Id": new_id, "UiPalette": new_night, "UiPaletteDay": {}}
    base = day_effective(copy)
    return {k: v for k, v in want.items()
            if (k in EDITABLE or k.endswith("_text")) and str(v).lower() != str(base.get(k, "")).lower()}
