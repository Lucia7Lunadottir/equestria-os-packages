import shutil
import subprocess
import sys

from core import check_writable


def find_elevator() -> str | None:
    """Return path to pkexec or kdesu, whichever is available."""
    for cmd in ("pkexec", "kdesu"):
        path = shutil.which(cmd)
        if path:
            return path
    return None


def needs_elevation(paths: list) -> bool:
    """Return True if any path is not writable by the current user."""
    return any(not check_writable(p) for p in paths)


def relaunch_elevated(elevator: str) -> None:
    """Re-run the current process under elevator and exit immediately."""
    subprocess.Popen([elevator, sys.executable] + sys.argv)
    sys.exit(0)
