"""How a write that needs root is performed (no Qt).

  HelperChannel   the root helper started through pkexec (one password prompt), kept only while needed
  Access          what a backend gets: the helper, and a way to write one LED attribute file
                  directly when the optional udev rule made it writable, else through the helper
"""

import json
import os
import subprocess
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from . import base


def _find_helper() -> str:
    """Installed helper first; when running from the sources, the one next to the app."""
    installed = "/usr/bin/pg-kbd-rgb-helper"
    if os.path.exists(installed):
        return installed
    beside = Path(__file__).resolve().parent.parent.parent / "pg-kbd-rgb-helper"
    return str(beside) if beside.exists() else installed


HELPER_PATH = _find_helper()
RULE_PATH = "/etc/udev/rules.d/91-equestria-kbd-rgb.rules"


class WriteChannel(ABC):
    #: True when a write never needs the user to type a password.
    silent: bool = False

    @abstractmethod
    def write_rgb(self, cmd: int, mode: int, rgb: tuple[int, int, int], speed: int) -> bool: ...

    def close(self) -> None:
        """Release anything held open (the root helper)."""


class HelperChannel(WriteChannel):
    """Root helper via pkexec. Started on first use, kept until close()."""

    silent = False

    def __init__(self, helper: str = HELPER_PATH):
        self._helper = helper
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _ensure_started(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True
        try:
            self._proc = subprocess.Popen(
                ["pkexec", self._helper, "--serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1)
            return True
        except OSError:
            self._proc = None
            return False

    def request(self, payload: dict) -> bool:
        with self._lock:
            if not self._ensure_started():
                return False
            proc = self._proc
            try:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
                reply = proc.stdout.readline()   # blocks while the password prompt is open
                return bool(reply) and json.loads(reply).get("ok") is True
            except (OSError, ValueError):
                self._proc = None
                return False

    def write_rgb(self, cmd, mode, rgb, speed) -> bool:
        return self.request({"op": "rgb", "cmd": cmd, "mode": mode,
                             "r": rgb[0], "g": rgb[1], "b": rgb[2], "speed": speed})

    def write_led_attr(self, led: str, attr: str, value: str) -> bool:
        return self.request({"op": "led_attr", "led": led, "attr": attr, "value": value})

    def set_direct_access(self, enable: bool) -> bool:
        return self.request({"op": "direct_access", "enable": enable})

    def close(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
            proc.wait(timeout=3)
        except (OSError, subprocess.SubprocessError):
            proc.kill()


class Access:
    """What every backend is given. It hides the difference between "the file is writable for me"
    (the optional udev rule) and "ask the root helper"."""

    def __init__(self, helper: HelperChannel | None = None):
        self.helper = helper or HelperChannel()

    @staticmethod
    def led_file(led_dir: str, attr: str) -> str:
        return os.path.join(led_dir, attr)

    def can_write_directly(self, led_dir: str, attr: str) -> bool:
        path = self.led_file(led_dir, attr)
        return os.path.exists(path) and os.access(path, os.W_OK)

    def write_led_attr(self, led_dir: str, attr: str, value: str) -> bool:
        """Write `value` into <led_dir>/<attr>: directly if allowed, otherwise through the root helper."""
        path = self.led_file(led_dir, attr)
        if self.can_write_directly(led_dir, attr):
            try:
                with open(path, "w") as f:
                    f.write(value + "\n")
                return True
            except OSError:
                return False
        return self.helper.write_led_attr(os.path.basename(led_dir.rstrip("/")), attr, value)

    def close(self) -> None:
        self.helper.close()
