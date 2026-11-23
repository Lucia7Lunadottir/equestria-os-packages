"""Bring new built-in assets (wallpapers, cutiemarks) to a user who already has the folders.

The first run copies whole folders. A later package version may add a theme (its wallpaper
folder, its icon); this adds only what the user does not have yet — one level deep,
so a whole new wallpaper folder or a new icon file — and never overwrites or removes
anything of theirs. No Qt.
"""

import os
import shutil


def add_missing(src_dir: str, dst_dir: str) -> list[str]:
    """Copy the entries of src_dir that dst_dir lacks. Returns the names that were added."""
    added = []
    try:
        entries = sorted(os.listdir(src_dir))
    except OSError:
        return added
    os.makedirs(dst_dir, exist_ok=True)
    for name in entries:
        src, dst = os.path.join(src_dir, name), os.path.join(dst_dir, name)
        if os.path.lexists(dst):
            continue
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            added.append(name)
        except OSError:
            continue   # a failed copy must not stop the others or the app
    return added
