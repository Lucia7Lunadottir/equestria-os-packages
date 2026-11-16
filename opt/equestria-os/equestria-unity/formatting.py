"""Values turned into what the interface shows: relative times, short paths, names, a colour seed."""
import hashlib
import time
from pathlib import Path

from kit import tr


def ago_parts(stamp, now=None):
    """(unit, count) for a relative time label, or ('date', 'YYYY-MM-DD')."""
    if not stamp:
        return "none", 0
    seconds = (now or time.time()) - stamp
    if seconds < 60:
        return "now", 0
    if seconds < 3600:
        return "min", int(seconds // 60)
    if seconds < 86400:
        return "hour", int(seconds // 3600)
    if seconds < 30 * 86400:
        return "day", int(seconds // 86400)
    return "date", time.strftime("%Y-%m-%d", time.localtime(stamp))


def when(stamp):
    unit, value = ago_parts(stamp)
    return "" if unit == "none" else tr(f"time.{unit}", value)


def short(path):
    """A path with the home folder written as ~."""
    text = str(path)
    home = str(Path.home())
    return "~" + text[len(home):] if text == home or text.startswith(home + "/") else text


def free_name(parent, base="My project"):
    parent = Path(parent)
    if not (parent / base).exists():
        return base
    for number in range(2, 1000):
        if not (parent / f"{base} {number}").exists():
            return f"{base} {number}"
    return base


def bad_name(name):
    return (not name or name in (".", "..") or Path(name).name != name or name.startswith("-")
            or any(ch in name for ch in '<>:"|?*\0'))


def seed(text):
    """A stable number from a name, so every project and Editor gets its own colour."""
    return int(hashlib.md5(text.encode()).hexdigest()[:6], 16)
