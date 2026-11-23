"""What the keyboard should look like for a character theme (no Qt).

Shared by the theme-following service (pg-kbd-theme-sync) and the preview helper
(pg-kbd-preview). The theme switcher stores only, per character,
    "KeyboardBacklight": {"Color": "#rrggbb", "Rainbow": true}
and never learns which light effects exist: that is decided here.
  * Rainbow ticked  -> the first rainbow effect the keyboard can draw
                       (RAINBOW_EFFECTS); if it has none, the user's own effect;
  * otherwise       -> the effect (animation) the user chose on the settings page — it stays
                       through every theme change — in the character's colour, or in its
                       AccentColor when no colour was chosen.
The theme decides the colour; the animation is the user's choice.
The data format shared with the theme switcher is described in
KEYBOARD-THEME-CONTRACT.md (next to this package's modules/ folder).
"""

import colorsys
import os
import sys

import kbd_rgb_backends as rgb

try:   # the theme switcher's data (characters.d + legacy characters.json) is read through the shared kit
    from equestria_kit.character_store import CharacterStore
except ImportError:   # running from the sources: the kit lies next to this package
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                    "equestria-qt-kit"))
    from equestria_kit.character_store import CharacterStore

STORE = CharacterStore()
# Tried in this order; the first one the keyboard supports is "the rainbow".
RAINBOW_EFFECTS = ("rainbow_cycle", "rainbow_wave")
PASTEL_BELOW = 0.75   # saturation under which an accent looks washed out on LEDs


def led_color(accent: str) -> str:
    """LEDs mix light additively: a pastel accent (little saturation) shows up
    whitish. Keep the hue and use full saturation and brightness for those;
    already vivid accents are used exactly as they are."""
    r, g, b = rgb.parse_hex(accent)
    h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s >= PASTEL_BELOW:
        return accent
    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def active_id() -> str:
    import json
    try:
        with open(STORE.user_dir / "state.json", encoding="utf-8") as f:
            return str(json.load(f).get("active_character") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def watched_files() -> tuple:
    """Changes when the character is switched, the themes' data is edited, or the page's own settings
    (e.g. the virtual brightness) change."""
    try:
        settings_mtime = (rgb.config_dir() / "kbd-rgb.json").stat().st_mtime_ns
    except OSError:
        settings_mtime = 0
    return STORE.signature() + (settings_mtime,)


def persist_to_keyboard(controller: rgb.RgbController, setting: rgb.RgbSetting) -> bool:
    """Write the look into the keyboard's own memory unless it is already there.

    While the keyboard follows the theme, the user must not have to open the settings page just to make
    the new look survive switching off (and show on the sign-in screen): the theme service does it, once the
    look has been stable for a few seconds. Returns True if the keyboard's memory was written."""
    if controller.backend is None or not controller.backend.firmware_save:
        return False                      # this laptop has no memory for a look; the login service re-applies it instead
    look = rgb.firmware_look(controller.resolve(setting))
    if look == controller.store.load_in_keyboard():
        return False
    if controller.apply(setting, save=True):
        controller.store.save_in_keyboard(look)
        return True
    return False


def accent_of(character: dict, base: rgb.RgbSetting) -> str:
    accent = character.get("AccentColor")
    try:
        return led_color(accent) if accent else base.color
    except (ValueError, TypeError):
        return base.color


def resolve(color: str | None, rainbow: bool, base: rgb.RgbSetting,
            available: set | None) -> rgb.RgbSetting | None:
    """Turn "colour + rainbow flag" into a setting. `available` — effect ids the keyboard can draw
    (None: all). The user's own effect (base.effect) is kept; only a character with the rainbow
    ticked overrides it, and only if the keyboard can draw a rainbow."""
    effect = base.effect
    if rainbow:
        effect = next((r for r in RAINBOW_EFFECTS if available is None or r in available), base.effect)
    try:
        rgb.parse_hex(color)
    except (ValueError, TypeError, AttributeError):
        return None
    return base.with_(effect=effect, color=color)


def _character(char_id: str) -> dict | None:
    return next((c for c in STORE.read() if str(c.get("Id")) == str(char_id)), None)


def setting_for(char_id: str, base: rgb.RgbSetting, available: set | None = None) -> rgb.RgbSetting | None:
    """The store already merges system and user data; the character's KeyboardBacklight is
    one value (the theme editor writes it whole)."""
    character = _character(char_id)
    if character is None:
        return None
    keyboard = character.get("KeyboardBacklight")
    keyboard = keyboard if isinstance(keyboard, dict) else {}
    color = keyboard.get("Color") or accent_of(character, base)   # own colour is used as chosen
    return resolve(color, keyboard.get("Rainbow") is True, base, available)


def accent_for(char_id: str, base: rgb.RgbSetting) -> str:
    """Colour used when the character has none of its own (for previews)."""
    return accent_of(_character(char_id) or {}, base)


def apply_theme_view(base: rgb.RgbSetting, available: set | None = None) -> rgb.RgbSetting:
    """What the keyboard really shows while it follows the theme, as the settings page should see it.

    The page keeps its own saved colour/effect; with "follow the theme" on, the theme decides them. Without
    this, changing anything on the page would send the page's old colour and undo the theme's. The colour
    comes from the theme (and the effect only for a character with the rainbow ticked); the user's effect,
    speed and virtual brightness stay exactly as they set them — nothing but the page itself changes them.
    """
    if not base.follow_theme:
        return base
    char_id = active_id()
    themed = setting_for(char_id, base, available) if char_id else None
    if themed is None:
        return base
    return base.with_(effect=themed.effect, color=themed.color)
