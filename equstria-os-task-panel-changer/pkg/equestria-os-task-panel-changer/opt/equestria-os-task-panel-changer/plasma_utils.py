import os
import shutil

PLASMA_CONFIG = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
PLASMA_SHELLRC = os.path.expanduser("~/.config/plasmashellrc")

_QDBUS_BIN = None

def find_qdbus():
    global _QDBUS_BIN
    if _QDBUS_BIN is not None:
        return _QDBUS_BIN
    for candidate in ("qdbus6", "qdbus-qt6", "qdbus"):
        if shutil.which(candidate):
            _QDBUS_BIN = candidate
            return _QDBUS_BIN
    _QDBUS_BIN = "qdbus6"  # fallback
    return _QDBUS_BIN

def set_desktop_icons_state(hide: bool) -> bool:
    """Modifies plasma-org.kde.plasma.desktop-appletsrc directly to change folder/containment state."""
    if not os.path.exists(PLASMA_CONFIG):
        return False

    try:
        with open(PLASMA_CONFIG, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return False

    old_plugin = "org.kde.plasma.folder" if hide else "org.kde.desktopcontainment"
    new_plugin = "org.kde.desktopcontainment" if hide else "org.kde.plasma.folder"

    changed = False
    new_lines = []
    in_containments = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[Containments]"):
            in_containments = True
        elif stripped.startswith("[") and not stripped.startswith("[Containments]"):
            in_containments = False

        if in_containments and stripped == f"plugin={old_plugin}":
            new_lines.append(f"plugin={new_plugin}\n")
            changed = True
        else:
            new_lines.append(line)

    if changed:
        try:
            with open(PLASMA_CONFIG, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except OSError:
            return False

    return changed

def generate_script_from_panels(panels_config):
    LAUNCHER_MAP = {
        "kickoff":    "org.kde.plasma.kickoff",
        "kicker":     "org.kde.plasma.kicker",
        "kickerdash": "org.kde.plasma.kickerdash",
    }
    ICON = "/usr/share/pixmaps/equestria-os-logo.png"
    parts = ["var a=panels();for(var i=0;i<a.length;i++){a[i].remove();}"]
    for i, p in enumerate(panels_config):
        v = f"p{i}"
        pos      = p.get("position", "bottom")
        height   = p.get("height", 48)
        width_px = p.get("width", 0)
        offset   = p.get("offset", 0)
        align    = p.get("alignment", "center" if p.get("floating") else "left")
        floatP   = p.get("floating", False)

        vis      = p.get("visibilityMode", "none")
        # Жесткая защита и конвертация старых названий из Plasma 5 -> Plasma 6
        if vis == "windowsbelow": vis = "dodgewindows"
        if vis == "windowscover": vis = "windowsgobelow"
        if p.get("autohide", False) and vis == "none":
            vis = "autohide"

        lmode    = p.get("lengthMode", "fill")
        launch   = p.get("launcher", "none")
        ww       = p.get("widgets", [])

        parts.append(f"var {v}=new Panel;")
        parts.append(f"{v}.location='{pos}';")
        parts.append(f"{v}.height={height};")
        parts.append(f"{v}.alignment='{align}';")
        if floatP:
            parts.append(f"{v}.floating=true;")
        parts.append(f"{v}.lengthMode='{lmode}';")
        if width_px > 0:
            parts.append(f"{v}.minimumLength={width_px};{v}.maximumLength={width_px};")
        if offset != 0:
            parts.append(f"{v}.offset={offset};")

        if vis != "none":
            parts.append(f"{v}.hiding='{vis}';")

        has_launcher = launch in LAUNCHER_MAP
        has_taskbar  = "taskbar" in ww
        has_right    = any(x in ww for x in ("pager", "monitor", "systray", "clock"))

        if has_launcher:
            pid = LAUNCHER_MAP[launch]
            parts.append(f"var k{i}={v}.addWidget('{pid}');")
            parts.append(f"k{i}.currentConfigGroup=['General'];")
            parts.append(f"k{i}.writeConfig('icon','{ICON}');")

        if has_launcher and (has_taskbar or has_right):
            parts.append(f"{v}.addWidget('org.kde.plasma.panelspacer');")

        if has_taskbar:
            parts.append(f"{v}.addWidget('org.kde.plasma.icontasks');")
            if has_right:
                parts.append(f"{v}.addWidget('org.kde.plasma.panelspacer');")

        if "pager"   in ww: parts.append(f"{v}.addWidget('org.kde.plasma.pager');")
        if "monitor" in ww: parts.append(f"{v}.addWidget('org.kde.plasma.systemmonitor');")
        if "systray" in ww: parts.append(f"{v}.addWidget('org.kde.plasma.systemtray');")
        if "clock"   in ww: parts.append(f"{v}.addWidget('org.kde.plasma.digitalclock');")

        parts.append(f"{v}.height={height};")

    return "".join(parts)

def generate_panel_svg(hex_color, opacity_float):
    """Generate a Plasma 6-compatible panel-background.svg with proper hints."""
    c = hex_color
    op = f"{opacity_float:.2f}"
    r = 8  # corner radius for floating

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">\n'
        '  <defs>\n'
        f'    <style>rect {{ fill: {c}; fill-opacity: {op}; }}</style>\n'
        '  </defs>\n'
        '\n'
        '  <rect id="hint-stretch-borders" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        f'  <rect id="center"      x="6" y="6" width="88" height="88"/>\n'
        f'  <rect id="top"         x="6" y="0" width="88" height="6"/>\n'
        f'  <rect id="bottom"      x="6" y="94" width="88" height="6"/>\n'
        f'  <rect id="left"        x="0" y="6" width="6" height="88"/>\n'
        f'  <rect id="right"       x="94" y="6" width="6" height="88"/>\n'
        f'  <rect id="topleft"     x="0" y="0" width="6" height="6"/>\n'
        f'  <rect id="topright"    x="94" y="0" width="6" height="6"/>\n'
        f'  <rect id="bottomleft"  x="0" y="94" width="6" height="6"/>\n'
        f'  <rect id="bottomright" x="94" y="94" width="6" height="6"/>\n'
        '\n'
        '  <rect id="shadow-top"         x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-bottom"      x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-left"        x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-right"       x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-topleft"     x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-topright"    x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-bottomleft"  x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="shadow-bottomright" x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '\n'
        f'  <rect id="floating-center"      x="{r}" y="{r}" width="{100-2*r}" height="{100-2*r}" rx="{r}" ry="{r}"/>\n'
        f'  <rect id="floating-top"         x="{r}" y="0" width="{100-2*r}" height="{r}"/>\n'
        f'  <rect id="floating-bottom"      x="{r}" y="{100-r}" width="{100-2*r}" height="{r}"/>\n'
        f'  <rect id="floating-left"        x="0" y="{r}" width="{r}" height="{100-2*r}"/>\n'
        f'  <rect id="floating-right"       x="{100-r}" y="{r}" width="{r}" height="{100-2*r}"/>\n'
        f'  <rect id="floating-topleft"     x="0" y="0" width="{r}" height="{r}"/>\n'
        f'  <rect id="floating-topright"    x="{100-r}" y="0" width="{r}" height="{r}"/>\n'
        f'  <rect id="floating-bottomleft"  x="0" y="{100-r}" width="{r}" height="{r}"/>\n'
        f'  <rect id="floating-bottomright" x="{100-r}" y="{100-r}" width="{r}" height="{r}"/>\n'
        '\n'
        '  <rect id="floating-shadow-top"         x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-bottom"      x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-left"        x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-right"       x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-topleft"     x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-topright"    x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-bottomleft"  x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '  <rect id="floating-shadow-bottomright" x="0" y="0" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '\n'
        f'  <rect id="mask-center"      x="{r}" y="{r}" width="{100-2*r}" height="{100-2*r}" rx="{r}" ry="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-top"         x="{r}" y="0" width="{100-2*r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-bottom"      x="{r}" y="{100-r}" width="{100-2*r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-left"        x="0" y="{r}" width="{r}" height="{100-2*r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-right"       x="{100-r}" y="{r}" width="{r}" height="{100-2*r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-topleft"     x="0" y="0" width="{r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-topright"    x="{100-r}" y="0" width="{r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-bottomleft"  x="0" y="{100-r}" width="{r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        f'  <rect id="mask-bottomright" x="{100-r}" y="{100-r}" width="{r}" height="{r}" fill="#fff" fill-opacity="1"/>\n'
        '\n'
        '  <rect id="hint-compose-over-border" width="0" height="0" fill="none" fill-opacity="0"/>\n'
        '</svg>\n'
    )
