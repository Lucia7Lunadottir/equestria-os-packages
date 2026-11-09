"""gpu: commands."""
from __future__ import annotations

import shlex
from .localization import tr
from .models import BRANCHES, Gpu, Sys, foreign_pkgs
from .probes import cached_pkg
from .rules import headers_pkg


COMPAT = {"open": ({"TU", "GA", "AD", "GB"}, set()),
          "580": ({"GM", "GP", "GV"}, {"TU", "GA", "AD", "GB"}),
          "470": ({"GK"}, set()),
          "390": ({"GF"}, set()),
          "none": ({"TESLA", ""}, {"GF", "GK", "GM", "GP", "GV", "TU", "GA", "AD", "GB"})}


def compat(g: Gpu, branch: str) -> str:
    """rec — рекомендуется, ok — работает, no — не подходит."""
    rec, ok = COMPAT[branch]
    return "rec" if g.fam in rec else "ok" if g.fam in ok else "no"


def branch_status(S: Sys, branch: str) -> tuple:
    """(текст, доступен ли для установки)."""
    if branch == "none":
        return tr("commands.built_into_kernel"), True
    br = BRANCHES[branch]
    st = [S.avail.get(br["dkms"], ""), S.avail.get(br["utils"], "")]
    if all(st):
        if st[0] == "installed":
            return tr("commands.installed", S.pkgs.get(br['dkms'], '')), True
        return (tr("commands.repository") if "repo" in st else tr("commands.offline_cache")), True
    return tr("commands.neither_repositories_nor_offline_cache"), False


def build_branch_cmd(S: Sys, branch: str, o: dict) -> list:
    """Ручная установка выбранной ветки: чистим чужую, ставим свою, собираем DKMS."""
    br = BRANCHES[branch]
    rm = [p for p in foreign_pkgs(branch, S.pkgs) if p not in ("nvidia-utils", "lib32-nvidia-utils")]
    rm += [p for p in ("xf86-video-nouveau", "vulkan-nouveau", "lib32-vulkan-nouveau") if p in S.pkgs]
    want = [br["dkms"], br["utils"]]
    if br["lib32"] and S.multilib and o.get("b32", True):
        want.append(br["lib32"])
    if o.get("settings", True) and branch in ("open", "580"):
        want.append("nvidia-settings")
    if any(g.vendor != "nvidia" for g in S.gpus):
        want.append("nvidia-prime")
    want += ["dkms", headers_pkg(S.kernel)]
    repo, cache = [], []
    for p in dict.fromkeys(want):
        if p in S.pkgs:
            continue
        if S.avail.get(p) == "cache":
            cache.append(cached_pkg(p))
        else:
            repo.append(p)
    q = lambda xs: " ".join(shlex.quote(x) for x in xs)
    lines = []
    if rm:
        lines.append(f"pacman -Rns --noconfirm {q(rm)} || true")
    if cache:
        lines.append(f"yes | pacman -U --needed --overwrite '*' {q(cache)}")
    if repo:
        lines.append(f"yes | pacman -S --needed --overwrite '*' {q(repo)}")
    lines += ["mkdir -p /etc/modprobe.d",
              "[ -f /etc/modprobe.d/nvidia.conf ] || printf 'options nvidia_drm modeset=1\\n' > /etc/modprobe.d/nvidia.conf",
              "printf 'blacklist nouveau\\noptions nouveau modeset=0\\n' > /etc/modprobe.d/blacklist-nouveau.conf",
              "dkms autoinstall",
              "if command -v mkinitcpio >/dev/null 2>&1; then mkinitcpio -P; fi",
              tr("commands.echo_echo_done_reboot_system")]
    return ["pkexec", "sh", "-c", "\n".join(lines)]


def build_cmd(kind: str, arg, o: dict):
    if kind == "raw":
        return arg
    if kind == "sync":
        a = list(arg or [])
        if o.get("b32", True):
            a.append("--32")
        if not o.get("settings", True):
            a.append("--no-settings")
        if o.get("nodkms"):
            a.append("--no-dkms")
        return ["pkexec", "sh", "-c", 'printf "y\\n" | pg-gpu-sync "$@"', "sh", *a]
    if kind == "pkgs":
        return ["pkexec", "pacman", "-S", "--needed", "--noconfirm", *arg]
    if kind == "dkms":
        return ["pkexec", "sh", "-c",
                "dkms autoinstall; if command -v mkinitcpio >/dev/null 2>&1; then mkinitcpio -P; fi"]
    return None
