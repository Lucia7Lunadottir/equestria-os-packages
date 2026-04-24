import os
import shlex

PACMAN_HOOK_PATH  = "/etc/pacman.d/hooks/equestria-save-point.hook"
FLATPAK_HOOK_PATH = "/etc/profile.d/60-equestria-save-point.sh"
HOOK_SCRIPT_SRC   = "/opt/equestria-os-save-point/equestria-save-point.hook"
FLATPAK_SCRIPT_SRC= "/opt/equestria-os-save-point/flatpak-hook.sh"
HOOK_CONFIG_PATH  = "/var/lib/equestria-save-point/hook-config"
REPO_PATH_SYS     = "/var/lib/equestria-save-point/repo-path"

def check_hooks_installed() -> tuple[bool, bool]:
    return (
        os.path.exists(PACMAN_HOOK_PATH),
        os.path.exists(FLATPAK_HOOK_PATH),
    )

def build_hook_apply_script(hook_pacman: bool, hook_flatpak: bool, 
                            repo_path: str, move_old_repo: str | None, 
                            keep_last: int, restic_repo_default: str) -> str:
    parts = [
        "mkdir -p /var/lib/equestria-save-point",
        f"echo {shlex.quote(str(keep_last))} > {HOOK_CONFIG_PATH}",
    ]

    # Move old repository to new location before updating the pointer
    if move_old_repo and move_old_repo != repo_path:
        new_parent = shlex.quote(os.path.dirname(repo_path))
        parts += [
            f"mkdir -p {new_parent}",
            f"mv {shlex.quote(move_old_repo)} {shlex.quote(repo_path)}",
        ]

    # Persist custom repo path (remove the override file if default)
    if repo_path and repo_path != restic_repo_default:
        parts.append(f"echo {shlex.quote(repo_path)} > {REPO_PATH_SYS}")
    else:
        parts.append(f"rm -f {REPO_PATH_SYS}")

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