import os
import datetime
import xml.etree.ElementTree as ET

FLATPAK_APPSTREAM = "/var/lib/flatpak/appstream/flathub/x86_64/active/appstream.xml.gz"
FLATPAK_ICONS_DIR = "/var/lib/flatpak/appstream/flathub/x86_64/active/icons/128x128"
SCREENSHOT_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".cache", "equestria-os-software-center", "screenshots"
)

_GENERIC_PACMAN_DESC = "Arch Repository"
_GENERIC_FLATPAK_DESC = "Flathub application"


def cleanup_screenshot_cache():
    if not os.path.exists(SCREENSHOT_CACHE_DIR):
        return
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    for fname in os.listdir(SCREENSHOT_CACHE_DIR):
        fpath = os.path.join(SCREENSHOT_CACHE_DIR, fname)
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                os.remove(fpath)
        except Exception:
            pass


def extract_appstream_text(el):
    parts = []
    if el.text:
        t = el.text.strip()
        if t:
            parts.append(t)
    for child in el:
        child_text = extract_appstream_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            t = child.tail.strip()
            if t:
                parts.append(t)
    return " ".join(parts)


def normalize_key(s):
    """Lowercase + strip non-alphanumeric — used for cross-source dedup matching."""
    return ''.join(c for c in s.lower() if c.isalnum())


def guess_cat(name):
    n = name.lower()
    if any(x in n for x in ["game", "steam", "lutris", "wine"]): return "Games"
    if any(x in n for x in ["browser", "firefox", "network", "chat", "discord"]): return "Internet"
    if any(x in n for x in ["vlc", "audio", "video", "media", "music"]): return "Media"
    if any(x in n for x in ["image", "photo", "gimp", "graphics"]): return "Graphics"
    if any(x in n for x in ["nvidia", "mesa", "driver", "kernel"]): return "Drivers"
    return "Software"


def merge_packages(pacman_pkgs, flatpak_pkgs):
    """Enrich Pacman entries with Flatpak icon/screenshots/description; skip matched Flatpak duplicates.

    Matching heuristic (normalized = lowercase, alphanumeric only):
      - normalize(last component of app_id) == normalize(pacman_name)
      - OR normalize(flatpak display name) == normalize(pacman_name)

    Returns: list(pacman_pkgs) + unmatched_flatpak_pkgs
    """
    if not flatpak_pkgs:
        return list(pacman_pkgs)

    pacman_index = {normalize_key(pkg.name): pkg for pkg in pacman_pkgs}
    unmatched = []

    for fp in flatpak_pkgs:
        app_id_key = normalize_key(fp.app_id.split('.')[-1]) if fp.app_id else ""
        name_key = normalize_key(fp.name)

        matched = (pacman_index.get(app_id_key)
                   or (pacman_index.get(name_key) if name_key != app_id_key else None))

        if matched:
            if fp.icon_url and not matched.icon_url:
                matched.icon_url = fp.icon_url
            if fp.screenshot_urls and not matched.screenshot_urls:
                matched.screenshot_urls = fp.screenshot_urls
            # Enrich generic Pacman description with Flatpak's
            if (fp.desc and fp.desc != _GENERIC_FLATPAK_DESC
                    and matched.desc in (_GENERIC_PACMAN_DESC, "")):
                matched.desc = fp.desc
        else:
            unmatched.append(fp)

    return list(pacman_pkgs) + unmatched
