# -*- coding: utf-8 -*-
"""
Общие Qt-кирпичики приложений Equestria OS, чтобы не копировать их в каждый файл:
  • render_qss   — QSS-шаблон с ролями темы: @accent@, @accent/40@, @yellow%10@ …;
  • ThemeManager — подключить приложение к общей теме одной строкой (и следить за сменой);
  • theme_color  — цвет роли для того, что рисуется кодом (QPainter);
  • ThemeApplier — применить тему: QSS-шаблон с @цвет@ + QPalette + запомнить выбор;
  • check_png    — галочка для QCheckBox в цвет темы (QSS сам её не рисует);
  • theme_menu   — выпадающее меню выбора темы;
  • JsonConfig   — настройки приложения в ~/.config/<app>/settings.json.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QAction, QColor, QPainter, QPalette, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from . import themes as kit_themes


_TOKEN = re.compile(r"@([a-z_0-9]+)(?:([/%])(\d{1,3}))?@")


def derived_colors(theme: dict) -> dict:
    """Производные роли, которых нет в файле темы, но которые нужны дизайну."""
    acc, text, base = QColor(theme["accent"]), QColor(theme["text"]), QColor(theme["base"])
    def on(color: str) -> str:   # читаемый текст поверх заливки: белый или тёмный — что контрастнее
        return "#ffffff" if contrast("#ffffff", color) >= contrast(theme["crust"], color) else theme["crust"]
    on_accent = on(theme["accent"])
    return {
        "on_red": on(theme["red"]), "on_green": on(theme["green"]), "on_yellow": on(theme["yellow"]),
        "on_accent2": on(_mix(theme["accent"], theme["text"], .40) if "accent2" not in theme else theme["accent2"]),
        "accent_hover": acc.lighter(112).name(),
        "accent2": _mix(theme["accent"], theme["text"], .40),   # второй акцент: заголовки, ссылки
        "on_accent": on_accent,                                  # текст на залитой акцентом кнопке
        "white": "#ffffff", "black": "#000000",
        "shadow": QColor(0, 0, 0).name() if base.lightnessF() < .5 else theme["surface2"],
    }


def _mix(a: str, b: str, k: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * k),
                  round(ca.green() + (cb.green() - ca.green()) * k),
                  round(ca.blue() + (cb.blue() - ca.blue()) * k)).name()


_SVG_TOKEN = re.compile(r"@svg:([^@]+?\.svg)@")
_ICON_TOKEN = re.compile(r"@icon:([a-z_]+)@")
ICONS_DIR = Path(__file__).resolve().parent / "icons"


def themed_svg(path: str, theme: dict) -> str:
    """SVG-шаблон с ролями внутри (fill="@accent@") → готовый файл в цветах темы
    (кэш ~/.cache/equestria-kit/svg). Возвращает путь к нему."""
    import hashlib
    try:
        src = Path(path).read_text(encoding="utf-8")
    except OSError:
        return path
    out = render_qss(src, theme)
    d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "equestria-kit" / "svg"
    d.mkdir(parents=True, exist_ok=True)
    f = d / (hashlib.sha1(out.encode()).hexdigest()[:16] + "-" + Path(path).name)
    if not f.exists():
        f.write_text(out, encoding="utf-8")
    return f.as_posix()


def render_qss(template: str, theme: dict) -> str:
    """@роль@ → цвет; @роль/NN@ → тот же цвет с прозрачностью NN (0–255);
    @роль%NN@ → NN процентов этого цвета поверх фона (тонированные плашки);
    @svg:/путь/иконка.svg@ → путь к копии SVG, окрашенной в цвета темы."""
    if "@svg:" in template:
        template = _SVG_TOKEN.sub(lambda m: themed_svg(m.group(1), theme), template)
    if "@icon:" in template:   # общие иконки библиотеки: флажки, стрелки, галочка
        template = _ICON_TOKEN.sub(lambda m: themed_svg(str(ICONS_DIR / f"{m.group(1)}.svg"), theme), template)
    colors = dict(theme)
    colors.update({k: v for k, v in derived_colors(theme).items() if k not in colors})
    readable_cache: dict = {}

    def sub(m):
        key, op, num = m.group(1), m.group(2), m.group(3)
        if key not in colors:
            return m.group(0)
        val = colors[key]
        if not op and key in _TEXT_SAFE_ROLES and _is_text_property(m.string, m.start()):
            # цвет роли как ТЕКСТ — гарантируем читаемость на карточках темы
            if key not in readable_cache:
                own = colors.get(f"{key}_text")   # цвет роли «для текста» из палитры персонажа
                readable_cache[key] = readable(own or val, colors["surface1"])
            return readable_cache[key]
        if not op or not val.startswith("#"):
            return val
        if op == "/":
            c = QColor(val)
            return f"rgba({c.red()}, {c.green()}, {c.blue()}, {min(255, int(num))})"
        return _mix(colors["base"], val, min(100, int(num)) / 100)
    return _TOKEN.sub(sub, template)


_TEXT_SAFE_ROLES = ("accent", "accent2", "accent_hover", "red", "green", "yellow", "subtext")
_PROP_RX = re.compile(r"([a-z-]+)\s*:\s*[^;:{}]*$")


def _is_text_property(text: str, pos: int) -> bool:
    m = _PROP_RX.search(text[max(0, pos - 80):pos])
    return bool(m) and m.group(1) in ("color", "selection-color")


def contrast(a: str, b: str) -> float:
    def lum(h):
        c = QColor(h)
        ch = [x / 255 for x in (c.red(), c.green(), c.blue())]
        ch = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable(color: str, background: str, target: float = 4.5) -> str:
    """Тот же оттенок, осветлённый (на тёмном фоне) до контраста ≥ target."""
    if contrast(color, background) >= target:
        return color
    c = QColor(color)
    h, s, l, _ = c.getHslF()
    dark_bg = QColor(background).lightnessF() < 0.5
    for _ in range(40):
        l = min(1.0, l + 0.025) if dark_bg else max(0.0, l - 0.025)
        cand = QColor.fromHslF(max(h, 0.0), s, l).name()
        if contrast(cand, background) >= target:
            return cand
    return cand


def theme_color(role: str, alpha: int = 255) -> QColor:
    """Цвет роли текущей темы — для paintEvent. Пример: theme_color("accent"),
    theme_color("red%25") (25% красного поверх фона), theme_color("accent/120")."""
    theme = _manager.theme if _manager else dict(kit_themes.THEMES[kit_themes.current_name()])
    c = QColor(render_qss(f"@{role}@", theme)) if ("%" in role) else None
    if c is None:
        key, _, a = role.partition("/")
        val = theme.get(key) or derived_colors(theme).get(key, "#ff00ff")
        c = QColor(val)
        if a:
            alpha = int(a)
    c.setAlpha(alpha)
    return c


def text_color(role: str) -> QColor:
    """Цвет роли для ТЕКСТА в paintEvent: тот же оттенок, но читаемый на карточках."""
    theme = _manager.theme if _manager else dict(kit_themes.THEMES[kit_themes.current_name()])
    surf = theme.get("surface1", "#45475a")
    own = theme.get(f"{role}_text")
    return QColor(readable(own or theme_color(role).name(), surf))


class ThemeManager:
    """Подключение «большого» приложения к общей теме:

        kit_qt.ThemeManager(app, open("style.qss").read())

    • рендерит QSS-шаблон с ролями темы и ставит его на всё приложение;
    • ставит QPalette темы (стандартные диалоги тоже в теме);
    • следит за переключателем тем персонажей и перекрашивает на лету,
      затем зовёт подписчиков on_change и перерисовывает окна."""

    def __init__(self, app: QApplication, qss_template: str = "", replacements: dict | None = None):
        global _manager
        self.app, self.template = app, qss_template
        self.replacements = replacements or {}
        self.name, self.theme = "", {}
        self.listeners: list = []
        _manager = self
        self.apply(kit_themes.current_name())
        kit_themes.follow(self.apply, lambda: self.name)

    def on_change(self, fn: Callable[[dict], object]) -> None:
        self.listeners.append(fn)

    def style(self, widget: QWidget, template: str) -> None:
        """Стиль виджета из шаблона с ролями; перерисуется при смене темы."""
        widget.setProperty(_TEMPLATE_PROP, template)
        widget.setStyleSheet(render_qss(template, self.theme))

    def apply(self, name: str) -> str:
        self.name = kit_themes.registry().resolve(name)
        self.theme = dict(kit_themes.THEMES[self.name])
        self.theme.update({k: v for k, v in derived_colors(self.theme).items() if k not in self.theme})
        qss = self.template
        for k, v in self.replacements.items():
            qss = qss.replace(k, v)
        pal = QPalette()
        for role, key in ThemeApplier.ROLES:
            pal.setColor(getattr(QPalette.ColorRole, role), QColor(self.theme[key]))
        self.app.setPalette(pal)
        self.app.setStyleSheet(render_qss(qss, self.theme))
        for fn in list(self.listeners):
            try:
                fn(self.theme)
            except Exception as e:  # noqa: BLE001 — слот Qt: исключение уронит PyQt6
                print(f"[equestria_kit] theme listener: {e}")
        for w in self.app.allWidgets():
            tpl = w.property(_TEMPLATE_PROP)
            if isinstance(tpl, str):
                w.setStyleSheet(render_qss(tpl, self.theme))
            w.update()
        return self.name


_manager: ThemeManager | None = None


def on_theme_change(fn: Callable[[dict], object]) -> None:
    """Подписка на смену темы — для того, что рисуется в коде (иконки, paintEvent).
    Работает, если в приложении есть ThemeManager; иначе ничего не делает."""
    if _manager is not None:
        _manager.on_change(fn)
_TEMPLATE_PROP = "_equestria_style_template"


def style(widget: QWidget, template: str) -> None:
    """kit_qt.style(btn, "background: @accent@; color: @on_accent@;") — вместо
    btn.setStyleSheet с зашитыми цветами. Работает и до создания ThemeManager
    (тогда берётся текущая общая тема)."""
    if _manager is not None:
        _manager.style(widget, template)
        return
    widget.setProperty(_TEMPLATE_PROP, template)
    theme = dict(kit_themes.THEMES[kit_themes.current_name()])
    widget.setStyleSheet(render_qss(template, theme))


def app_style(template: str) -> None:
    """Вместо app.setStyleSheet(...) с зашитыми цветами: шаблон всего приложения."""
    if _manager is not None:
        _manager.template = template
        _manager.apply(_manager.name)
    else:
        ThemeManager(QApplication.instance(), template)


def style_append(widget: QWidget, extra: str) -> None:
    """Дописать правила к стилю виджета (к шаблону, а не к уже окрашенному тексту)."""
    tpl = widget.property(_TEMPLATE_PROP)
    style(widget, (tpl if isinstance(tpl, str) else widget.styleSheet()) + extra)


def qss(template: str) -> str:
    """Отрендерить шаблон текущей темой (для мест, где нужен готовый текст QSS)."""
    theme = _manager.theme if _manager else dict(kit_themes.THEMES[kit_themes.current_name()])
    return render_qss(template, theme)


class ThemeApplier:
    """state — словарь THEME приложения (обновляется на месте, его читают виджеты).
    extras(state) → доп. ключи для QSS (картинки, производные цвета)."""

    ROLES = (("Window", "base"), ("WindowText", "text"), ("Base", "surface0"),
             ("AlternateBase", "mantle"), ("Text", "text"), ("Button", "surface0"),
             ("ButtonText", "text"), ("Highlight", "accent"), ("HighlightedText", "base"),
             ("ToolTipBase", "surface1"), ("ToolTipText", "text"),
             ("PlaceholderText", "subtext"), ("Link", "accent"))

    def __init__(self, qss: str, state: dict, extras: Callable[[dict], dict] | None = None):
        self.qss, self.state, self.extras = qss, state, extras

    def apply(self, name: str) -> str:
        name = kit_themes.registry().resolve(name)
        self.state.clear()
        self.state.update(kit_themes.THEMES[name])
        self.state["accent_hover"] = QColor(self.state["accent"]).lighter(112).name()
        if self.extras:
            self.state.update(self.extras(self.state))
        qss = render_qss(self.qss, self.state)   # те же правила читаемости, что и везде
        pal = QPalette()
        for role, key in self.ROLES:
            pal.setColor(getattr(QPalette.ColorRole, role), QColor(self.state[key]))
        app = QApplication.instance()
        app.setPalette(pal)
        app.setStyleSheet(qss)
        kit_themes.remember(name)
        return name


def cache_dir(app_id: str) -> Path:
    d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / app_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def check_png(color: str, app_id: str) -> str:
    """Галочка 14×14 цвета color, путь к PNG для QSS (image: url(...))."""
    path = cache_dir(app_id) / f"check-{color.lstrip('#')}.png"
    if not path.exists():
        pm = QPixmap(14, 14)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QPolygonF([QPointF(3, 7.5), QPointF(6, 10.5), QPointF(11, 3.5)]))
        p.end()
        pm.save(str(path))
    return path.as_posix()


def theme_menu(parent: QWidget, anchor: QWidget, current: str, on_pick: Callable[[str], object]) -> None:
    """Меню со всеми темами под кнопкой anchor; текущая отмечена точкой."""
    menu = QMenu(parent)
    for name in kit_themes.THEMES:
        act = QAction(("● " if name == current else "   ") + name, parent)
        act.triggered.connect(lambda _=False, n=name: on_pick(n))
        menu.addAction(act)
    menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))


class JsonConfig:
    """Словарь настроек, который сам читается/пишется в JSON."""

    def __init__(self, app_id: str, defaults: dict | None = None, filename: str = "settings.json"):
        self.path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / app_id / filename
        self.data: dict = dict(defaults or {})
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data.update(raw)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
