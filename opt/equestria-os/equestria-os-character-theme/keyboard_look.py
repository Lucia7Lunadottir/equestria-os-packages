"""How a character looks on the keyboard backlight (no Qt).

Stored in the character as  "KeyboardBacklight": {"Color": "#rrggbb", "Rainbow": true}.

This package knows only two things: a colour and "rainbow or not". Which light
effect is used for the rainbow (and whether the keyboard can do one at all) is
decided by equestria-os-settings, which applies it. Without the rainbow, the
colour is used; with no colour set, the character's accent colour is used.
An empty dict means "not set". The format is shared with equestria-os-settings; see
/usr/share/doc/equestria-os-settings/KEYBOARD-THEME-CONTRACT.md
"""

import re

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def clean(data) -> dict:
    """Only a valid #rrggbb colour and a rainbow flag survive (the file may be foreign)."""
    if not isinstance(data, dict):
        return {}
    out = {}
    color = data.get("Color")
    if isinstance(color, str) and _HEX.match(color):
        out["Color"] = color.lower()
    if data.get("Rainbow") is True:
        out["Rainbow"] = True
    return out
