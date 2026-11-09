"""notes: markdown."""
from __future__ import annotations

import html as _html
import re


TASK_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+\[([ xX])\]\s?(.*)$")


LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


FENCE_RE = re.compile(r"^\s*(```|~~~)")


HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def count_tasks(src: str):
    """(сделано, всего) — без учёта блоков кода."""
    done = total = 0
    fence = False
    for line in src.split("\n"):
        if FENCE_RE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        m = TASK_RE.match(line)
        if m:
            total += 1
            done += m.group(3) in "xX"
    return done, total


def flip_task(line: str) -> str:
    return re.sub(r"\[([ xX])\]", lambda m: "[ ]" if m.group(1) in "xX" else "[x]", line, count=1)


def inline(s: str, th: dict, img_size=None) -> str:
    stash: list = []

    def keep(h: str) -> str:
        stash.append(h)
        return f"\x00{len(stash) - 1}\x00"

    s = _html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", lambda m: keep(
        f'<span style="font-family:monospace; background-color:{th["surface1"]}; color:{th["green"]};">'
        f'&nbsp;{m.group(1)}&nbsp;</span>'), s)

    def image(m):
        src = m.group(2)
        w = ""
        if img_size:
            size = img_size(src)
            if size and size[0] > 560:
                w = ' width="560"'
        return keep(f'<img src="{src}"{w}>')
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
               lambda m: keep(f'<a href="{m.group(2)}">{m.group(1)}</a>'), s)
    s = re.sub(r"(?<![\w\"=>])(https?://[^\s<]+[^\s<.,;:!?)\]])",
               lambda m: keep(f'<a href="{m.group(1)}">{m.group(1)}</a>'), s)
    s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])", r"<b>\1</b>", s)
    s = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<s>\1</s>", s)
    s = re.sub(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"(?<![\w_])_(?![\s_])(.+?)(?<![\s_])_(?![\w_])", r"<i>\1</i>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], s)


def css(th: dict) -> str:
    return (f"body {{ color:{th['text']}; }} "
            f"h1 {{ color:{th['accent']}; font-size:27px; }} h2 {{ color:{th['accent']}; font-size:22px; }} "
            f"h3 {{ color:{th['text']}; font-size:18px; }} h4, h5, h6 {{ color:{th['subtext']}; }} "
            f"a {{ color:{th['accent']}; }} p {{ margin-top:4px; margin-bottom:4px; }}")


def md_to_html(src: str, th: dict, hide_done: bool = False, img_size=None) -> str:
    lines = src.replace("\r\n", "\n").split("\n")
    n = len(lines)
    out: list = []
    para: list = []
    i = 0

    def flush() -> None:
        if para:
            out.append("<p>" + "<br>".join(inline(l, th, img_size) for l in para) + "</p>")
            para.clear()

    while i < n:
        line = lines[i]
        fm = FENCE_RE.match(line)
        if fm:
            flush()
            fence = fm.group(1)
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith(fence):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(f'<table width="100%" cellspacing="0" cellpadding="10"><tr><td bgcolor="{th["crust"]}">'
                       f'<pre style="color:{th["green"]};">{_html.escape(chr(10).join(code), quote=False)}</pre>'
                       f'</td></tr></table>')
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        m = HEAD_RE.match(line)
        if m:
            flush()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2), th, img_size)}</h{lvl}>")
            i += 1
            continue
        if HR_RE.match(line):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith(">"):
            flush()
            q = []
            while i < n and lines[i].lstrip().startswith(">"):
                q.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f'<table width="100%" cellspacing="0" cellpadding="6"><tr><td width="4" bgcolor="{th["accent"]}">'
                       f'</td><td style="color:{th["subtext"]};"><i>'
                       + "<br>".join(inline(l, th, img_size) for l in q) + "</i></td></tr></table>")
            continue
        if "|" in line and i + 1 < n and "-" in lines[i + 1] and TABLE_SEP_RE.match(lines[i + 1]):
            flush()

            def cells(row: str) -> list:
                row = row.strip()
                row = row[1:] if row.startswith("|") else row
                row = row[:-1] if row.endswith("|") else row
                return [c.strip() for c in row.split("|")]
            head = cells(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(cells(lines[i]))
                i += 1
            t = f'<table border="1" cellspacing="0" cellpadding="6" width="100%"><tr>'
            t += "".join(f'<th bgcolor="{th["surface1"]}">{inline(c, th, img_size)}</th>' for c in head) + "</tr>"
            for r in rows:
                t += "<tr>" + "".join(f"<td>{inline(c, th, img_size)}</td>" for c in r) + "</tr>"
            out.append(t + "</table>")
            continue
        if LIST_RE.match(line):
            flush()
            rows = []
            stack: list = []
            while i < n and LIST_RE.match(lines[i]) and not HR_RE.match(lines[i]):
                tm = TASK_RE.match(lines[i])
                lm = LIST_RE.match(lines[i])
                indent = len(lm.group(1).expandtabs(4))
                while stack and indent < stack[-1]:
                    stack.pop()
                if not stack or indent > stack[-1]:
                    stack.append(indent)
                level = len(stack) - 1
                if tm:
                    done = tm.group(3) in "xX"
                    text = inline(tm.group(4), th, img_size)
                    if done and hide_done:
                        i += 1
                        continue
                    box = ("☑" if done else "☐")
                    color = th["green"] if done else th["accent"]
                    marker = (f'<a href="toggle:{i}" style="text-decoration:none; color:{color};">'
                              f'<span style="font-size:19px;">{box}</span></a>')
                    body = f'<span style="color:{th["subtext"]};"><s>{text}</s></span>' if done else text
                else:
                    bullet = lm.group(2)
                    marker = ["•", "◦", "▪"][min(level, 2)] if bullet in "-*+" else _html.escape(bullet)
                    marker = f'<span style="color:{th["accent"]};">{marker}</span>'
                    body = inline(lm.group(3), th, img_size)
                rows.append(f'<tr><td width="{level * 22 + 4}">&nbsp;</td>'
                            f'<td width="26" valign="top">{marker}</td><td>{body}</td></tr>')
                i += 1
            if rows:
                out.append('<table cellspacing="0" cellpadding="2" width="100%">' + "".join(rows) + "</table>")
            continue
        para.append(line)
        i += 1
    flush()
    return "<html><body>" + "\n".join(out) + "</body></html>"


def line_kind(t: str) -> str:
    if TASK_RE.match(t):
        return "task"
    if re.match(r"^\s*[-*+]\s+", t):
        return "ul"
    if re.match(r"^\s*\d+[.)]\s+", t):
        return "ol"
    if re.match(r"^\s*>\s?", t):
        return "quote"
    m = re.match(r"^(#{1,6})\s", t)
    return f"h{len(m.group(1))}" if m else "none"


def split_line(t: str):
    m = re.match(r"^(\s*)(?:[-*+]\s+\[[ xX]\]\s?|[-*+]\s+|\d+[.)]\s+|>\s?|#{1,6}\s+)?(.*)$", t)
    return m.group(1), m.group(2)
