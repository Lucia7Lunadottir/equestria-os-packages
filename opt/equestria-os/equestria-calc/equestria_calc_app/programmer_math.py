"""calc: programmer math."""
from __future__ import annotations

import ast
import operator
import re


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
