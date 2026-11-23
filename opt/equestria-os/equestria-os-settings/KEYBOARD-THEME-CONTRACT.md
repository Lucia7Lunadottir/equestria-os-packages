# Keyboard backlight ↔ character themes: the contract

Two independent packages cooperate through plain data. Neither may require the other.

| Package | Role |
|---|---|
| `equestria-os-character-theme` | stores, per character, **a colour and a rainbow flag**. Knows nothing about light effects. |
| `equestria-os-settings` | knows the keyboard hardware and effects; applies the look (service `pg-kbd-theme-sync`, preview `pg-kbd-preview`). |

## Data format

In the character's data (one file per character in `characters.d/`, see below; the old single
`characters.json` is still read):

```json
"KeyboardBacklight": {"Color": "#rrggbb", "Rainbow": true}
```

* Both fields are optional; the whole key may be absent (it is not written when empty).
* `Color` — `#rrggbb`. Used as chosen. Without it the character's `AccentColor` is used
  (pastel accents are saturated for LEDs, see `led_color`).
* `Rainbow: true` — "show a rainbow". Settings picks the first rainbow effect the keyboard
  can draw (`RAINBOW_EFFECTS`); with none available the user's own effect is used.
* Without the rainbow the **user's own animation** (chosen on the settings page) is shown in the character's
  colour: the theme decides the colour, never the animation.
* Readers ignore unknown fields; writers keep fields they do not know (forward compatible).

## Where it is read from

Always through `equestria_kit.character_store.CharacterStore` (shared kit, no Qt): the system
characters (`<package>/characters.d/NN-<id>.json`) with the user's overrides
(`~/.local/share/EquestriaOS/Themes/characters.d/<id>.json`) on top, field by field.
A user file holds only the fields that differ from the system character; `null` removes a field.
`KeyboardBacklight` is one value: what the theme editor writes replaces the system's as a whole.

## Preview helper

`pg-kbd-preview --color #rrggbb | --accent #rrggbb  [--rainbow]` shows a look,
`pg-kbd-preview --restore` goes back. It is optional: when it is not installed, or the
keyboard cannot be changed without a password, it does nothing.

## When a package is missing

* no `equestria-os-settings`: the theme editor still stores the choice; the preview does nothing
  and the editor says so;
* no `equestria-os-character-theme`: the service has nothing to follow and stays idle.
