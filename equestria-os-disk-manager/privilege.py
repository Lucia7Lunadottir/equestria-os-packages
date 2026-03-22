import os
import shutil
import subprocess
import sys

from core import check_writable

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disk_backend.py")


def find_elevator() -> str | None:
    """Return path to kdesu or pkexec, whichever is available."""
    for cmd in ("kdesu", "/usr/lib/kf6/kdesu", "pkexec"):
        path = shutil.which(cmd)
        if path:
            return path
        if os.path.isfile(cmd) and os.access(cmd, os.X_OK):
            return cmd
    return None


def needs_elevation(paths: list) -> bool:
    """Return True if any path is not writable by the current user."""
    return any(not check_writable(p) for p in paths)


def start_elevated(elevator: str, sources: list, destination: str):
    """Start the backend script under elevator. Returns a Popen object."""
    inner = [sys.executable, BACKEND] + sources + ["--dest", destination]
    cmd = [elevator, "--"] + inner if os.path.basename(elevator) == "kdesu" else [elevator] + inner
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
