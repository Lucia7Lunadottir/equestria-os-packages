import os
import subprocess
import tempfile
from datetime import datetime
from backend import SnapshotData

SCREENSHOTS_DIR = os.path.expanduser("~/.cache/equestria-os-save-point/screenshots")

def init_screenshots():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

def take_screenshot() -> str | None:
    now_str  = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = os.path.join(SCREENSHOTS_DIR, f"{now_str}.webp")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp = tf.name

    captured = False
    for cmd in [
        ["spectacle", "-b", "-f", "-n", "-o", tmp],
        ["grim", tmp],
        ["scrot", tmp],
        ["import", "-window", "root", tmp],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=10)
            if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                captured = True
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if not captured:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return None

    converted = False
    for cmd in [
        ["ffmpeg", "-y", "-i", tmp, "-vf", "scale=800:450",
         "-codec:v", "libwebp", "-quality", "82", out_path],
        ["convert", tmp, "-resize", "800x450!", out_path],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=30)
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                converted = True
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    try:
        os.unlink(tmp)
    except OSError:
        pass

    return out_path if converted else None

def find_screenshot(snap: SnapshotData) -> str | None:
    exact = os.path.join(SCREENSHOTS_DIR, f"{snap.fs_id}.webp")
    if os.path.exists(exact):
        return exact
    try:
        snap_dt = datetime.strptime(snap.fs_id, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None
    best_path, best_diff = None, float("inf")
    try:
        entries = os.listdir(SCREENSHOTS_DIR)
    except OSError:
        return None
    for fname in entries:
        if not fname.endswith(".webp"):
            continue
        try:
            ss_dt = datetime.strptime(fname[:-5], "%Y-%m-%d_%H-%M-%S")
            diff  = abs((snap_dt - ss_dt).total_seconds())
            if diff < best_diff and diff <= 300:
                best_diff, best_path = diff, os.path.join(SCREENSHOTS_DIR, fname)
        except ValueError:
            continue
    if best_path:
        try:
            os.rename(best_path, exact)
            return exact
        except OSError:
            return best_path
    return None