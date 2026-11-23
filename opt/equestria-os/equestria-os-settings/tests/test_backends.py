"""Backends of the keyboard lighting (one per file in modules/kbd_lighting) on a fake /sys/class/leds tree.

Nothing here touches real hardware.  Run:  python3 -m unittest discover -s tests"""

import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "modules"))

from kbd_lighting import access, asus_wmi, asusctl, base, controller, kernel_multicolor, system76  # noqa: E402


class FakeHelper:
    def __init__(self):
        self.calls = []

    def write_led_attr(self, led, attr, value):
        self.calls.append((led, attr, value))
        return True

    def close(self):
        pass


class Tree(unittest.TestCase):
    """A fake /sys/class/leds in a temporary folder."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        saved = base.LEDS_ROOT
        base.LEDS_ROOT = str(self.root)
        self.addCleanup(lambda: setattr(base, "LEDS_ROOT", saved))
        self.helper = FakeHelper()
        self.access = access.Access(self.helper)
        original = asusctl.AsusctlBackend.detect          # whatever is installed on the machine running the tests
        asusctl.AsusctlBackend.detect = classmethod(lambda cls, a: None)
        self.addCleanup(lambda: setattr(asusctl.AsusctlBackend, "detect", original))

    def led(self, name, **files):
        d = self.root / name
        d.mkdir()
        for fname, text in files.items():
            (d / fname).write_text(text + "\n")
        return d


class Discovery(Tree):
    def test_every_backend_is_found_and_the_asus_one_comes_first(self):
        ids = [c.id for c in controller.backend_classes()]
        self.assertEqual(ids[0], "asus_wmi")
        self.assertEqual(set(ids), {"asus_wmi", "asusctl", "kernel_multicolor", "system76"})

    def test_nothing_on_this_laptop_means_no_backend(self):
        c = controller.RgbController(access=self.access)
        c.backend = None
        c.refresh()
        # asusctl may exist on the machine running the tests; only the /sys based ones must stay silent
        self.assertIsNone(asus_wmi.KernelWmiBackend.detect(self.access))
        self.assertIsNone(kernel_multicolor.KernelMulticolorBackend.detect(self.access))
        self.assertIsNone(system76.System76Backend.detect(self.access))

    def test_a_backend_that_crashes_while_detecting_does_not_stop_the_others(self):
        self.led("system76_acpi::kbd_backlight", color="000000", brightness="0")
        original = asus_wmi.KernelWmiBackend.detect
        asus_wmi.KernelWmiBackend.detect = classmethod(lambda cls, a: 1 / 0)
        self.addCleanup(lambda: setattr(asus_wmi.KernelWmiBackend, "detect", original))
        c = controller.RgbController(access=self.access)
        self.assertEqual(c.backend.id, "system76")

    def test_traits_tell_what_each_backend_offers(self):
        self.assertTrue(asus_wmi.KernelWmiBackend.firmware_save)
        self.assertFalse(asus_wmi.KernelWmiBackend.experimental)
        for cls in (kernel_multicolor.KernelMulticolorBackend, system76.System76Backend):
            self.assertTrue(cls.experimental, cls.id)
            self.assertFalse(cls.firmware_save, cls.id)


class AsusOnFakeTree(Tree):
    def test_the_asus_backend_writes_the_kernel_command(self):
        d = self.led("asus::kbd_backlight", kbd_rgb_mode="", brightness="1")
        backend = controller.RgbController(access=self.access).backend
        self.assertEqual(backend.id, "asus_wmi")
        self.assertTrue(backend.silent)                          # the file is writable here: no password
        self.assertTrue(backend.apply(base.RgbSetting("breathe", "#ff8000", speed=2, intensity=50)))
        self.assertEqual((d / "kbd_rgb_mode").read_text().strip(), "0 1 128 64 0 2")
        backend.apply(base.RgbSetting("static", "#ff0000"), save=True)
        self.assertTrue((d / "kbd_rgb_mode").read_text().startswith("1 0 255 0 0"))   # cmd 1: into the laptop's memory

    def test_the_asus_backend_wins_over_a_multicolor_led(self):
        self.led("asus::kbd_backlight", kbd_rgb_mode="")
        self.led("rgb:kbd_backlight", multi_index="red green blue", multi_intensity="0 0 0")
        self.assertEqual(controller.RgbController(access=self.access).backend.id, "asus_wmi")


class Multicolor(Tree):
    def make(self, order="green blue red", maximum="50 50 50"):
        return self.led("uniwill:rgb:kbd_backlight", multi_index=order, multi_intensity="0 0 0",
                        multi_max_intensity=maximum, brightness="1", max_brightness="2")

    def test_the_colour_is_written_in_the_leds_own_order_and_scale(self):
        d = self.make()
        backend = controller.RgbController(access=self.access).backend
        self.assertEqual(backend.id, "kernel_multicolor")
        self.assertTrue(backend.apply(base.RgbSetting("static", "#ff8000")))
        # order green blue red, maximum 50 each: green 128 -> 25, blue 0 -> 0, red 255 -> 50
        self.assertEqual((d / "multi_intensity").read_text().strip(), "25 0 50")

    def test_virtual_brightness_is_applied_to_the_colour_and_the_leds_brightness_file_is_never_touched(self):
        d = self.make(order="red green blue", maximum="255 255 255")
        backend = controller.RgbController(access=self.access).backend
        backend.apply(base.RgbSetting("static", "#ffffff", intensity=50))
        self.assertEqual((d / "multi_intensity").read_text().strip(), "128 128 128")
        self.assertEqual((d / "brightness").read_text().strip(), "1")

    def test_only_a_static_colour_and_nothing_else_is_offered(self):
        self.make()
        backend = controller.RgbController(access=self.access).backend
        self.assertEqual([e.id for e in backend.effects()], ["static"])
        self.assertFalse(backend.apply(base.RgbSetting("breathe", "#ff0000")))
        c = controller.RgbController(access=self.access)
        self.assertEqual(c.resolve(base.RgbSetting("breathe")).effect, "static")      # never swapped for another animation

    def test_a_colour_the_led_has_but_we_have_no_value_for_stays_off(self):
        d = self.led("x:rgbw:kbd_backlight", multi_index="red green blue white", multi_intensity="0 0 0 0")
        backend = kernel_multicolor.KernelMulticolorBackend.detect(self.access)
        backend.apply(base.RgbSetting("static", "#102030"))
        self.assertEqual((d / "multi_intensity").read_text().split()[3], "0")

    def test_a_read_only_file_goes_through_the_root_helper(self):
        d = self.make()
        os.chmod(d / "multi_intensity", 0o444)
        if os.access(d / "multi_intensity", os.W_OK):
            self.skipTest("rights that ignore file permissions (root)")
        backend = kernel_multicolor.KernelMulticolorBackend.detect(self.access)
        self.assertFalse(backend.silent)
        self.assertTrue(backend.apply(base.RgbSetting("static", "#ff0000")))
        self.assertEqual(self.helper.calls, [("uniwill:rgb:kbd_backlight", "multi_intensity", "0 0 50")])


class System76(Tree):
    def test_the_colour_is_six_hex_digits(self):
        d = self.led("system76_acpi::kbd_backlight", color="000000", brightness="255")
        backend = controller.RgbController(access=self.access).backend
        self.assertEqual(backend.id, "system76")
        backend.apply(base.RgbSetting("static", "#ff8000", intensity=100))
        self.assertEqual((d / "color").read_text().strip(), "FF8000")
        self.assertEqual((d / "brightness").read_text().strip(), "255")                # not touched

    def test_a_missing_colour_file_means_no_backend(self):
        self.led("system76_acpi::kbd_backlight", brightness="255")
        self.assertIsNone(system76.System76Backend.detect(self.access))


class RootHelper(Tree):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("helper", str(ROOT / "pg-kbd-rgb-helper"))
        spec = importlib.util.spec_from_loader("helper", loader)
        cls.hmod = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.hmod)

    def setUp(self):
        super().setUp()
        for name, value in (("LEDS_ROOT", str(self.root)), ("SYSFS", str(self.root))):
            old = getattr(self.hmod, name)
            setattr(self.hmod, name, value)
            self.addCleanup(lambda n=name, o=old: setattr(self.hmod, n, o))
        self.d = self.led("uniwill:rgb:kbd_backlight", multi_index="green blue red", multi_intensity="0 0 0",
                          multi_max_intensity="50 50 50")

    def call(self, **kw):
        req = {"led": "uniwill:rgb:kbd_backlight", "attr": "multi_intensity", "value": "10 20 30"}
        req.update(kw)
        return self.hmod.handle_led_attr(req)

    def test_a_good_request_is_written(self):
        self.assertEqual(self.call(), {"ok": True})
        self.assertEqual((self.d / "multi_intensity").read_text().strip(), "10 20 30")

    def test_everything_else_is_refused_before_anything_is_written(self):
        for bad in ({"led": "../etc"}, {"led": "uniwill:rgb:status"}, {"led": "a/b:kbd_backlight"}, {"led": 5},
                    {"attr": "brightness"}, {"attr": "trigger"}, {"attr": "../multi_intensity"},
                    {"value": "10 20"}, {"value": "10 20 30 40"}, {"value": "10 20 51"}, {"value": "a b c"},
                    {"value": "10;20 30"}, {"value": 5}, {"value": ""}):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.call(**bad)
        self.assertEqual((self.d / "multi_intensity").read_text().strip(), "0 0 0")

    def test_system76_colour_must_be_six_hex_digits(self):
        d = self.led("system76_acpi::kbd_backlight", color="000000")
        ok = {"led": "system76_acpi::kbd_backlight", "attr": "color"}
        self.assertEqual(self.hmod.handle_led_attr({**ok, "value": "FF8000"}), {"ok": True})
        for bad in ("FF80", "GG0000", "FF8000 ", "#FF8000", "1234567"):
            with self.assertRaises(ValueError, msg=bad):
                self.hmod.handle_led_attr({**ok, "value": bad})
        self.assertEqual((d / "color").read_text().strip(), "FF8000")

    def test_the_udev_rule_covers_every_colour_file(self):
        for name in ("kbd_rgb_mode", "multi_intensity", "color"):
            self.assertIn(name, self.hmod.RULE_TEXT)


if __name__ == "__main__":
    unittest.main()
