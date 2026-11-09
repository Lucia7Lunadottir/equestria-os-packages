"""calc: arithmetic."""
from __future__ import annotations

import ast
import math
import operator


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
