"""Who is signed in and which licenses are active, read from the Unity CLI and shared by every screen."""
import time

from PyQt6.QtCore import QObject, pyqtSignal

from cli_errors import NOT_SIGNED_IN, code_of

STALE_AFTER = 30  # seconds; the state is read again when the window is shown after this


class AccountState(QObject):
    changed = pyqtSignal()

    def __init__(self, cli, parent=None):
        super().__init__(parent)
        self.cli = cli
        self.auth = None          # data of `unity auth status`, None until read
        self.license = None       # data of `unity license status`, None until read
        self.problems = {"auth": None, "license": None}   # why a read failed (text), per kind
        self.loading = set()
        self.loaded_at = 0.0

    def load(self):
        self.loaded_at = time.monotonic()
        for kind in ("auth", "license"):
            self.loading.add(kind)
            self.cli.status(kind, lambda data, k=kind: self.received(k, data, None),
                            lambda reason, k=kind: self.received(k, None, reason))
        self.changed.emit()

    def received(self, kind, data, problem):
        self.loading.discard(kind)
        if code_of(problem) == NOT_SIGNED_IN:
            data, problem = {"loggedIn": False}, None   # an ordinary state, not an error
        setattr(self, kind, data if isinstance(data, dict) else None)
        self.problems[kind] = problem
        self.changed.emit()

    def stale(self):
        return time.monotonic() - self.loaded_at > STALE_AFTER

    # ---- reading --------------------------------------------------------------------------------

    def signed_in(self):
        return bool((self.auth or {}).get("loggedIn"))

    def user(self):
        user = (self.auth or {}).get("user")
        return user if isinstance(user, dict) else {}

    def licenses(self):
        """[(license, count)]: the CLI can list the same license twice, it is shown once with a count."""
        entries = (self.license or {}).get("licenses")
        grouped = {}
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("product"):
                key = tuple(str(entry.get(name) or "") for name in ("product", "type", "organization", "expires"))
                grouped[key] = (entry, grouped.get(key, (entry, 0))[1] + 1)
        return list(grouped.values())
