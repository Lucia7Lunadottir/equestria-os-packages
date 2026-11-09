"""gpu: rules."""
from __future__ import annotations

import glob
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from equestria_kit import live_i18n
from .localization import tr
from .models import BRANCHES, BRANCH_PKGS, FAMILIES, Gpu, Sys, WHY, foreign_pkgs


LVL_ORDER = {"fail": 0, "warn": 1, "info": 2, "ok": 3}


SYNC = (tr("rules.install_recommended_driver"), "sync", ["--reset-mode"])


@dataclass
class Check:
    level: str
    title: str
    detail: str
    fix: tuple | None = None


def headers_pkg(kernel: str) -> str:
    m = re.search(r"-(lts|zen|hardened|rt|cachyos)", kernel)
    return f"linux-{m.group(1)}-headers" if m else "linux-headers"


def api_tuple(s: str) -> tuple:
    m = re.match(r"(\d+)\.(\d+)", s or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


class CheckContext:
    """Всё, что нужно правилам про одну карту, + собранные результаты."""

    def __init__(self, g: Gpu, S: Sys):
        self.g, self.S = g, S
        self.fam = FAMILIES.get(g.fam)
        self.br = BRANCHES[g.branch]
        self.dkms_pkg = self.br["dkms"]
        self.results: list = []

    def add(self, lvl: str, title: str, detail: str, fix=None) -> None:
        self.results.append(Check(lvl, title, detail, fix))

    def unpack(self) -> tuple:
        return self.g, self.S, self.fam, self.br, self.dkms_pkg, self.add


class Rule(ABC):
    """Одна проверка диагностики (Open/Closed: новая проверка — новый класс в
    RULES, существующие не трогаются). vendors — к каким картам применима."""
    vendors: tuple = ("nvidia",)

    def applies(self, ctx: CheckContext) -> bool:
        return ctx.g.vendor in self.vendors

    @abstractmethod
    def run(self, ctx: CheckContext) -> None: ...


class KernelDriverRule(Rule):
    """1. Драйвер ядра: Какой драйвер ядра обслуживает карту."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if g.driver == "nvidia":
            add("ok", tr("rules.kernel_driver_nvidia"), tr("rules.card_runs_nvidia_driver", ' ' + S.nv_version if S.nv_version else ''))
        elif g.driver == "nouveau":
            if g.branch == "none":
                add("info", tr("rules.kernel_driver_nouveau"), tr("rules.generation_nouveau_standard_option"))
            else:
                add("fail", tr("rules.card_runs_nouveau_not_nvidia"),
                    tr("rules.under_nouveau_there_no_nvapi", br['label']), SYNC)
        elif not g.driver:
            add("fail", tr("rules.kernel_driver_not_loaded"),
                tr("rules.graphics_card_not_bound_any"), SYNC)
        else:
            add("info", tr("rules.kernel_driver", g.driver), tr("rules.non_standard_driver_example_vfio"))


class BranchPackagesRule(Rule):
    """2. Пакеты ветки: Установлен ли пакет нужной ветки и нет ли пакетов чужой ветки."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if dkms_pkg:
            have = (dkms_pkg in S.pkgs or (g.branch == "open" and ("nvidia-open" in S.pkgs or "nvidia-open-lts" in S.pkgs))
                    or (g.branch == "580" and "equestria-nvidia-dkms" in S.pkgs))
            if have:
                add("ok", tr("rules.driver_package_installed", dkms_pkg if dkms_pkg in S.pkgs else tr("rules.compatible_equivalent")),
                    tr("rules.branch", g.fam_name, br['label']))
            else:
                add("fail", tr("rules.recommended_package_not_installed", dkms_pkg),
                    tr("rules.needs", g.fam_name, br['label'], WHY[g.branch]), SYNC)
            bad = foreign_pkgs(g.branch, S.pkgs)
            if bad:
                add("fail", tr("rules.packages_another_driver_branch_installed"),
                    tr("rules.incompatible_with_branches_mutually_exclusive", ', '.join(bad), g.fam_name)
                    + (tr("rules.nvidia_open_pascal_maxwell_volta") if g.branch == "580" else "."), SYNC)
        elif g.branch == "none":
            bad = [p for p in BRANCH_PKGS["open"] | BRANCH_PKGS["580"] if p in S.pkgs]
            if bad:
                add("warn", tr("rules.drivers_card_does_not_support"), ", ".join(bad), SYNC)


class DkmsRule(Rule):
    """3. DKMS и заголовки ядра: Собран ли DKMS-модуль для текущего ядра (и есть ли заголовки)."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        uses_dkms = bool(dkms_pkg) and (dkms_pkg in S.pkgs or "equestria-nvidia-dkms" in S.pkgs)
        if uses_dkms:
            mine = [d for d in S.dkms if d[0] == "nvidia" and d[2] == S.kernel]
            if any(d[3] == "installed" for d in mine):
                add("ok", tr("rules.dkms_module_built_kernel", S.kernel), tr("rules.nvidia_modules_ready_load"))
            else:
                hp = headers_pkg(S.kernel)
                if not Path(f"/usr/lib/modules/{S.kernel}/build").exists():
                    add("fail", tr("rules.no_headers_kernel", S.kernel),
                        tr("rules.dkms_cannot_build_module_without", hp),
                        (tr("rules.install_2", hp), "pkgs", [hp]))
                else:
                    add("fail", tr("rules.dkms_module_not_built_kernel", S.kernel),
                        tr("rules.driver_installed_but_kernel_module"),
                        (tr("common.rebuild_dkms_initramfs"), "dkms", []))


class VersionMatchRule(Rule):
    """4. Версии модуль/библиотеки: Совпадают ли версии модуля ядра и пользовательских библиотек."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        uv = S.pkgver(br["utils"] if br["utils"] in S.pkgs else "nvidia-utils")
        if S.nv_version and uv:
            if S.nv_version == uv:
                add("ok", tr("rules.versions_match", uv), tr("rules.kernel_module_user_libraries_same"))
            else:
                add("fail", tr("rules.kernel_module_libraries", S.nv_version, uv),
                    tr("rules.driver_was_updated_but_kernel"))


class ModesetRule(Rule):
    """5. DRM modeset: nvidia_drm.modeset и файл nvidia_icd.json."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if g.driver == "nvidia":
            if S.modeset == "Y":
                add("ok", "nvidia_drm.modeset=1", tr("rules.wayland_prime_correct_output_games"))
            else:
                add("warn", tr("rules.nvidia_drm_modeset_off"),
                    tr("rules.wayland_hybrid_graphics_stable_output"), SYNC)
            if not Path("/usr/share/vulkan/icd.d/nvidia_icd.json").exists():
                add("fail", tr("rules.no_nvidia_icd_json_file"),
                    tr("rules.vulkan_loader_does_not_know"), SYNC)


class NvidiaVulkanRule(Rule):
    """6. Vulkan: Vulkan-загрузчик, видит ли Vulkan карту, мешающие переменные окружения."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if g.branch in ("open", "580", "470"):
            miss = [p for p in ("vulkan-icd-loader", "lib32-vulkan-icd-loader") if p not in S.pkgs
                    and (p == "vulkan-icd-loader" or S.multilib)]
            if miss:
                add("warn", tr("rules.vulkan_loader_not_installed"), ", ".join(miss) + tr("rules.without_games_will_not_see"),
                    (tr("rules.install") + " ".join(miss), "pkgs", miss))
            vk = S.vk_for(g)
            if not S.vk_tool:
                add("info", tr("rules.vulkaninfo_not_found"), tr("rules.install_vulkan_tools_then_vulkan"),
                    (tr("rules.install_vulkan_tools"), "pkgs", ["vulkan-tools"]))
            elif not vk:
                add("fail", tr("rules.vulkan_does_not_see_graphics"),
                    tr("rules.without_vulkan_games_say_dx12"), SYNC)
            else:
                api = vk.get("apiVersion", "?")
                if api_tuple(api) >= (1, 3):
                    add("ok", tr("rules.vulkan_driver", api.split()[0], vk.get('driverName', '?')),
                        tr("rules.enough_dxvk_2_x_vkd3d"))
                elif g.branch == "470":
                    add("info", f"Vulkan {api.split()[0]}", tr("rules.driver_470_limit_dx12_unavailable"))
                else:
                    add("warn", tr("rules.vulkan_below_1_3", api.split()[0]),
                        tr("rules.vkd3d_proton_needs_vulkan_1"), SYNC)
        for k in ("VK_ICD_FILENAMES", "VK_DRIVER_FILES"):
            v = S.env.get(k)
            if v and "nvidia" not in v.lower():
                add("warn", tr("rules.variable_hides_nvidia_driver", k), tr("rules.remove_from_etc_environment_environment", k, v))


class Lib32Rule(Rule):
    """7. 32-битные библиотеки: 32-битные библиотеки для Steam/Wine."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if br["lib32"]:
            if not S.multilib:
                add("warn", tr("rules.multilib_repository_not_enabled"),
                    tr("rules.without_32_bit_driver_libraries"))
            elif br["lib32"] not in S.pkgs:
                add("warn", tr("rules.no_32_bit_libraries", br['lib32']),
                    tr("rules.needed_by_steam_wine_32"), SYNC)
            else:
                add("ok", tr("rules.32_bit_driver_libraries_installed"), br["lib32"])
        elif g.branch in ("470", "390"):
            add("info", tr("rules.32_bit_libraries_not_available"), tr("rules.no_lib32_packages_exist_driver"))


class DlssRule(Rule):
    """8. DLSS / RT: Файлы DLSS (NGX) на RTX или пояснение, почему DLSS нет."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if g.rtx:
            wine = Path("/usr/lib/nvidia/wine/nvngx.dll").exists()
            so = bool(glob.glob("/usr/lib/libnvidia-ngx.so*"))
            if wine and so:
                add("ok", tr("rules.dlss_ngx_files_place"), tr("rules.libnvidia_ngx_so_nvngx_dll"))
            else:
                add("warn", tr("rules.dlss_ngx_files_not_found"),
                    tr("rules.nvidia_utils_puts_libnvidia_ngx"))
            add("info", tr("rules.make_dlss_work_proton"),
                tr("rules.required_game_actually_runs_nvidia"))
        else:
            add("info", tr("rules.dlss_rt_not_available_card"),
                tr("rules.dlss_hardware_ray_tracing_require"))


class Dx12Rule(Rule):
    """9. DX12 и особенности поколения: Поддержка DX12 у поколения карты."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if fam:
            txt = {1: tr("rules.dx12_supported_via_vkd3d_proton"), 2: tr("rules.dx12_limited"), 0: tr("rules.dx12_not_available")}[fam["dx12"]]
            add("ok" if fam["dx12"] == 1 and g.driver == "nvidia" else "info", "DX12 (VKD3D-Proton)",
                txt + (" " + fam["note"] if fam["note"] else ""))


class HybridGraphicsRule(Rule):
    """10. Гибридная графика: Гибридная графика: PRIME, nvidia-prime, глобальный рендер на NVIDIA."""

    def run(self, ctx: "CheckContext") -> None:
        g, S, fam, br, dkms_pkg, add = ctx.unpack()
        if any(o.vendor != "nvidia" for o in S.gpus):
            add("info", tr("rules.hybrid_graphics_integrated_nvidia"),
                tr("rules.games_must_run_nvidia_prime"))
            if "nvidia-prime" not in S.pkgs:
                add("warn", tr("rules.nvidia_prime_not_installed"), tr("rules.needed_prime_run_running_programs"),
                    (tr("rules.install_nvidia_prime"), "pkgs", ["nvidia-prime"]))
            if S.env.get("__GLX_VENDOR_LIBRARY_NAME") == "nvidia":
                add("info", tr("rules.whole_desktop_runs_nvidia"),
                    tr("rules.glx_vendor_library_name_nvidia"))


class MesaDriverRule(Rule):
    """AMD / Intel: открытый драйвер ядра и пакеты Vulkan/Mesa."""
    vendors = ("amd", "intel")
    EXPECTED = {"amd": ("amdgpu", "vulkan-radeon"), "intel": ("i915", "vulkan-intel")}

    def run(self, ctx: CheckContext) -> None:
        g, S = ctx.g, ctx.S
        exp = self.EXPECTED[g.vendor]
        good = (exp[0], "xe") if g.vendor == "intel" else (exp[0],)
        if g.driver in good:
            ctx.add("ok", tr("rules.kernel_driver", g.driver), tr("rules.open_mesa_kernel_driver_everything"))
        else:
            _or = tr("rules.or")  # str.join у Text берёт старый текст, поэтому собираем «живую» строку
            ctx.add("warn", tr("rules.kernel_driver", g.driver or tr("common.not_loaded")), tr("rules.expected", live_i18n.Text(_or.catalog, lambda: str(_or).join(good))))
        miss = [p for p in (exp[1], "mesa") + (("lib32-" + exp[1], "lib32-mesa") if S.multilib else ()) if p not in S.pkgs]
        if miss:
            ctx.add("warn", tr("rules.vulkan_mesa_packages_missing"), ", ".join(miss),
                    (tr("rules.install") + " ".join(miss), "pkgs", miss))
        else:
            ctx.add("ok", tr("rules.vulkan_mesa_packages_installed"), exp[1])


class MesaVulkanRule(Rule):
    """Любая не-NVIDIA карта: видит ли её Vulkan и хватает ли версии для DX12."""

    def applies(self, ctx: CheckContext) -> bool:
        return ctx.g.vendor != "nvidia"

    def run(self, ctx: CheckContext) -> None:
        g, S = ctx.g, ctx.S
        vk = S.vk_for(g)
        if not S.vk_tool:
            ctx.add("info", tr("rules.vulkaninfo_not_found"), tr("rules.install_vulkan_tools_check_vulkan"),
                    (tr("rules.install_vulkan_tools"), "pkgs", ["vulkan-tools"]))
        elif vk:
            api = vk.get("apiVersion", "?")
            ok = api_tuple(api) >= (1, 3)
            ctx.add("ok" if ok else "warn", f"Vulkan {api.split()[0]}",
                    tr("rules.enough_dx12_via_vkd3d_proton") if ok else tr("rules.dx12_requires_vulkan_1_3"))
        else:
            ctx.add("warn", tr("rules.vulkan_does_not_see_graphics"), tr("rules.check_vulkan_radeon_vulkan_intel"))


RULES: tuple = (KernelDriverRule(), BranchPackagesRule(), DkmsRule(), VersionMatchRule(), ModesetRule(),
                NvidiaVulkanRule(), Lib32Rule(), DlssRule(), Dx12Rule(), HybridGraphicsRule(),
                MesaDriverRule(), MesaVulkanRule())


def checks_for(g: Gpu, S: Sys) -> list:
    ctx = CheckContext(g, S)
    for rule in RULES:
        if rule.applies(ctx):
            rule.run(ctx)
    return ctx.results
