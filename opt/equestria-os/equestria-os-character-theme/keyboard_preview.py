"""Preview of a character's keyboard look while editing (no Qt).

Calls the optional helper `pg-kbd-preview` from equestria-os-settings, passing only a
colour and a "rainbow" flag. This package never learns which light effects exist; if
the helper is not installed (or the keyboard cannot be changed without a password),
every call is a silent no-op.

Calls are coalesced on a worker thread: while one runs, only the newest later request
is kept, so dragging in a colour dialog never queues up a backlog.
"""

import shutil
import subprocess
import threading

BINARY = "pg-kbd-preview"


class KeyboardPreview:
    def __init__(self):
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._latest: list | None = None
        self._worker: threading.Thread | None = None

    @staticmethod
    def available() -> bool:
        return shutil.which(BINARY) is not None

    def show(self, color: str | None, accent: str, rainbow: bool) -> None:
        """Own colour if there is one, else the character's accent (the helper adjusts it for LEDs)."""
        args = ["--color", color] if color else ["--accent", accent]
        if rainbow:
            args.append("--rainbow")
        self._submit(args)

    def restore(self) -> None:
        """Back to what the keyboard should show now (the theme's look or the page's own setting)."""
        self._submit(["--restore"])

    def _submit(self, args: list) -> None:
        if not self.available():
            return
        with self._lock:
            self._latest = args
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, daemon=True)
                self._worker.start()
        self._wake.set()

    def _run(self) -> None:
        while True:
            with self._lock:
                args, self._latest = self._latest, None
            if args is None:
                return
            try:
                subprocess.run([BINARY, *args], capture_output=True, timeout=15)
            except (OSError, subprocess.SubprocessError):
                pass
