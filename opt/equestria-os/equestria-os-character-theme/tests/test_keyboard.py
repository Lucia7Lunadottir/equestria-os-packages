"""Tests for the theme editor's keyboard data and preview (no Qt, no hardware).

Run:  python3 -m unittest discover -s tests      (from the package folder)
"""

import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import keyboard_look  # noqa: E402
import keyboard_preview  # noqa: E402


class Clean(unittest.TestCase):
    def test_keeps_valid_colour_and_rainbow_only(self):
        self.assertEqual(keyboard_look.clean({"Color": "#AABBCC", "Rainbow": True}),
                         {"Color": "#aabbcc", "Rainbow": True})

    def test_drops_garbage_and_foreign_fields(self):
        self.assertEqual(keyboard_look.clean({"Color": "red", "Rainbow": "yes", "Effect": "stars", "Speed": 2}), {})
        self.assertEqual(keyboard_look.clean(None), {})
        self.assertEqual(keyboard_look.clean([1, 2]), {})

    def test_package_knows_no_light_effects(self):
        self.assertFalse(hasattr(keyboard_look, "EFFECTS"))      # effects are equestria-os-settings' business

    def test_colour_and_rainbow_are_independent(self):
        self.assertEqual(keyboard_look.clean({"Color": "#000000"}), {"Color": "#000000"})
        self.assertEqual(keyboard_look.clean({"Rainbow": True}), {"Rainbow": True})
        self.assertEqual(keyboard_look.clean({"Rainbow": False}), {})


class Preview(unittest.TestCase):
    def test_without_the_settings_package_every_call_is_a_silent_noop(self):
        with mock.patch.object(keyboard_preview.shutil, "which", return_value=None), \
                mock.patch.object(keyboard_preview.subprocess, "run") as run:
            p = keyboard_preview.KeyboardPreview()
            self.assertFalse(p.available())
            p.show("#ff0000", "#00ff00", True)
            p.restore()
            time.sleep(0.1)
            run.assert_not_called()

    def test_arguments(self):
        calls = []
        done = threading.Event()

        def fake_run(cmd, **kw):
            calls.append(cmd[1:])
            done.set()
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(keyboard_preview.shutil, "which", return_value="/usr/bin/pg-kbd-preview"), \
                mock.patch.object(keyboard_preview.subprocess, "run", fake_run):
            p = keyboard_preview.KeyboardPreview()
            p.show("#112233", "#00ff00", False)
            done.wait(2)
            self.assertEqual(calls[-1], ["--color", "#112233"])
            done.clear()
            p.show(None, "#00ff00", True)
            done.wait(2)
            self.assertEqual(calls[-1], ["--accent", "#00ff00", "--rainbow"])

    def test_burst_is_coalesced_to_the_newest_request(self):
        release, started, calls = threading.Event(), threading.Event(), []

        def slow_run(cmd, **kw):
            calls.append(cmd[1:])
            started.set()
            release.wait(2)
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(keyboard_preview.shutil, "which", return_value="/x"), \
                mock.patch.object(keyboard_preview.subprocess, "run", slow_run):
            p = keyboard_preview.KeyboardPreview()
            p.show("#000001", "#fff", False)
            started.wait(2)
            for n in range(2, 8):                  # a drag in the colour dialog: many fast requests
                p.show(f"#00000{n}", "#fff", False)
            release.set()
            time.sleep(0.3)
            self.assertEqual(calls[0], ["--color", "#000001"])
            self.assertEqual(calls[-1], ["--color", "#000007"])   # the newest one
            self.assertLessEqual(len(calls), 3)                    # no backlog


if __name__ == "__main__":
    unittest.main()
