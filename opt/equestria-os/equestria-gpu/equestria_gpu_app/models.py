"""gpu: models."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from .localization import tr


def _f(name, branch, vk, dx11, dx12, note=""):
    """dx11/dx12: 1 — да, 2 — ограниченно, 0 — нет."""
    return dict(name=name, branch=branch, vk=vk, dx11=dx11, dx12=dx12, note=note)


FAMILIES = {
    "GB": _f("Blackwell (RTX 50)", "open", "1.3+", 1, 1),
    "AD": _f("Ada Lovelace (RTX 40)", "open", "1.3+", 1, 1),
    "GA": _f("Ampere (RTX 30)", "open", "1.3+", 1, 1),
    "TU": _f("Turing (RTX 20 / GTX 16)", "open", "1.3+", 1, 1),
    "GV": _f("Volta (Titan V)", "580", "1.3", 1, 1),
    "GP": _f("Pascal (GTX 10)", "580", "1.3", 1, 1,
             tr("models.dx12_pascal_goes_through_vkd3d")),
    "GM": _f("Maxwell (GTX 9xx / 750)", "580", "1.3", 1, 1,
             tr("models.first_generation_maxwell_gtx_750")),
    "GK": _f("Kepler (GTX 6xx / 7xx)", "470", "1.2", 2, 0,
             tr("models.driver_470_provides_only_vulkan")),
    "GF": _f("Fermi (GT/GTX 4xx / 5xx)", "390", "", 0, 0,
             tr("models.fermi_opengl_4_5_only")),
    "TESLA": _f("Tesla (GeForce 8xx — 3xx)", "none", "", 0, 0,
                tr("models.arch_has_no_proprietary_drivers")),
}


BRANCHES = {
    "open": dict(dkms="nvidia-open-dkms", utils="nvidia-utils", lib32="lib32-nvidia-utils",
                 label="nvidia-open-dkms (590+)"),
    "580": dict(dkms="equestria-nvidia-580xx-dkms", utils="equestria-nvidia-580xx-utils",
                lib32="lib32-equestria-nvidia-580xx-utils", label="equestria-nvidia-580xx (580.xx)"),
    "470": dict(dkms="nvidia-470xx-dkms", utils="nvidia-470xx-utils", lib32=None, label="nvidia-470xx (470.xx)"),
    "390": dict(dkms="nvidia-390xx-dkms", utils="nvidia-390xx-utils", lib32=None, label="nvidia-390xx (390.xx)"),
    "none": dict(dkms=None, utils=None, lib32=None, label=tr("models.nouveau_open_driver")),
}


WHY = {
    "open": tr("models.open_nvidia_kernel_modules_with"),
    "580": tr("models.last_driver_branch_580_xx"),
    "470": tr("models.last_branch_supporting_kepler_vulkan"),
    "390": tr("models.last_branch_supporting_fermi_opengl"),
    "none": tr("models.there_no_proprietary_drivers_generation"),
}


BRANCH_GPUS = {
    "open": tr("models.turing_newer_geforce_rtx_20"),
    "580": tr("models.maxwell_pascal_volta_gtx_750"),
    "470": tr("models.kepler_gtx_650_660_670"),
    "390": tr("models.fermi_gtx_460_470_480"),
    "none": tr("models.any_card_as_fallback_geforce"),
}


BRANCH_PKGS = {b: {x for x in (d["dkms"], d["utils"], d["lib32"]) if x} for b, d in BRANCHES.items()}


EXTRA_PKGS = {"nvidia-dkms", "nvidia", "nvidia-lts", "nvidia-open", "nvidia-open-lts", "equestria-nvidia-dkms"}


def foreign_pkgs(branch: str, pkgs: dict) -> list:
    own = BRANCH_PKGS.get(branch, set())
    out = []
    for b, s in BRANCH_PKGS.items():
        if b != branch:
            out += [p for p in s if p in pkgs and p not in own]
    for p in EXTRA_PKGS:
        if p not in pkgs:
            continue
        if branch == "open" and p in ("nvidia-open", "nvidia-open-lts"):
            continue
        if branch == "580" and p == "equestria-nvidia-dkms":
            continue
        out.append(p)
    return sorted(set(out))


def nv_family(chip: str) -> str:
    c = chip.upper()
    if c[:2] in FAMILIES and c[2:3].isdigit():
        return c[:2]
    if c.startswith(("GT", "NV", "MCP")) or re.match(r"G\d", c):
        return "TESLA"
    return ""


@dataclass
class Gpu:
    addr: str
    vid: str
    did: str
    vendor: str
    name: str
    chip: str
    driver: str = ""
    modules: list = field(default_factory=list)
    boot: bool = False
    fam: str = ""
    rtx: bool = False
    checks: list = field(default_factory=list)

    @property
    def branch(self) -> str:
        return FAMILIES[self.fam]["branch"] if self.fam in FAMILIES else "none"

    @property
    def fam_name(self) -> str:
        return FAMILIES[self.fam]["name"] if self.fam in FAMILIES else ""

    @property
    def worst(self) -> str:
        for lvl in ("fail", "warn"):
            if any(c.level == lvl for c in self.checks):
                return lvl
        return "ok"


@dataclass
class Sys:
    kernel: str = ""
    session: str = ""
    pkgs: dict = field(default_factory=dict)
    dkms: list = field(default_factory=list)
    multilib: bool = False
    vk: list = field(default_factory=list)
    vk_tool: bool = False
    smi: dict = field(default_factory=dict)
    nv_version: str = ""
    modeset: str = ""
    env: dict = field(default_factory=dict)
    avail: dict = field(default_factory=dict)
    gpus: list = field(default_factory=list)

    def vk_for(self, g: Gpu):
        for d in self.vk:
            if d.get("vendorID", "").lower() == "0x" + g.vid:
                return d
        return None

    def pkgver(self, name: str) -> str:
        v = self.pkgs.get(name, "")
        return re.sub(r"^\d+:", "", v).rsplit("-", 1)[0] if v else ""
