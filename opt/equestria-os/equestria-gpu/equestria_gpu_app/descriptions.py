"""gpu: descriptions."""
from __future__ import annotations
from .localization import live_i18n

from .localization import tr
from .models import BRANCHES, BRANCH_PKGS, EXTRA_PKGS, FAMILIES, Gpu, Sys
from .probes import VENDOR_LABEL
from .rules import api_tuple


def capabilities(g: Gpu, S: Sys) -> list:
    vk = S.vk_for(g)
    api = vk.get("apiVersion", "").split()[0] if vk else ""
    if g.vendor != "nvidia":
        ok = api_tuple(api) >= (1, 3)
        return [(live_i18n.format_text('{0} Vulkan {1}', '✓' if api else '✗', api or '—'), "ok" if api else "fail"),
                (live_i18n.format_text('{0} DX12 (VKD3D)', '✓' if ok else '✗'), "ok" if ok else "warn")]
    fam = FAMILIES.get(g.fam)
    drv = g.driver == "nvidia"
    if not fam:
        return [(tr("descriptions.generation_unknown"), "warn")]

    def chip(label, val):
        sym = {1: "✓", 2: "~", 0: "✗"}[val]
        lvl = "fail" if val == 0 else ("ok" if val == 1 and drv else "warn")
        return (live_i18n.format_text('{0} {1}', sym, label), lvl)

    return [chip("DX9–11 (DXVK)", fam["dx11"]), chip("DX12 (VKD3D)", fam["dx12"]),
            (live_i18n.format_text('{0} Vulkan {1}', '✓' if (api or fam['vk']) else '✗', api or fam['vk'] or '—'),
             ("ok" if drv else "warn") if (api or fam["vk"]) else "fail"),
            chip("DLSS", 1 if g.rtx else 0), chip("Ray Tracing", 1 if g.rtx else 0)]


def overview_rows(g: Gpu, S: Sys) -> list:
    r = [(tr("descriptions.model"), g.name), (tr("descriptions.vendor"), VENDOR_LABEL[g.vendor]),
         ("PCI", live_i18n.format_text('{0}  [{1}:{2}]', g.addr, g.vid, g.did) + (tr("descriptions.chip", g.chip) if g.chip else ""))]
    if g.vendor == "nvidia":
        r.append((tr("descriptions.generation"), g.fam_name or tr("descriptions.unknown_nouveau_will_used")))
    r.append((tr("descriptions.role"), tr("descriptions.primary_boot_vga") if g.boot else tr("descriptions.secondary") + (" (PRIME offload)" if len(S.gpus) > 1 else "")))
    r.append((tr("descriptions.current_driver"), g.driver or tr("common.not_loaded")))
    if g.vendor == "nvidia":
        r.append((tr("descriptions.recommended_branch"), BRANCHES[g.branch]["label"]))
        inst = [live_i18n.format_text('{0} {1}', p, S.pkgs[p]) for p in sorted(S.pkgs) if p in BRANCH_PKGS["open"] | BRANCH_PKGS["580"]
                | BRANCH_PKGS["470"] | BRANCH_PKGS["390"] | EXTRA_PKGS | {"nvidia-settings", "nvidia-prime"}]
        r.append((tr("descriptions.installed"), live_i18n.join_text('\n', (inst)) or tr("descriptions.no_nvidia_drivers")))
        if S.nv_version:
            r.append((tr("descriptions.kernel_module_version"), S.nv_version))
    vk = S.vk_for(g)
    r.append(("Vulkan", live_i18n.format_text('{0}  ·  {1}', vk.get('apiVersion', '?'), vk.get('driverName', '')) if vk else tr("descriptions.unknown")))
    sm = S.smi.get(g.addr[-7:].lower())
    if sm:
        r += [("VRAM", tr("descriptions.mib", sm['vram'])), (tr("descriptions.temperature"), live_i18n.format_text('{0} °C', sm['temp'])), (tr("descriptions.load"), live_i18n.format_text('{0} %', sm['util'])),
              (tr("descriptions.power"), tr("descriptions.w", sm['power'])), (tr("descriptions.core_clock"), tr("descriptions.mhz", sm['clock'])), ("P-state", sm["pstate"])]
    r.append((tr("descriptions.session"), S.session))
    return r


def launch_options(g: Gpu, S: Sys, f: dict) -> str:
    env, pre = [], []
    if f.get("prime"):
        if g.vendor == "nvidia":
            env += ["__NV_PRIME_RENDER_OFFLOAD=1", "__VK_LAYER_NV_optimus=NVIDIA_only", "__GLX_VENDOR_LIBRARY_NAME=nvidia",
                    'DXVK_FILTER_DEVICE_NAME="NVIDIA"', 'VKD3D_FILTER_DEVICE_NAME="NVIDIA"']
        else:
            env += ["DRI_PRIME=1", live_i18n.format_text('MESA_VK_DEVICE_SELECT={0}:{1}', g.vid, g.did)]
    if f.get("nvapi"):
        env += ["PROTON_ENABLE_NVAPI=1", "DXVK_ENABLE_NVAPI=1"]
    if f.get("dxr"):
        env.append("VKD3D_CONFIG=dxr")
    if f.get("nod3d12"):
        env.append("PROTON_NO_D3D12=1")
    if f.get("hud"):
        pre.append("mangohud")
    if f.get("gamemode"):
        pre.append("gamemoderun")
    return live_i18n.join_text(' ', (env + pre + ["%command%"]))


def tips_for(g: Gpu) -> str:
    base = (tr("descriptions.how_apply_steam_game_properties"))
    fam = FAMILIES.get(g.fam)
    if g.vendor == "nvidia" and fam:
        extra = {
            "GP": tr("descriptions.gtx_10xx_if_game_does"),
            "GM": tr("descriptions.maxwell_dx12_limited_crashes_use"),
            "GK": tr("descriptions.kepler_dx12_impossible_dx9_11"),
            "GF": tr("descriptions.fermi_no_vulkan_proton_dxvk"),
        }.get(g.fam, "")
        if g.rtx:
            extra = (tr("descriptions.rtx_enable_nvapi_dlss_dxr"))
        return (extra + "\n\n" if extra else "") + base
    return base
