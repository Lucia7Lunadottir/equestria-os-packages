# -*- coding: utf-8 -*-
"""
Единые цветовые темы Equestria OS для всех PyQt6-приложений.

Откуда берутся темы (по порядку, поздние перекрывают ранние):
  1. запасная   — Catppuccin Mocha (основа для недостающих цветов);
  2. персонажи  — characters.json переключателя «Тема персонажа» (и свои персонажи);
  3. системные  — /usr/share/equestria-os/themes/*.json;
  4. свои       — ~/.config/equestria-os/themes/*.json.
Списка персонажей в коде нет: новый персонаж в characters.json сразу становится темой.

Формат файла темы (недостающие цвета берутся из Catppuccin Mocha):
    {"name": "Моя тема", "colors": {"base": "#101010", "accent": "#ffcc00", ...}}

Выбор темы:
  • «Как в системе» (SYSTEM, по умолчанию) — персонаж, выбранный в переключателе;
    приложение перекрашивается вслед за ним;
  • конкретная тема — только для этого приложения
    (~/.config/equestria-os/app-themes/<приложение>.json); общий выбор она не меняет.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol

# Что значит каждый цвет:
#   base      — фон окна              mantle   — чуть темнее фона
#   crust     — самый тёмный          surface0 — карточки и кнопки
#   surface1  — кнопка при наведении  surface2 — выключенные элементы
#   text      — основной текст        subtext  — второстепенный текст
#   accent    — главный цвет (кнопки, цифры, активная вкладка)
#   green / red / yellow — статусы «ок / ошибка / предупреждение»
KEYS = ("base", "mantle", "crust", "surface0", "surface1", "surface2",
        "text", "subtext", "accent", "green", "red", "yellow")

DEFAULT_THEME = "Catppuccin Mocha"

SYSTEM = ""   # выбор «Как в системе»: тема персонажа из переключателя

# Единственная тема в коде — нейтральная запасная (и основа недостающих цветов).
# Темы персонажей берутся только из characters.json.
_FALLBACK_RAW = "#1e1e2e #181825 #11111b #313244 #45475a #585b70 #cdd6f4 #a6adc8 #cba6f7 #a6e3a1 #f38ba8 #f9e2af"


@dataclass(frozen=True)
class Theme:
    """Одна тема: имя + 12 цветов."""
    name: str
    colors: dict

    @classmethod
    def from_mapping(cls, name: str, colors: dict, fallback: "Theme | None" = None) -> "Theme":
        merged = dict(fallback.colors) if fallback else {}
        for k, v in (colors or {}).items():
            if k in KEYS and isinstance(v, str) and _is_hex(v):
                merged[k] = v
        return cls(str(name), merged)


def _is_hex(v: str) -> bool:
    s = v.lstrip("#")
    return v.startswith("#") and len(s) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in s)


# ── источники тем (Open/Closed: новый источник = новый класс) ──────────────
class ThemeSource(Protocol):
    def load(self, fallback: Theme) -> Iterable[Theme]: ...


class BuiltinThemes:
    def load(self, fallback: Theme) -> Iterable[Theme]:
        yield fallback


class JsonDirThemes:
    """Папка с файлами *.json, по одной теме в файле."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def load(self, fallback: Theme) -> Iterable[Theme]:
        for path in sorted(self.folder.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                yield Theme.from_mapping(data.get("name") or path.stem, data.get("colors") or data, fallback)


class JsonDictThemes:
    """Старый формат одного файла {"Имя": {цвета}, ...} (например themes.json часов)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, fallback: Theme) -> Iterable[Theme]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            for name, pal in data.items():
                if isinstance(pal, dict):
                    yield Theme.from_mapping(name, pal, fallback)


CHARACTER_DIR = Path.home() / ".local/share/EquestriaOS/Themes"   # USER_PATH переключателя
CHARACTER_SYSTEM_JSON = Path("/opt/equestria-os/equestria-os-character-theme/characters.json")


def _rgb(v) -> str | None:
    """'37,18,16' (Konsole) или '#e54c35' → '#rrggbb'."""
    if not isinstance(v, str):
        return None
    v = v.strip()
    if v.startswith("#"):
        return v.lower() if _is_hex(v) else None
    try:
        r, g, b = (max(0, min(255, int(x))) for x in v.split(",")[:3])
    except ValueError:
        return None
    return f"#{r:02x}{g:02x}{b:02x}"


def _mix(a: str, b: str, k: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * k):02x}" for x, y in zip(ca, cb))


def _hue_sat(h: str) -> tuple:
    import colorsys
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return hh * 360, ss, ll


def _hue_gap(a: str, b: str) -> float:
    d = abs(_hue_sat(a)[0] - _hue_sat(b)[0]) % 360
    return min(d, 360 - d)


def _desaturate(h: str, k: float) -> str:
    """Убрать долю k насыщенности, сохранив яркость."""
    import colorsys
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(hh, ll, ss * (1 - k))
    return "#" + "".join(f"{round(x * 255):02x}" for x in (r, g, b))


# Спроектированные палитры персонажей (по каноничным цветам). Правила:
#   фон — тёмный, почти нейтральный, с лёгким оттенком персонажа;
#   accent  — главный цвет персонажа: кнопки, переключатели, выделение;
#   accent2 — второй цвет персонажа: заголовки секций, ссылки;
#   red/green/yellow — статусы, red всегда отличим от accent;
#   text/subtext — почти белый с оттенком персонажа и приглушённый.
# Свой персонаж может задать палитру полем "UiPalette" в characters.json.
_PAL_KEYS = KEYS + ("accent2",)
DESIGNED_PALETTES = {
    # Сансет: красно-жёлтая — винно-угольный фон, чистый жёлтый для действий, огненный красный в заголовках
    "sunset":     "#1d1416 #171012 #100b0c #2b1d20 #38262a #4c3338 #fbeeea #d0aeab #ffcf33 #9fd67a #ff4d6d #ffe066 #ff5a4a",
    # Сай-Твай: лаванда шёрстки + малиновая полоса гривы
    "twilight":   "#17141f #120f19 #0c0a12 #241f30 #302940 #433a57 #efe9fb #b5a9cc #b48cf0 #8fd9a8 #ff6b7f #f6d67a #e8689f",
    # Рэйнбоу: небесно-голубой + жёлтая полоса радуги
    "rainbow":    "#121820 #0e131a #090d12 #1c2530 #263241 #354559 #eaf5ff #a6bdd1 #5cc2f2 #7ad98a #ff6464 #ffb648 #ffd75e",
    # Рарити: фиолет гривы + голубой бриллиант, белоснежный текст
    "rarity":     "#15141b #111016 #0b0a0f #211f2b #2c2939 #3e3a50 #f6f5fb #b9b6cc #9d8cf0 #8edcb2 #ff7a9a #f2df9a #6fd0f5",
    # Пинки: ярко-розовая грива + голубой шарик
    "pinkie":     "#1c1219 #170f14 #10090e #2b1c26 #382532 #4c3445 #fdedf5 #cfa9bd #f45ea6 #8fe0a6 #ff5c5c #ffd86b #68c8f0",
    # Эпплджек: деревенская — оливково-коричневый фон, оранжевая шёрстка для действий, зелёный лист в заголовках
    "applejack":  "#1b1710 #16130d #0f0d09 #2a2418 #362e1f #4a402c #fdf3dc #cbb78f #f39a3d #8ccf5a #e0503f #ffe08a #8ccf5a",
    # Флаттершай: нежно-розовая грива + бирюза бабочек, шалфейный фон
    "fluttershy": "#161a15 #121511 #0c0f0b #222820 #2d352a #3f4a3b #f6faee #b6c4ad #f4a6c8 #a8dc8a #ff7a8a #fbe58a #6fd3c7",
}

# Необязательные доп. роли: <роль>_text — цвет этой роли, когда она стоит ТЕКСТОМ
# (заливки остаются яркими). У Пинки розовый текст пастельный, кнопки — яркие.
DESIGNED_EXTRAS = {
    "pinkie": {"accent_text": "#f7b6d4"},
}


class CharacterThemes:
    """Темы из переключателя «Тема персонажа» (equestria-os-character-theme):
    и встроенные персонажи, и созданные/импортированные пользователем.
    Палитра выводится из цветов персонажа: фон/текст — из его схемы Konsole,
    акцент — AccentColor, карточки — фон с примесью акцента, а «ок/ошибка/
    предупреждение» берутся из его же цветов, если там есть зелёный/красный/жёлтый."""

    _STATUS = {"green": (85, 165, "#a6e3a1"), "red": (345, 375, "#f38ba8"), "yellow": (40, 66, "#f9e2af")}

    def __init__(self, user_dir: Path = None, system_json: Path = None):
        self.user_dir = Path(user_dir or CHARACTER_DIR)
        self.system_json = Path(system_json or CHARACTER_SYSTEM_JSON)

    def characters(self) -> list:
        for path in (self.user_dir / "characters.json", self.system_json):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                chars = data.get("Characters") if isinstance(data, dict) else None
                if isinstance(chars, list):
                    return [c for c in chars if isinstance(c, dict)]
            except (OSError, ValueError):
                continue
        return []

    def load(self, fallback: Theme) -> Iterable[Theme]:
        for c in self.characters():
            colors = self.palette_of(c, fallback.colors)
            if colors:
                yield Theme(str(c.get("DisplayName") or c.get("Id")), colors)

    def palette_of(self, c: dict, fb: dict) -> dict | None:
        designed = DESIGNED_PALETTES.get(str(c.get("Id")))
        if designed:
            pal = dict(zip(_PAL_KEYS, designed.split()))
            pal.update(DESIGNED_EXTRAS.get(str(c.get("Id")), {}))
            return pal
        own = c.get("UiPalette")
        if isinstance(own, dict):   # палитра, заданная пользователем для своего персонажа
            base = self._derived(c) or dict(fb)
            base.update({k: v for k, v in own.items()
                         if (k in _PAL_KEYS or k.endswith("_text")) and isinstance(v, str) and _is_hex(v)})
            return base
        return self._derived(c)

    def _derived(self, c: dict) -> dict | None:
        """Палитра для своего персонажа без UiPalette — по тем же правилам из его цветов."""
        k = c.get("KonsoleTheme") or {}
        bg, fg, acc = _rgb(k.get("Background")), _rgb(k.get("Foreground")), _rgb(c.get("AccentColor"))
        if not (bg and fg and acc):
            return None
        black = "#000000"
        # Фон: тёплый/холодный оттенок персонажа, но спокойнее — насыщенный
        # цветной фон (красный у Сансет) утомляет глаза и съедает различия.
        bg = _desaturate(bg, .55)
        ansi = [_rgb(v) for key, v in k.items() if key.startswith("Color")]
        status = {role: next((h for h in ansi if h and self._fits(h, lo, hi)), default)
                  for role, (lo, hi, default) in self._STATUS.items()}
        second = self._second_color(acc, ansi) or _mix(acc, fg, .40)
        primary, brand = acc, second
        # Если акцент того же оттенка, что «опасный» красный, кнопки «Создать» и
        # «Удалить» становятся неразличимы. Тогда основным действиям — второй цвет
        # персонажа (у Сансет — золотой), а её красный — фирменный/опасный.
        if _hue_gap(acc, status["red"]) < 25 and _hue_gap(second, status["red"]) > 25:
            primary, brand = second, acc

        def surface(k_fg, k_acc):
            return _mix(_mix(bg, fg, k_fg), primary, k_acc)
        pal = {"base": bg, "mantle": _mix(bg, black, .18), "crust": _mix(bg, black, .35),
               "surface0": surface(.06, .04), "surface1": surface(.11, .05), "surface2": surface(.20, .07),
               "text": fg, "subtext": _mix(fg, bg, .22), "accent": primary, "accent2": brand}
        pal.update(status)
        return pal

    @staticmethod
    def _second_color(acc: str, ansi: list) -> str | None:
        """Второй цвет персонажа (у Сансет — жёлтый к красному): самый насыщенный
        яркий цвет его палитры, заметно отличающийся по оттенку от акцента."""
        ah = _hue_sat(acc)[0]
        best, best_sat = None, .45
        for h in ansi:
            if not h:
                continue
            hue, sat, light = _hue_sat(h)
            d = abs(hue - ah) % 360
            if min(d, 360 - d) > 25 and .35 < light < .85 and sat > best_sat:
                best, best_sat = h, sat
        return best

    @staticmethod
    def _fits(h: str, lo: float, hi: float) -> bool:
        """Яркий (не почти чёрный/белый) цвет нужного оттенка."""
        hue, sat, light = _hue_sat(h)
        return sat > .45 and .3 < light < .85 and (lo <= hue <= hi or lo <= hue + 360 <= hi)

    def active_name(self) -> str:
        """Имя выбранного в переключателе персонажа ("" — не выбран)."""
        try:
            active = json.loads((self.user_dir / "state.json").read_text(encoding="utf-8")).get("active_character")
        except (OSError, ValueError, AttributeError):
            return ""
        c = next((c for c in self.characters() if c.get("Id") == active), None)
        return str(c.get("DisplayName") or c.get("Id")) if c else ""

    def changed_at(self) -> float:
        try:
            return (self.user_dir / "state.json").stat().st_mtime
        except OSError:
            return 0.0


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-os"


SYSTEM_THEMES_DIR = Path("/usr/share/equestria-os/themes")


class ThemeRegistry:
    """Собирает темы из всех источников. palettes — живой словарь имя → цвета:
    reload() обновляет его на месте, поэтому `for name in THEMES` в приложениях
    сразу видит новые темы."""

    def __init__(self, sources: list | None = None):
        self.sources: list = sources if sources is not None else [
            BuiltinThemes(), CHARACTERS, JsonDirThemes(SYSTEM_THEMES_DIR), JsonDirThemes(config_dir() / "themes")]
        self.palettes: dict = {}
        self.reload()

    def add_source(self, source) -> None:
        self.sources.append(source)
        self.reload()

    def reload(self) -> None:
        fallback = Theme(DEFAULT_THEME, dict(zip(KEYS, _FALLBACK_RAW.split())))
        found: dict = {}
        for src in self.sources:
            for theme in src.load(fallback):
                found[theme.name] = theme.colors
        self.palettes.clear()
        self.palettes.update(found)

    def resolve(self, name) -> str:
        return name if name in self.palettes else DEFAULT_THEME


class SystemTheme:
    """Тема «Как в системе» — персонаж, выбранный в переключателе тем.
    Старые версии библиотеки писали общий theme.json из меню приложений; он
    только читается и только если персонаж не выбран (переключатель не запускали)."""

    def __init__(self, characters: "CharacterThemes", legacy_path: Path | None = None):
        self.characters = characters
        self.legacy_path = legacy_path or config_dir() / "theme.json"

    def name(self) -> str:
        active = self.characters.active_name()
        if active:
            return active
        try:
            name = json.loads(self.legacy_path.read_text(encoding="utf-8")).get("theme")
            if isinstance(name, str) and name:
                return name
        except (OSError, ValueError, AttributeError):
            pass
        return DEFAULT_THEME


class AppThemeChoice:
    """Тема одного приложения: SYSTEM («Как в системе») или имя темы.
    Файл свой у каждого приложения, поэтому выбор в одном не трогает остальные.
    Имя приложения — QApplication.applicationName() (его ставят все приложения)."""

    def __init__(self, folder: Path | None = None, app_key: str | None = None):
        self.folder = folder or config_dir() / "app-themes"
        self._app_key = app_key

    @property
    def app_key(self) -> str:
        if self._app_key:
            return self._app_key
        name = ""
        try:
            from PyQt6.QtCore import QCoreApplication
            name = QCoreApplication.applicationName()
        except ImportError:
            pass
        if not name or name.startswith("python"):
            import sys
            name = Path(sys.argv[0]).stem if sys.argv and sys.argv[0] else "app"
        return "".join(ch if ch.isalnum() else "-" for ch in name.strip().lower()).strip("-") or "app"

    @property
    def path(self) -> Path:
        return self.folder / f"{self.app_key}.json"

    def load(self) -> str:
        try:
            name = json.loads(self.path.read_text(encoding="utf-8")).get("theme")
            return name if isinstance(name, str) else SYSTEM
        except (OSError, ValueError, AttributeError):
            return SYSTEM

    def save(self, choice: str) -> None:
        if self.load() == choice:
            return
        try:
            if choice == SYSTEM:
                self.path.unlink(missing_ok=True)
                return
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"theme": choice}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass


class ThemeFollower:
    """Следит за переключателем персонажей и файлами тем и зовёт apply(name),
    когда тема этого приложения должна смениться. wanted() — какая тема нужна
    (с учётом выбора приложения), current() — какая сейчас в окне."""

    def __init__(self, wanted: Callable[[], str], registry: ThemeRegistry,
                 apply: Callable[[str], object], current: Callable[[], str]):
        from PyQt6.QtCore import QFileSystemWatcher, QTimer
        self.wanted, self.registry, self.apply, self.current = wanted, registry, apply, current
        folder = config_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "themes").mkdir(exist_ok=True)
        paths = [str(folder), str(folder / "themes")]
        if CHARACTERS.user_dir.is_dir():
            paths.append(str(CHARACTERS.user_dir))   # клик по персонажу → state.json
        self.watcher = QFileSystemWatcher(paths)
        self.debounce = QTimer(singleShot=True, interval=250)
        self.debounce.timeout.connect(self._check)
        self.watcher.directoryChanged.connect(lambda _p: self.debounce.start())
        self.watcher.fileChanged.connect(lambda _p: self.debounce.start())
        self._watch_files()

    def _watch_files(self) -> None:
        """Слежка за папкой видит только новые/удалённые файлы, а переключатель
        персонажей перезаписывает state.json на месте — за ним следим отдельно.
        После атомарной замены файла Qt его «теряет», поэтому зовётся повторно."""
        watched = set(self.watcher.files())
        for f in (CHARACTERS.user_dir / "state.json", CHARACTERS.user_dir / "characters.json"):
            if f.is_file() and str(f) not in watched:
                self.watcher.addPath(str(f))

    def _check(self) -> None:
        self._watch_files()
        before = list(self.registry.palettes)
        self.registry.reload()
        if list(self.registry.palettes) != before:   # в редакторе добавили/удалили/переименовали тему
            for fn in list(_list_listeners):
                try:
                    fn()
                except Exception as e:  # noqa: BLE001 — слот Qt
                    print(f"[equestria_kit] themes list listener: {e}")
        name = self.wanted()
        if name != self.current():
            self.apply(name)


# ── простой интерфейс для приложений ──────────────────────────────────────
CHARACTERS = CharacterThemes()
_registry = ThemeRegistry()
_system = SystemTheme(CHARACTERS)
_app_choice = AppThemeChoice()
_followers: list = []

THEMES: dict = _registry.palettes


def registry() -> ThemeRegistry:
    return _registry


def system_name() -> str:
    """Тема «Как в системе» (персонаж из переключателя)."""
    return _registry.resolve(_system.name())


def choice() -> str:
    """Выбор этого приложения: SYSTEM или имя темы."""
    return _app_choice.load()


def current_name() -> str:
    """Тема этого приложения: своя, если выбрана и существует, иначе «Как в системе»."""
    own = choice()
    return own if own != SYSTEM and own in _registry.palettes else system_name()


def remember(name: str) -> None:
    """Запомнить выбор только для этого приложения (SYSTEM — «Как в системе»)."""
    _app_choice.save(name if name == SYSTEM else _registry.resolve(name))


_list_listeners: list = []


def on_list_change(fn: Callable[[], object]) -> None:
    """Подписка «список тем изменился» — для списков тем, заполняемых заранее
    (выпадающие меню, открываемые по клику, перечитывают THEMES сами)."""
    _list_listeners.append(fn)


def follow(apply: Callable[[str], object], current: Callable[[], str]) -> None:
    """Подписать окно на смену темы из других приложений (нужен QApplication)."""
    _followers.append(ThemeFollower(current_name, _registry, apply, current))
