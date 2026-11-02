import os
import shlex


PACMAN_HOOK_PATH  = "/etc/pacman.d/hooks/equestria-save-point.hook"
FLATPAK_HOOK_PATH = "/etc/profile.d/60-equestria-save-point.sh"
HOOK_SCRIPT_SRC   = "/opt/equestria-os/equestria-os-save-point/equestria-save-point.hook"
FLATPAK_SCRIPT_SRC= "/opt/equestria-os/equestria-os-save-point/flatpak-hook.sh"
HOOK_CONFIG_PATH  = "/var/lib/equestria-save-point/hook-config"


def check_hooks_installed() -> tuple[bool, bool]:
    return (
        os.path.exists(PACMAN_HOOK_PATH),
        os.path.exists(FLATPAK_HOOK_PATH),
    )

def build_hook_apply_script(hook_pacman: bool, hook_flatpak: bool, keep_last: int) -> str:
    parts = [
        "mkdir -p /var/lib/equestria-save-point",
        f"echo {shlex.quote(str(keep_last))} > {HOOK_CONFIG_PATH}",
    ]

    if hook_pacman:
        parts += [
            "mkdir -p /etc/pacman.d/hooks",
            f"cp {HOOK_SCRIPT_SRC} {PACMAN_HOOK_PATH}",
            f"chmod 644 {PACMAN_HOOK_PATH}",
        ]
    else:
        parts.append(f"rm -f {PACMAN_HOOK_PATH}")

    if hook_flatpak:
        parts += [
            f"cp {FLATPAK_SCRIPT_SRC} {FLATPAK_HOOK_PATH}",
            f"chmod 644 {FLATPAK_HOOK_PATH}",
        ]
    else:
        parts.append(f"rm -f {FLATPAK_HOOK_PATH}")

    return " && ".join(parts)