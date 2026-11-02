#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equestria Calc — многорежимный калькулятор в стиле Equestria Clock (PyQt6).

Режимы: Обычный, Инженерный, Программист, Конвертер, Даты.
Клавиатура: цифры, + - * / ^ ( ) % . , Enter или = — результат,
Backspace — стереть, Esc — очистить, Ctrl+C — копировать результат.
"""
from __future__ import annotations

import ast
import calendar
import datetime as dt
import json
import math
import operator
import os
import re
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QFontDatabase, QGuiApplication,
                         QKeySequence, QPalette)
from PyQt6.QtWidgets import (QApplication, QComboBox, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QPushButton, QSizePolicy,
                             QStackedWidget, QVBoxLayout, QWidget)

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit import themes as kit_themes
from equestria_kit import i18n as kit_i18n

tr = kit_i18n.install("equestria-calc", __file__)

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "equestria-calc" / "settings.json"

# ════════════════════════════════════════════════════════════════════════════
#  ТЕМЫ
# ════════════════════════════════════════════════════════════════════════════

# Темы общие для всех приложений Equestria OS: см. equestria_kit/themes.py.
# Свои темы — файлы ~/.config/equestria-os/themes/*.json.
KEYS = kit_themes.KEYS
THEMES = kit_themes.THEMES
DEFAULT_THEME = kit_themes.DEFAULT_THEME
THEME: dict = dict(THEMES[DEFAULT_THEME])

QSS = """
QMainWindow { background: @base@; }
QWidget { color: @text@; font-size: 18px; }
QLabel { background: transparent; }
QLabel#expr { color: @subtext@; font-size: 18px; }
QLabel#result { font-size: 44px; font-weight: 700; color: @accent@; }
QLabel#result[error="true"] { color: @red@; }
QLabel#hint { color: @subtext@; font-size: 15px; }
QLabel#h2 { color: @accent@; font-size: 15px; font-weight: 700; }
QLabel#out { font-size: 20px; font-weight: 600; }
QPushButton { background: @surface0@; border: none; border-radius: 12px; font-weight: 600; }
QPushButton:hover { background: @surface1@; }
QPushButton:pressed { background: @surface2@; }
QPushButton:disabled { color: @surface2@; background: @mantle@; }
QPushButton#num { background: @mantle@; }
QPushButton#num:hover { background: @surface0@; }
QPushButton#fn { background: @mantle@; color: @subtext@; font-size: 15px; }
QPushButton#fn:hover { background: @surface0@; }
QPushButton#op { color: @accent@; }
QPushButton#eq { background: @accent@; color: @base@; }
QPushButton#eq:hover { background: @accent_hover@; }
QPushButton#clr { color: @red@; }
QPushButton#small { padding: 6px 14px; font-size: 14px; border-radius: 10px; }
QPushButton#small:checked { background: @accent@; color: @base@; }
QPushButton#row { background: transparent; text-align: left; padding: 6px 12px;
    border-radius: 8px; font-size: 15px; }
QPushButton#row:hover { background: @surface0@; }
QPushButton#row:checked { background: @surface0@; color: @accent@; }
QLineEdit { background: @surface0@; border: 2px solid transparent; border-radius: 10px;
    padding: 8px 12px; font-size: 20px; selection-background-color: @accent@; selection-color: @base@; }
QLineEdit:focus { border-color: @accent@; }
QLineEdit[error="true"] { border-color: @red@; }
QListWidget { background: transparent; border: none; outline: 0; font-size: 15px; }
QListWidget::item { background: @surface0@; border-radius: 8px; padding: 8px 12px; margin: 3px 0; }
QListWidget::item:hover { background: @surface1@; }
QMenu { background: @mantle@; border: 1px solid @surface1@; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 6px; }
QMenu::item:selected { background: @surface1@; }
QToolTip { background: @surface1@; color: @text@; border: none; padding: 4px 8px; }
"""


_THEME_APPLIER = kit_qt.ThemeApplier(QSS, THEME)


def apply_theme(name: str) -> str:
    return _THEME_APPLIER.apply(name)


# ════════════════════════════════════════════════════════════════════════════
#  ВЫЧИСЛЕНИЯ (без eval: разбираем AST по белому списку)
# ════════════════════════════════════════════════════════════════════════════
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod}


def _fact(x):
    if x != int(x) or not 0 <= x <= 170:
        raise ValueError("fact")
    return math.factorial(int(x))


def funcs(deg: bool) -> dict:
    r = math.radians if deg else (lambda x: x)
    d = math.degrees if deg else (lambda x: x)

    def tan(x):
        if deg and (x - 90) % 180 == 0:
            raise ValueError("tan")
        return math.tan(r(x))

    return {
        "sin": lambda x: math.sin(r(x)), "cos": lambda x: math.cos(r(x)), "tan": tan,
        "asin": lambda x: d(math.asin(x)), "acos": lambda x: d(math.acos(x)),
        "atan": lambda x: d(math.atan(x)),
        "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
        "ln": math.log, "log": math.log10, "sqrt": math.sqrt,
        "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
        "abs": abs, "fact": _fact, "floor": math.floor, "ceil": math.ceil,
    }


def _ev(n, F):
    if isinstance(n, ast.Expression):
        return _ev(n.body, F)
    if isinstance(n, ast.Constant) and type(n.value) in (int, float):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in OPS:
        a, b = _ev(n.left, F), _ev(n.right, F)
        if isinstance(n.op, ast.Pow) and abs(b) > 1000:
            raise ValueError("pow")
        return OPS[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
        v = _ev(n.operand, F)
        return -v if isinstance(n.op, ast.USub) else v
    if isinstance(n, ast.Name) and n.id in ("pi", "e"):
        return math.pi if n.id == "pi" else math.e
    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in F
            and len(n.args) == 1 and not n.keywords):
        return F[n.func.id](_ev(n.args[0], F))
    raise ValueError("bad expression")


def evaluate(expr: str, deg: bool = True):
    s = expr.replace("mod", "\x00").replace("%", "/100").replace("\x00", "%")
    s = (s.replace("×", "*").replace("÷", "/").replace("−", "-")
         .replace("π", "pi").replace("√", "sqrt").replace("^", "**").replace(",", "."))
    return _ev(ast.parse(s.strip(), mode="eval"), funcs(deg))


def fmt(v) -> str:
    if isinstance(v, complex) or v != v or v in (math.inf, -math.inf):
        raise ValueError("bad result")
    if abs(v) < 1e-14:
        return "0"
    if float(v).is_integer() and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.12g}"


# --- программистский режим (целые числа заданной разрядности)
BITS = {"QWORD": 64, "DWORD": 32, "WORD": 16, "BYTE": 8}


def wrap(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _tdiv(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def _shift(f):
    def g(a, b):
        if not 0 <= b <= 1024:
            raise ValueError("shift")
        return f(a, b)
    return g


POPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: _tdiv, ast.Mod: lambda a, b: a - _tdiv(a, b) * b,
        ast.BitAnd: operator.and_, ast.BitOr: operator.or_, ast.BitXor: operator.xor,
        ast.LShift: _shift(operator.lshift), ast.RShift: _shift(operator.rshift)}


def _pev(n, bits):
    if isinstance(n, ast.Constant) and type(n.value) is int:
        return wrap(n.value, bits)
    if isinstance(n, ast.BinOp) and type(n.op) in POPS:
        return wrap(POPS[type(n.op)](_pev(n.left, bits), _pev(n.right, bits)), bits)
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd, ast.Invert)):
        v = _pev(n.operand, bits)
        return wrap(-v if isinstance(n.op, ast.USub) else ~v if isinstance(n.op, ast.Invert) else v, bits)
    raise ValueError("bad expression")


def prog_eval(expr: str, base: int, bits: int) -> int:
    s = expr.replace("×", "*").replace("÷", "/").replace("−", "-")
    s = re.sub(r"[0-9A-F]+", lambda m: str(int(m.group(), base)), s)
    return wrap(_pev(ast.parse(s.strip(), mode="eval").body, bits), bits)


def fmt_base(v: int, base: int, bits: int) -> str:
    if base == 10:
        return str(v)
    u = v & ((1 << bits) - 1)
    return {16: f"{u:X}", 8: f"{u:o}", 2: f"{u:b}"}[base]


def group(s: str, n: int = 4) -> str:
    parts = []
    while s:
        parts.append(s[-n:])
        s = s[:-n]
    return " ".join(reversed(parts))


# --- конвертер
CATS = {
    tr("Длина"): ([(tr("мм"), 1e-3), (tr("см"), 1e-2), (tr("м"), 1), (tr("км"), 1e3), (tr("дюйм"), 0.0254),
               (tr("фут"), 0.3048), (tr("ярд"), 0.9144), (tr("миля"), 1609.344), (tr("морская миля"), 1852)], 2, 3),
    tr("Масса"): ([(tr("мг"), 1e-6), (tr("г"), 1e-3), (tr("кг"), 1), (tr("т"), 1e3), (tr("унция"), 0.028349523125),
               (tr("фунт"), 0.45359237), (tr("стоун"), 6.35029318)], 2, 5),
    tr("Температура"): ([("°C", 0), ("°F", 0), ("K", 0)], 0, 1),
    tr("Площадь"): ([(tr("мм²"), 1e-6), (tr("см²"), 1e-4), (tr("м²"), 1), (tr("га"), 1e4), (tr("км²"), 1e6),
                 (tr("фут²"), 0.09290304), (tr("акр"), 4046.8564224)], 2, 3),
    tr("Объём"): ([(tr("мл"), 1e-3), (tr("л"), 1), (tr("м³"), 1e3), (tr("галлон (США)"), 3.785411784),
               (tr("пинта (США)"), 0.473176473), (tr("чашка (США)"), 0.2365882365),
               (tr("жидкая унция"), 0.0295735295625)], 1, 3),
    tr("Скорость"): ([(tr("м/с"), 1), (tr("км/ч"), 1 / 3.6), (tr("миля/ч"), 0.44704), (tr("узел"), 1852 / 3600),
                  (tr("фут/с"), 0.3048)], 1, 2),
    tr("Время"): ([(tr("мс"), 1e-3), (tr("с"), 1), (tr("мин"), 60), (tr("ч"), 3600), (tr("сут"), 86400),
               (tr("нед"), 604800), (tr("год"), 31557600)], 2, 3),
    tr("Данные"): ([(tr("бит"), 0.125), (tr("байт"), 1), (tr("КБ"), 1e3), (tr("МБ"), 1e6), (tr("ГБ"), 1e9), (tr("ТБ"), 1e12),
                (tr("КиБ"), 1024), (tr("МиБ"), 1024 ** 2), (tr("ГиБ"), 1024 ** 3)], 3, 4),
}


def convert(cat: str, v: float, a: str, b: str) -> float:
    if cat == tr("Температура"):
        c = {"°C": v, "°F": (v - 32) * 5 / 9, "K": v - 273.15}[a]
        return {"°C": c, "°F": c * 9 / 5 + 32, "K": c + 273.15}[b]
    u = dict(CATS[cat][0])
    return v * u[a] / u[b]


# --- даты
WEEKDAYS = [tr("понедельник"), tr("вторник"), tr("среда"), tr("четверг"), tr("пятница"), tr("суббота"), tr("воскресенье")]


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s.strip(), "%d.%m.%Y").date()


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return dt.date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def date_diff(a: dt.date, b: dt.date):
    if a > b:
        a, b = b, a
    total = (b.year - a.year) * 12 + b.month - a.month
    if add_months(a, total) > b:
        total -= 1
    rest = (b - add_months(a, total)).days
    y, m = divmod(total, 12)
    return (b - a).days, y, m, rest


# ════════════════════════════════════════════════════════════════════════════
#  МЕЛОЧИ UI
# ════════════════════════════════════════════════════════════════════════════
def mk(text, name="", cb=None, expand=True, h=44) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if name:
        b.setObjectName(name)
    if expand:
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        b.setMinimumHeight(h)
    if cb:
        b.clicked.connect(lambda _=False, t=text: cb(t))
    return b


def fit(label: QLabel, text: str, error: bool = False, px: int = 44) -> None:
    n = len(text)
    size = px if n <= 11 else int(px * .7) if n <= 16 else int(px * .5) if n <= 26 else int(px * .36)
    label.setProperty("error", error)
    label.setStyleSheet(f"font-size: {size}px;")
    label.style().unpolish(label)
    label.style().polish(label)
    label.setText(text)


def right_label(name: str, minh: int) -> QLabel:
    lab = QLabel("")
    lab.setObjectName(name)
    lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lab.setMinimumHeight(minh)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return lab


def single_group(e: str) -> bool:
    """Строка вида −( … ) — одна скобочная группа целиком."""
    if not (e.startswith("−(") and e.endswith(")")):
        return False
    depth = 0
    for i, ch in enumerate(e[1:], 1):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0 and i != len(e) - 1:
            return False
    return depth == 0


def toggle_neg(e: str, num: str) -> str:
    if single_group(e):
        return e[2:-1]
    if re.fullmatch(num, e):
        return "−" + e
    if re.fullmatch("−" + num, e):
        return e[1:]
    return f"−({e})"


class HistoryPanel(QWidget):
    picked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.list = QListWidget()
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(lambda it: self.picked.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.empty = QLabel(tr("История пуста"))
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clear_btn = mk(tr("Очистить историю"), "small", expand=False)
        self.clear_btn.clicked.connect(self.clear)
        v.addWidget(self.list, 1)
        v.addWidget(self.empty, 1)
        v.addWidget(self.clear_btn)
        self._sync()

    def add(self, text: str, result: str) -> None:
        it = QListWidgetItem(text)
        it.setData(Qt.ItemDataRole.UserRole, result)
        self.list.insertItem(0, it)
        self._sync()

    def clear(self) -> None:
        self.list.clear()
        self._sync()

    def _sync(self) -> None:
        has = self.list.count() > 0
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        self.clear_btn.setEnabled(has)


class PageBase(QWidget):
    """Общее для экранов: текст результата для Ctrl+C и обработка клавиш."""
    pref = (420, 700)
    minimum = (360, 600)

    def copy_text(self) -> str | None:
        return None

    def key(self, e) -> bool:
        return False


# ════════════════════════════════════════════════════════════════════════════
#  ОБЫЧНЫЙ / ИНЖЕНЕРНЫЙ
# ════════════════════════════════════════════════════════════════════════════
PLUS_OPS = ("+", "−", "×", "÷", "^", " mod ")
SCI_ROWS = [["sin", "cos", "tan", "n!"],
            ["asin", "acos", "atan", "|x|"],
            ["sinh", "cosh", "tanh", "xʸ"],
            ["ln", "log", "10ˣ", "eˣ"],
            ["∛", "x³", "floor", "ceil"],
            ["π", "e", "mod", "Deg"]]
STD_ROWS = [["(", ")", "%", "⌫"],
            ["C", "1/x", "x²", "√"],
            ["7", "8", "9", "÷"],
            ["4", "5", "6", "×"],
            ["1", "2", "3", "−"],
            ["±", "0", ".", "+"]]
EXPR_TXT = {"sin": "sin(", "cos": "cos(", "tan": "tan(", "asin": "asin(", "acos": "acos(",
            "atan": "atan(", "sinh": "sinh(", "cosh": "cosh(", "tanh": "tanh(",
            "ln": "ln(", "log": "log(", "n!": "fact(", "|x|": "abs(", "10ˣ": "10^(",
            "eˣ": "e^(", "∛": "cbrt(", "floor": "floor(", "ceil": "ceil(", "√": "√(",
            "mod": " mod ", "xʸ": "^"}


class ExprPage(PageBase):
    def __init__(self, sci: bool):
        super().__init__()
        self.sci = sci
        self.pref = (860, 700) if sci else (420, 700)
        self.minimum = (780, 620) if sci else (360, 600)
        self.deg = True
        self.expr = ""
        self.prev = ""
        self.fresh = False

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        top = QHBoxLayout()
        self.hist_btn = mk(tr("История"), "small", expand=False)
        self.hist_btn.setCheckable(True)
        self.hist_btn.toggled.connect(self._toggle_history)
        top.addWidget(self.hist_btn)
        top.addStretch()
        v.addLayout(top)
        self.expr_label = right_label("expr", 26)
        self.result_label = right_label("result", 62)
        v.addWidget(self.expr_label)
        v.addWidget(self.result_label)

        self.hist = HistoryPanel()
        self.hist.setVisible(False)
        self.hist.picked.connect(self._pick)
        v.addWidget(self.hist, 1)

        self.body = QWidget()
        g = QGridLayout(self.body)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(8)
        off = 0
        if sci:
            for r, row in enumerate(SCI_ROWS):
                for c, lab in enumerate(row):
                    b = mk(lab, "num" if lab in ("π", "e") else "fn", self.press)
                    if lab == "Deg":
                        self.deg_btn = b
                    g.addWidget(b, r, c)
            off = 4
        for r, row in enumerate(STD_ROWS):
            for c, lab in enumerate(row):
                name = ("clr" if lab == "C" else "num" if lab.isdigit() or lab in ".±"
                        else "op")
                g.addWidget(mk(lab, name, self.press), r, off + c)
        g.addWidget(mk("=", "eq", self.press), len(STD_ROWS), 0, 1, off + 4)
        v.addWidget(self.body, 4)
        self._refresh()

    # --- ввод
    def press(self, t: str) -> None:
        if t == "Deg" or t == "Rad":
            self.deg = not self.deg
            self.deg_btn.setText("Deg" if self.deg else "Rad")
        elif t == "C":
            self.expr, self.prev, self.fresh = "", "", False
        elif t == "⌫":
            self.expr = re.sub(r"(?:[a-z]+\(|√\(| mod |.)$", "", self.expr)
            self.fresh = False
        elif t == "=":
            self._equals()
            return
        elif t in ("±", "x²", "x³", "1/x"):
            e = self.expr
            if e and not e.endswith(PLUS_OPS) and not e.endswith("("):
                self.expr = {"±": lambda: toggle_neg(e, r"[0-9.]+"),
                             "x²": lambda: f"({e})^2", "x³": lambda: f"({e})^3",
                             "1/x": lambda: f"1÷({e})"}[t]()
                self.fresh = False
        else:
            self._insert(EXPR_TXT.get(t, t))
        self._refresh()

    def _insert(self, tok: str) -> None:
        e = self.expr
        kind = ("digit" if tok.isdigit() or tok == "." else
                "val" if tok in ("π", "e") or tok.endswith("(") else "op")
        if self.fresh and kind != "op":
            e = ""
        last = e[-1:]
        closing = bool(last) and last in ")πe"
        if kind == "digit":
            if tok == ".":
                seg = re.search(r"[0-9.]*$", e).group()
                if "." in seg:
                    return
                if not seg:
                    tok = ("×" if closing else "") + "0."
            elif closing:
                tok = "×" + tok
        elif kind == "val":
            if last and (last.isdigit() or closing or last == "."):
                tok = "×" + tok
        elif tok == ")":
            if e.count("(") <= e.count(")") or last == "(" or e.endswith(PLUS_OPS):
                return
        elif tok == "%":
            if not (last.isdigit() or last == ")"):
                return
        else:  # бинарный оператор
            neg_ok = tok == "−" and e.endswith(PLUS_OPS) and (last in "×÷^" or e.endswith(" mod "))
            if not neg_ok:
                while e.endswith(PLUS_OPS):
                    e = next(e[:-len(o)] for o in PLUS_OPS if e.endswith(o))
                if (not e and tok != "−") or (e.endswith("(") and tok != "−"):
                    return
        self.expr, self.fresh = e + tok, False

    def _balanced(self, e: str) -> str:
        return e + ")" * (e.count("(") - e.count(")"))

    def _probe(self) -> str:
        """Выражение без висящих операторов и с закрытыми скобками."""
        e = self.expr
        while e.endswith(PLUS_OPS):
            e = next(e[:-len(o)] for o in PLUS_OPS if e.endswith(o))
        return self._balanced(e)

    def _equals(self) -> None:
        if not self.expr or self.fresh:
            return
        try:
            res = fmt(evaluate(self._probe(), self.deg))
        except Exception:
            fit(self.result_label, tr("Ошибка"), True)
            return
        self.hist.add(f"{self.expr}  =  {res}", res)
        self.prev, self.expr, self.fresh = self.expr, res, True
        self._refresh()

    def _refresh(self) -> None:
        e = self.expr
        self.expr_label.setText(f"{self.prev} =" if self.fresh else e)
        if not e:
            fit(self.result_label, "0")
            return
        try:
            fit(self.result_label, fmt(evaluate(self._probe(), self.deg)))
        except Exception:
            m = re.search(r"[0-9.]+$", e)
            fit(self.result_label, m.group() if m else "0")

    # --- история
    def _toggle_history(self, on: bool) -> None:
        self.hist.setVisible(on)
        self.body.setVisible(not on)

    def _pick(self, res: str) -> None:
        self.expr, self.fresh, self.prev = res, True, ""
        self.hist_btn.setChecked(False)
        self._refresh()

    def copy_text(self):
        return self.result_label.text()

    def key(self, e) -> bool:
        k, txt = e.key(), e.text()
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or txt == "=":
            self.press("=")
        elif k == Qt.Key.Key_Backspace:
            self.press("⌫")
        elif k == Qt.Key.Key_Escape:
            self.press("C")
        elif txt and txt in "0123456789().+-*/%^,":
            self.press({"*": "×", "/": "÷", "-": "−", ",": ".", "^": "xʸ"}.get(txt, txt))
        else:
            return False
        return True


# ════════════════════════════════════════════════════════════════════════════
#  ПРОГРАММИСТ
# ════════════════════════════════════════════════════════════════════════════
PROG_ROWS = [["A", "<<", ">>", "(", ")", "⌫"],
             ["B", "AND", "7", "8", "9", "÷"],
             ["C", "OR", "4", "5", "6", "×"],
             ["D", "XOR", "1", "2", "3", "−"],
             ["E", "NOT", "±", "0", "mod", "+"],
             ["F", "CE"]]
PROG_TXT = {"AND": "&", "OR": "|", "XOR": "^", "NOT": "~", "mod": "%"}
DIGITS = "0123456789ABCDEF"


class ProgPage(PageBase):
    pref = (640, 780)
    minimum = (560, 680)

    def __init__(self):
        super().__init__()
        self.base, self.bits = 10, 64
        self.expr, self.prev, self.fresh, self.last = "", "", False, 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        top = QHBoxLayout()
        self.hist_btn = mk(tr("История"), "small", expand=False)
        self.hist_btn.setCheckable(True)
        self.hist_btn.toggled.connect(self._toggle_history)
        self.word = QComboBox()
        self.word.addItems(list(BITS))
        self.word.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.word.currentTextChanged.connect(self._word_changed)
        top.addWidget(self.hist_btn)
        top.addStretch()
        top.addWidget(self.word)
        v.addLayout(top)
        self.expr_label = right_label("expr", 26)
        self.result_label = right_label("result", 56)
        v.addWidget(self.expr_label)
        v.addWidget(self.result_label)

        self.rows = {}
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        for name, base in (("HEX", 16), ("DEC", 10), ("OCT", 8), ("BIN", 2)):
            b = mk(name, "row", expand=False)
            b.setCheckable(True)
            b.setFont(mono)
            b.clicked.connect(lambda _=False, bs=base: self.set_base(bs))
            self.rows[base] = b
            v.addWidget(b)

        self.hist = HistoryPanel()
        self.hist.setVisible(False)
        self.hist.picked.connect(self._pick)
        v.addWidget(self.hist, 1)

        self.body = QWidget()
        g = QGridLayout(self.body)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(8)
        self.keys = {}
        for r, row in enumerate(PROG_ROWS):
            for c, lab in enumerate(row):
                name = ("clr" if lab == "CE" else "num" if lab in DIGITS or lab == "±"
                        else "op")
                b = mk(lab, name, self.press)
                self.keys[lab] = b
                g.addWidget(b, r, c)
        g.addWidget(mk("=", "eq", self.press), len(PROG_ROWS) - 1, 2, 1, 4)
        v.addWidget(self.body, 4)
        self._base_changed()
        self._refresh()

    def press(self, t: str) -> None:
        if t == "CE":
            self.expr, self.prev, self.fresh = "", "", False
        elif t == "⌫":
            self.expr = re.sub(r"(?:<<|>>|.)$", "", self.expr)
            self.fresh = False
        elif t == "=":
            self._equals()
            return
        elif t == "±":
            if self.expr and not re.search(r"[-+×÷−*/%&|^~(]$|<<$|>>$", self.expr):
                self.expr = toggle_neg(self.expr, r"[0-9A-F]+")
                self.fresh = False
        else:
            tok = PROG_TXT.get(t, t)
            if self.fresh and tok in DIGITS:
                self.expr = ""
            self.expr += tok
            self.fresh = False
        self._refresh()

    def _balanced(self) -> str:
        e = re.sub(r"(?:[-+×÷−*/%&|^]|<<|>>)+$", "", self.expr)  # висящие операторы
        return e + ")" * (e.count("(") - e.count(")"))

    def _equals(self) -> None:
        if not self.expr or self.fresh:
            return
        try:
            v = prog_eval(self._balanced(), self.base, self.bits)
        except Exception:
            fit(self.result_label, tr("Ошибка"), True, 38)
            return
        res = fmt_base(v, self.base, self.bits)
        self.hist.add(f"{self.expr}  =  {res}  (base {self.base})", res)
        self.prev, self.expr, self.fresh, self.last = self.expr, res, True, v
        self._refresh()

    def _refresh(self) -> None:
        self.expr_label.setText(f"{self.prev} =" if self.fresh else self.expr)
        valid = True
        if not self.expr:
            v = 0
        else:
            try:
                v = prog_eval(self._balanced(), self.base, self.bits)
            except Exception:
                valid, v = False, self.last
        self.last = v
        text = fmt_base(v, self.base, self.bits) if valid else (self.expr[-20:] or "0")
        fit(self.result_label, group(text) if (valid and self.base in (2, 16, 8)) else text, False, 38)
        for base, b in self.rows.items():
            s = fmt_base(v, base, self.bits)
            s = f"{v:,}".replace(",", " ") if base == 10 else group(s)
            b.setText(f"{ {16: 'HEX', 10: 'DEC', 8: 'OCT', 2: 'BIN'}[base] }   {s}")
            b.setChecked(base == self.base)

    def set_base(self, base: int) -> None:
        if base != self.base:
            try:
                v = prog_eval(self._balanced(), self.base, self.bits) if self.expr else 0
            except Exception:
                v = self.last
            had = bool(self.expr)
            self.base = base
            self.expr = fmt_base(v, base, self.bits) if had else ""
            self.fresh, self.prev = had, ""
            self._base_changed()
        self._refresh()

    def _base_changed(self) -> None:
        for i, d in enumerate(DIGITS):
            self.keys[d].setEnabled(i < self.base)

    def _word_changed(self, name: str) -> None:
        self.bits = BITS[name]
        self._refresh()

    def _toggle_history(self, on: bool) -> None:
        self.hist.setVisible(on)
        self.body.setVisible(not on)

    def _pick(self, res: str) -> None:
        self.expr, self.fresh, self.prev = res, True, ""
        self.hist_btn.setChecked(False)
        self._refresh()

    def copy_text(self):
        return self.result_label.text().replace(" ", "")

    def key(self, e) -> bool:
        k, txt = e.key(), e.text().upper()
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or txt == "=":
            self.press("=")
        elif k == Qt.Key.Key_Backspace:
            self.press("⌫")
        elif k == Qt.Key.Key_Escape:
            self.press("CE")
        elif txt and txt in DIGITS and DIGITS.index(txt) < self.base:
            self.press(txt)
        elif txt and txt in "+-*/%&|^~()":
            self.press({"*": "×", "/": "÷", "-": "−"}.get(txt, txt))
        elif txt in ("<", ">"):
            self.press(txt * 2)
        else:
            return False
        return True


# ════════════════════════════════════════════════════════════════════════════
#  КОНВЕРТЕР
# ════════════════════════════════════════════════════════════════════════════
class ConverterPage(PageBase):
    pref = (480, 560)
    minimum = (420, 480)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)
        self.cat = QComboBox()
        self.cat.addItems(list(CATS))
        self.inp = QLineEdit("1")
        self.frm, self.to = QComboBox(), QComboBox()
        swap = mk(tr("⇅  Поменять местами"), "small", expand=False)
        swap.clicked.connect(self._swap)
        self.out = QLineEdit()
        self.out.setReadOnly(True)
        for w in (self.cat, self.frm, self.to):
            w.setMinimumHeight(40)
        v.addWidget(self._cap(tr("Величина")))
        v.addWidget(self.cat)
        v.addWidget(self._cap(tr("Из")))
        v.addWidget(self.inp)
        v.addWidget(self.frm)
        v.addWidget(swap)
        v.addWidget(self._cap(tr("В")))
        v.addWidget(self.out)
        v.addWidget(self.to)
        v.addStretch()
        self.cat.currentIndexChanged.connect(self._fill)
        self.inp.textChanged.connect(self._update)
        self.frm.currentIndexChanged.connect(self._update)
        self.to.currentIndexChanged.connect(self._update)
        self._fill()

    @staticmethod
    def _cap(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("h2")
        return lab

    def _fill(self) -> None:
        units, i, j = CATS[self.cat.currentText()]
        for box, idx in ((self.frm, i), (self.to, j)):
            box.blockSignals(True)
            box.clear()
            box.addItems([u for u, _ in units])
            box.setCurrentIndex(idx)
            box.blockSignals(False)
        self._update()

    def _swap(self) -> None:
        i, j = self.frm.currentIndex(), self.to.currentIndex()
        self.frm.blockSignals(True)
        self.to.blockSignals(True)
        self.frm.setCurrentIndex(j)
        self.to.setCurrentIndex(i)
        self.frm.blockSignals(False)
        self.to.blockSignals(False)
        self._update()

    def _update(self) -> None:
        bad = False
        try:
            x = float(self.inp.text().replace(",", ".").replace(" ", ""))
            self.out.setText(fmt(convert(self.cat.currentText(), x,
                                         self.frm.currentText(), self.to.currentText())))
        except Exception:
            bad = bool(self.inp.text().strip())
            self.out.setText("")
        self.inp.setProperty("error", bad)
        self.inp.style().unpolish(self.inp)
        self.inp.style().polish(self.inp)

    def copy_text(self):
        return None  # у полей свой Ctrl+C


# ════════════════════════════════════════════════════════════════════════════
#  ДАТЫ
# ════════════════════════════════════════════════════════════════════════════
class DatePage(PageBase):
    pref = (480, 600)
    minimum = (420, 520)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)
        today = dt.date.today().strftime("%d.%m.%Y")
        self.d1, self.d2, self.days = QLineEdit(today), QLineEdit(today), QLineEdit("30")
        for e in (self.d1, self.d2):
            e.setPlaceholderText(tr("дд.мм.гггг"))
        self.days.setPlaceholderText(tr("число дней, можно отрицательное"))
        self.res_diff, self.res_add = QLabel(""), QLabel("")
        for lab in (self.res_diff, self.res_add):
            lab.setObjectName("out")
            lab.setWordWrap(True)
        t1 = mk(tr("Сегодня"), "small", expand=False)
        t1.clicked.connect(lambda: self.d1.setText(dt.date.today().strftime("%d.%m.%Y")))
        t2 = mk(tr("Сегодня"), "small", expand=False)
        t2.clicked.connect(lambda: self.d2.setText(dt.date.today().strftime("%d.%m.%Y")))
        v.addWidget(self._cap(tr("Первая дата")))
        r1 = QHBoxLayout()
        r1.addWidget(self.d1, 1)
        r1.addWidget(t1)
        v.addLayout(r1)
        v.addWidget(self._cap(tr("Вторая дата")))
        r2 = QHBoxLayout()
        r2.addWidget(self.d2, 1)
        r2.addWidget(t2)
        v.addLayout(r2)
        v.addWidget(self._cap(tr("Разница")))
        v.addWidget(self.res_diff)
        v.addWidget(self._cap(tr("Первая дата ± дни")))
        v.addWidget(self.days)
        v.addWidget(self.res_add)
        v.addStretch()
        for e in (self.d1, self.d2, self.days):
            e.textChanged.connect(self._update)
        self._update()

    @staticmethod
    def _cap(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("h2")
        return lab

    @staticmethod
    def _flag(edit: QLineEdit, bad: bool) -> None:
        edit.setProperty("error", bad)
        edit.style().unpolish(edit)
        edit.style().polish(edit)

    def _update(self) -> None:
        a = b = None
        for edit, name in ((self.d1, "a"), (self.d2, "b")):
            try:
                d = parse_date(edit.text())
                self._flag(edit, False)
            except ValueError:
                d = None
                self._flag(edit, bool(edit.text().strip()))
            if name == "a":
                a = d
            else:
                b = d
        if a and b:
            n, y, m, r = date_diff(a, b)
            w, wd = divmod(n, 7)
            self.res_diff.setText(tr("{} дн.\n{} нед. {} дн.\n{} г. {} мес. {} дн.", n, w, wd, y, m, r))
        else:
            self.res_diff.setText(tr("Введите обе даты в формате дд.мм.гггг"))
        try:
            k = int(self.days.text().strip())
            self._flag(self.days, False)
        except ValueError:
            k = None
            self._flag(self.days, bool(self.days.text().strip()))
        if a and k is not None:
            try:
                r = a + dt.timedelta(days=k)
                self.res_add.setText(f"{r.strftime('%d.%m.%Y')}, {WEEKDAYS[r.weekday()]}")
            except OverflowError:
                self.res_add.setText(tr("Дата вне допустимого диапазона"))
        else:
            self.res_add.setText("—")


# ════════════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ════════════════════════════════════════════════════════════════════════════
MODES = [(tr("Обычный"), lambda: ExprPage(False)), (tr("Инженерный"), lambda: ExprPage(True)),
         (tr("Программист"), ProgPage), (tr("Конвертер"), ConverterPage), (tr("Даты"), DatePage)]


class MainWindow(QMainWindow):
    def __init__(self, theme: str, mode: int):
        super().__init__()
        self.theme = theme
        self.mode = 0
        self.setWindowTitle("Equestria Calc")
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 18)
        root.setSpacing(8)
        top = QHBoxLayout()
        self.mode_btn = mk("", "small", expand=False)
        self.mode_btn.clicked.connect(self._mode_menu)
        theme_btn = mk(tr("Тема"), "small", expand=False)
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(self.mode_btn)
        top.addStretch()
        top.addWidget(theme_btn)
        root.addLayout(top)
        self.stack = QStackedWidget()
        self.pages = [make() for _, make in MODES]
        for p in self.pages:
            self.stack.addWidget(p)
        root.addWidget(self.stack, 1)
        self.set_mode(mode if 0 <= mode < len(MODES) else 0)

    def set_mode(self, i: int) -> None:
        self.mode = i
        page = self.pages[i]
        self.stack.setCurrentIndex(i)
        self.mode_btn.setText(f"☰  {MODES[i][0]}")
        self.setMinimumSize(*page.minimum)
        self.resize(*page.pref)
        self.setFocus()
        self._save()

    def _mode_menu(self) -> None:
        menu = QMenu(self)
        for i, (name, _) in enumerate(MODES):
            act = QAction(("● " if i == self.mode else "   ") + name, self)
            act.triggered.connect(lambda _=False, k=i: self.set_mode(k))
            menu.addAction(act)
        menu.exec(self.mode_btn.mapToGlobal(self.mode_btn.rect().bottomLeft()))

    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self._save()

    def _save(self) -> None:
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps({"theme": self.theme, "mode": self.mode}), encoding="utf-8")
        except OSError:
            pass

    def keyPressEvent(self, e) -> None:
        page = self.pages[self.mode]
        if e.matches(QKeySequence.StandardKey.Copy):
            text = page.copy_text()
            if text:
                QGuiApplication.clipboard().setText(text)
        elif not page.key(e):
            super().keyPressEvent(e)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Equestria Calc")
    app.setStyle("Fusion")
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        theme, mode = str(cfg.get("theme", DEFAULT_THEME)), int(cfg.get("mode", 0))
    except Exception:
        theme, mode = DEFAULT_THEME, 0
    theme = apply_theme(kit_themes.current_name())
    win = MainWindow(theme, mode)
    win.show()
    kit_themes.follow(win._set_theme, lambda: win.theme)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())