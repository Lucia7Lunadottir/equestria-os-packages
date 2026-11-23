"""Tests for the keyboard backlight logic (no hardware, no Qt, no root).

Run:  python3 -m unittest discover -s tests      (from the package folder)
"""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "modules"))
sys.path.insert(0, str(ROOT.parent / "equestria-qt-kit"))   # the kit from the sources, not an older installed one

import kbd_rgb_backends as rgb  # noqa: E402
import kbd_theme_look as look  # noqa: E402


def load_script(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(ROOT / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeChannel(rgb.WriteChannel):
    silent = True

    def __init__(self):
        self.writes = []

    def write_rgb(self, cmd, mode, color, speed):
        self.writes.append((cmd, mode, color, speed))
        return True


class EffectsAndSettings(unittest.TestCase):
    def test_effect_ids_unique_and_verified_subset(self):
        ids = [e.id for e in rgb.EFFECTS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(rgb.KERNEL_VERIFIED <= set(ids))

    def test_kernel_backend_lists_only_verified_effects(self):
        backend = rgb.KernelWmiBackend(FakeChannel())
        self.assertEqual({e.id for e in backend.effects()}, set(rgb.KERNEL_VERIFIED))

    def test_scaled_rgb(self):
        s = rgb.RgbSetting(color="#ff8040", intensity=50)
        self.assertEqual(s.scaled_rgb(), (128, 64, 32))
        self.assertEqual(rgb.RgbSetting(color="#ff8040", intensity=100).scaled_rgb(), (255, 128, 64))
        self.assertEqual(rgb.RgbSetting(color="#ffffff", intensity=0).scaled_rgb(), (3, 3, 3))  # clamped to 1 %

    def test_parse_hex_rejects_garbage(self):
        for bad in ("", "#12", "#1234567", "zzzzzz"):
            with self.assertRaises(ValueError):
                rgb.parse_hex(bad)

    def test_store_roundtrip_and_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            store = rgb.SettingsStore(Path(d) / "kbd-rgb.json")
            self.assertEqual(store.load(), rgb.RgbSetting())            # no file
            wanted = rgb.RgbSetting("breathe", "#112233", 2, True, 40)
            store.save(wanted)
            self.assertEqual(store.load(), wanted)
            store.path.write_text('{"effect": "nope", "color": "oops", "speed": 9}')
            self.assertEqual(store.load(), rgb.RgbSetting())            # invalid -> defaults

    def test_kernel_backend_writes_scaled_colour_and_save_flag(self):
        channel = FakeChannel()
        backend = rgb.KernelWmiBackend(channel)
        backend.apply(rgb.RgbSetting("static", "#ff0000", 1, False, 50))
        backend.apply(rgb.RgbSetting("static", "#ff0000"), save=True)
        self.assertEqual(channel.writes[0], (0, 0, (128, 0, 0), 1))     # preview: cmd 0
        self.assertEqual(channel.writes[1][0], 1)                       # saved to firmware: cmd 1

    def test_unsupported_effect_is_never_swapped_for_another_animation(self):
        controller = rgb.RgbController.__new__(rgb.RgbController)
        controller.backend = rgb.KernelWmiBackend(FakeChannel())
        for effect in ("rainbow_wave", "stars", "rain", "highlight", "laser", "ripple", "flash", "nope"):
            self.assertEqual(controller.resolve(rgb.RgbSetting(effect)).effect, "static", effect)
        self.assertEqual(controller.resolve(rgb.RgbSetting("rainbow_cycle")).effect, "rainbow_cycle")


class StoreKeepsWhatIsInTheKeyboard(unittest.TestCase):
    def test_saving_the_page_settings_keeps_the_record_of_what_is_written_in_the_keyboard(self):
        with tempfile.TemporaryDirectory() as d:
            store = rgb.SettingsStore(Path(d) / "kbd-rgb.json")
            self.assertIsNone(store.load_in_keyboard())
            store.save_in_keyboard({"effect": "static", "color": "#112233"})
            store.save(rgb.RgbSetting(intensity=40))                  # the slider moved: remembered at once
            self.assertEqual(store.load().intensity, 40)
            self.assertEqual(store.load_in_keyboard(), {"effect": "static", "color": "#112233"})

    def test_the_saved_settings_are_never_half_written(self):
        with tempfile.TemporaryDirectory() as d:
            store = rgb.SettingsStore(Path(d) / "kbd-rgb.json")
            for n in range(1, 30):
                store.save(rgb.RgbSetting(intensity=n))
                json.loads((Path(d) / "kbd-rgb.json").read_text())     # always valid JSON
            self.assertFalse((Path(d) / "kbd-rgb.json.tmp").exists())

    def test_firmware_look_ignores_what_the_effect_does_not_use(self):
        a = rgb.firmware_look(rgb.RgbSetting("rainbow_cycle", "#ff0000", 1, False, 30))
        b = rgb.firmware_look(rgb.RgbSetting("rainbow_cycle", "#00ff00", 1, True, 90))
        self.assertEqual(a, b)                                         # a rainbow has no colour or brightness
        self.assertNotEqual(rgb.firmware_look(rgb.RgbSetting("static", "#ff0000", intensity=100)),
                            rgb.firmware_look(rgb.RgbSetting("static", "#ff0000", intensity=50)))


class PersistToKeyboard(unittest.TestCase):
    def controller(self, in_keyboard):
        c = rgb.RgbController.__new__(rgb.RgbController)
        channel = FakeChannel()
        c.backend = rgb.KernelWmiBackend(channel)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        c.store = rgb.SettingsStore(Path(d.name) / "kbd-rgb.json")
        if in_keyboard:
            c.store.save_in_keyboard(in_keyboard)
        return c, channel

    def test_writes_the_keyboard_memory_once_and_remembers_it(self):
        c, channel = self.controller(None)
        setting = rgb.RgbSetting("static", "#ff0000", 1, True, 50)
        self.assertTrue(look.persist_to_keyboard(c, setting))
        self.assertEqual([w[0] for w in channel.writes], [1])                      # cmd 1 = into the keyboard's memory
        self.assertFalse(look.persist_to_keyboard(c, setting))                     # already there: no second write
        self.assertEqual([w[0] for w in channel.writes], [1])

    def test_a_new_look_is_written_again(self):
        c, channel = self.controller(rgb.firmware_look(rgb.RgbSetting("static", "#ff0000")))
        self.assertTrue(look.persist_to_keyboard(c, rgb.RgbSetting("static", "#00ff00")))
        self.assertEqual(len(channel.writes), 1)

    def test_a_backend_without_memory_for_a_look_is_never_asked_to_save(self):
        class NoMemory(rgb.KernelWmiBackend):
            firmware_save = False
        c, channel = self.controller(None)
        c.backend = NoMemory(channel)
        self.assertFalse(look.persist_to_keyboard(c, rgb.RgbSetting("static", "#ff0000")))
        self.assertEqual(channel.writes, [])
        self.assertIsNone(c.store.load_in_keyboard())

    def test_a_failed_write_is_not_recorded_as_saved(self):
        c, channel = self.controller(None)
        channel.write_rgb = lambda *a, **k: False
        self.assertFalse(look.persist_to_keyboard(c, rgb.RgbSetting("static", "#ff0000")))
        self.assertIsNone(c.store.load_in_keyboard())


class ThemeLook(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.user, self.system = Path(tmp.name) / "user", Path(tmp.name) / "system"
        self.user.mkdir()
        self.system.mkdir()
        saved = look.STORE
        look.STORE = look.CharacterStore(self.user, self.system)
        self.addCleanup(lambda: setattr(look, "STORE", saved))

    def put(self, folder, character):
        d = folder / "characters.d"
        d.mkdir(exist_ok=True)
        (d / f"{character['Id']}.json").write_text(json.dumps(character))

    def test_vivid_accent_is_used_as_is_pastel_is_saturated(self):
        self.assertEqual(look.led_color("#e54c35"), "#e54c35")
        pastel = look.led_color("#B39DDB")
        r, g, b = rgb.parse_hex(pastel)
        self.assertEqual(max(r, g, b), 255)
        self.assertEqual(min(r, g, b), 0)

    def test_accent_fallback_and_own_colour(self):
        self.put(self.system, {"Id": "a", "AccentColor": "#e54c35"})
        self.put(self.system, {"Id": "b", "AccentColor": "#e54c35", "KeyboardBacklight": {"Color": "#00ff00"}})
        base = rgb.RgbSetting()
        self.assertEqual(look.setting_for("a", base).color, "#e54c35")
        self.assertEqual(look.setting_for("b", base).color, "#00ff00")     # used as chosen, not adjusted
        self.assertIsNone(look.setting_for("missing", base))

    def test_rainbow_uses_first_supported_effect_else_colour(self):
        self.put(self.system, {"Id": "r", "AccentColor": "#1E88E5", "KeyboardBacklight": {"Rainbow": True}})
        base = rgb.RgbSetting()
        self.assertEqual(look.setting_for("r", base, {"static", "rainbow_cycle"}).effect, "rainbow_cycle")
        self.assertEqual(look.setting_for("r", base, {"static", "rainbow_wave"}).effect, "rainbow_wave")
        no_rainbow = look.setting_for("r", base, {"static", "breathe"})
        self.assertEqual((no_rainbow.effect, no_rainbow.color), ("static", "#1E88E5"))

    def test_user_edit_replaces_the_systems_keyboard_look_as_a_whole(self):
        self.put(self.system, {"Id": "r", "AccentColor": "#1E88E5", "KeyboardBacklight": {"Color": "#112233", "Rainbow": True}})
        self.put(self.user, {"Id": "r", "KeyboardBacklight": {"Color": "#ff0000"}})   # what the editor writes
        got = look.setting_for("r", rgb.RgbSetting(), {"rainbow_cycle"})
        self.assertEqual((got.effect, got.color), ("static", "#ff0000"))

    def test_user_clearing_the_look_falls_back_to_the_accent(self):
        self.put(self.system, {"Id": "r", "AccentColor": "#1E88E5", "KeyboardBacklight": {"Rainbow": True}})
        self.put(self.user, {"Id": "r", "KeyboardBacklight": None})                  # "Auto" in the editor
        got = look.setting_for("r", rgb.RgbSetting(), {"rainbow_cycle"})
        self.assertEqual((got.effect, got.color), ("static", "#1E88E5"))

    def _active(self, char_id):
        (self.user / "state.json").write_text(json.dumps({"active_character": char_id}))

    def test_page_sees_the_themes_colour_while_following_and_keeps_its_own_otherwise(self):
        self.put(self.system, {"Id": "a", "AccentColor": "#e54c35", "KeyboardBacklight": {"Color": "#e53b1d"}})
        self._active("a")
        saved = rgb.RgbSetting(effect="breathe", color="#2a8aff", follow_theme=False)
        self.assertEqual(look.apply_theme_view(saved), saved)                       # not following: untouched
        shown = look.apply_theme_view(saved.with_(follow_theme=True), {"static", "breathe"})
        self.assertEqual((shown.effect, shown.color), ("breathe", "#e53b1d"))       # the theme's colour, the user's animation

    def test_virtual_brightness_and_speed_are_never_changed_by_theme_code(self):
        self.put(self.system, {"Id": "a", "AccentColor": "#B39DDB", "KeyboardBacklight": {"Rainbow": True}})
        self._active("a")
        base = rgb.RgbSetting(color="#2a8aff", speed=2, intensity=37, follow_theme=True)
        for result in (look.setting_for("a", base, {"rainbow_cycle"}), look.apply_theme_view(base, {"rainbow_cycle"}),
                       look.resolve("#00ff00", True, base, {"rainbow_cycle"})):
            self.assertEqual((result.intensity, result.speed), (37, 2))
        controller = rgb.RgbController.__new__(rgb.RgbController)
        controller.backend = rgb.KernelWmiBackend(FakeChannel())
        self.assertEqual(controller.resolve(base.with_(effect="stars")).intensity, 37)

    def test_the_page_settings_file_is_watched_too(self):
        before = look.watched_files()
        with tempfile.TemporaryDirectory() as d:
            saved = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = d
            try:
                first = look.watched_files()
                (Path(d) / "equestria-os").mkdir()
                (Path(d) / "equestria-os" / "kbd-rgb.json").write_text("{}")
                self.assertNotEqual(first, look.watched_files())      # a changed brightness reaches the theme service
            finally:
                os.environ.pop("XDG_CONFIG_HOME") if saved is None else os.environ.update(XDG_CONFIG_HOME=saved)

    def test_the_users_animation_survives_every_theme_change(self):
        self.put(self.system, {"Id": "plain", "AccentColor": "#e54c35"})
        self.put(self.system, {"Id": "dash", "AccentColor": "#1E88E5", "KeyboardBacklight": {"Rainbow": True}})
        self.put(self.system, {"Id": "green", "AccentColor": "#e54c35", "KeyboardBacklight": {"Color": "#00ff00"}})
        mine = rgb.RgbSetting(effect="breathe", speed=2, intensity=40)
        avail = {"static", "breathe", "pulse", "rainbow_cycle"}
        for char_id, colour in (("plain", "#e54c35"), ("green", "#00ff00")):
            got = look.setting_for(char_id, mine, avail)
            self.assertEqual((got.effect, got.color, got.speed, got.intensity), ("breathe", colour, 2, 40), char_id)
        dash = look.setting_for("dash", mine, avail)                                 # explicit rainbow wins for that character
        self.assertEqual((dash.effect, dash.intensity), ("rainbow_cycle", 40))
        back = look.setting_for("plain", mine, avail)                                # ...and the user's animation comes back
        self.assertEqual(back.effect, "breathe")

    def test_without_a_rainbow_on_the_keyboard_the_users_effect_is_kept(self):
        self.put(self.system, {"Id": "dash", "AccentColor": "#1E88E5", "KeyboardBacklight": {"Rainbow": True}})
        got = look.setting_for("dash", rgb.RgbSetting(effect="pulse"), {"static", "pulse"})
        self.assertEqual((got.effect, got.color), ("pulse", "#1E88E5"))

    def test_old_single_file_still_works(self):
        (self.system / "characters.json").write_text(json.dumps({"Characters": [
            {"Id": "old", "AccentColor": "#e54c35", "KeyboardBacklight": {"Color": "#00ff00"}}]}))
        self.assertEqual(look.setting_for("old", rgb.RgbSetting()).color, "#00ff00")

    def test_missing_files_do_not_raise(self):
        self.assertEqual(look.active_id(), "")
        self.assertIsNone(look.setting_for("x", rgb.RgbSetting()))
        self.assertEqual(len(look.watched_files()), 6)


class Helper(unittest.TestCase):
    """The root helper must reject bad input before it touches anything."""

    @classmethod
    def setUpClass(cls):
        cls.helper = load_script("pg-kbd-rgb-helper")
        cls.helper.LED_GLOB = "/nonexistent/*kbd_backlight*/kbd_rgb_mode"   # never write to real hardware in tests

    def request(self, **kw):
        base = {"cmd": 0, "mode": 0, "r": 1, "g": 2, "b": 3, "speed": 1}
        base.update(kw)
        return base

    def test_rejects_bad_values(self):
        for bad in ({"cmd": 2}, {"mode": 9}, {"mode": 12}, {"mode": -1}, {"r": 256}, {"g": -1},
                    {"b": "1"}, {"speed": 3}, {"r": True}):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.helper.handle_rgb(self.request(**bad))

    def test_valid_request_without_device_is_a_clean_error(self):
        with self.assertRaisesRegex(ValueError, "no keyboard RGB device"):
            self.helper.handle_rgb(self.request())

    def test_direct_access_needs_a_real_boolean(self):
        for bad in (1, "true", None):
            with self.assertRaises(ValueError):
                self.helper.handle_direct_access({"enable": bad})

    def test_udev_rule_text(self):
        text = self.helper.RULE_TEXT
        self.assertIn('SUBSYSTEM=="leds"', text)
        self.assertIn("/sys%p/$$f", text)     # %p expanded by udev, $$ keeps the shell's $
        self.assertIn("wheel", text)


class Preview(unittest.TestCase):
    def test_preview_rejects_unknown_colour(self):
        preview = load_script("pg-kbd-preview")
        self.assertIsNotNone(preview.restore_setting)          # importable, entry points present
        with self.assertRaises(ValueError):
            look.led_color("not-a-colour")


if __name__ == "__main__":
    unittest.main()
