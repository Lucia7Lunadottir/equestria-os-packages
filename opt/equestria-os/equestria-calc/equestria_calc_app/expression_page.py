"""calc: expression page."""
from __future__ import annotations

import re
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget
from .arithmetic import evaluate, fmt
from .localization import live_i18n, tr
from .widgets import HistoryPanel, PageBase, fit, mk, right_label, toggle_neg


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
        self.hist_btn = mk(tr("common.history"), "small", expand=False)
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
            live_i18n.call(self.deg_btn.setText, "Deg" if self.deg else "Rad")
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
            fit(self.result_label, tr("common.error"), True)
            return
        self.hist.add(f"{self.expr}  =  {res}", res)
        self.prev, self.expr, self.fresh = self.expr, res, True
        self._refresh()

    def _refresh(self) -> None:
        e = self.expr
        live_i18n.call(self.expr_label.setText, f"{self.prev} =" if self.fresh else e)
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
