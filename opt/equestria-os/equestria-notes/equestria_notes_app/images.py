"""notes: images."""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
from PyQt6.QtGui import QImage, QTextBlockFormat, QTextFormat, QTextListFormat
from datetime import datetime


IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


BULLETS = (QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListCircle, QTextListFormat.Style.ListSquare)


MK = QTextBlockFormat.MarkerType


FSA = QTextFormat.Property.FontSizeAdjustment.value


def _unique(d: str, name: str) -> str:
    stem, ext = os.path.splitext(name)
    p, n = os.path.join(d, name), 1
    while os.path.exists(p):
        n += 1
        p = os.path.join(d, f"{stem}-{n}{ext}")
    return p


def store_image(src: str, note_dir: str) -> str:
    d = os.path.join(note_dir, "assets")
    os.makedirs(d, exist_ok=True)
    name = re.sub(r"[^\w.-]", "_", os.path.basename(src))
    dst = os.path.join(d, name)
    if os.path.abspath(src) != os.path.abspath(dst):
        dst = _unique(d, name)
        shutil.copyfile(src, dst)
    return "assets/" + os.path.basename(dst)


REFDEF_RE = re.compile(r"^[ ]{0,3}\[([^\]\n]+)\]:[ \t]*<?([^\s>]+)>?[ \t]*$", re.M)


REFUSE_RE = re.compile(r"(!?)\[([^\]\n]*)\]\[([^\]\n]*)\]")


def save_data_uri(uri: str, note_dir: str) -> str:
    m = re.match(r"data:image/([\w+.-]+);base64,(.*)$", uri, re.S)
    if not m:
        return uri
    try:
        raw = base64.b64decode(m.group(2))
        ext = {"jpeg": "jpg", "svg+xml": "svg"}.get(m.group(1), m.group(1))
        d = os.path.join(note_dir, "assets")
        os.makedirs(d, exist_ok=True)
        name = f"img-{hashlib.sha1(raw).hexdigest()[:10]}.{ext}"
        p = os.path.join(d, name)
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(raw)
        return "assets/" + name
    except (OSError, ValueError):
        return uri


def resolve_refs(text: str, note_dir: str) -> str:
    """![][image1] / [текст][ref] + определения внизу → обычные ![](url) / [текст](url)."""
    defs: dict = {}

    def grab(m):
        defs[m.group(1).strip().lower()] = m.group(2)
        return ""
    body = REFDEF_RE.sub(grab, text)
    if not defs:
        return text

    def use(m):
        key = (m.group(3) or m.group(2)).strip().lower()
        if key not in defs:
            return m.group(0)
        url = defs[key]
        if url.startswith("data:image/"):
            url = save_data_uri(url, note_dir)
        return f"{m.group(1)}[{m.group(2)}]({url})"
    return REFUSE_RE.sub(use, body).rstrip("\n") + "\n"


def store_qimage(img: QImage, note_dir: str) -> str:
    d = os.path.join(note_dir, "assets")
    os.makedirs(d, exist_ok=True)
    dst = _unique(d, f"img-{datetime.now():%Y%m%d-%H%M%S}.png")
    img.save(dst, "PNG")
    return "assets/" + os.path.basename(dst)
