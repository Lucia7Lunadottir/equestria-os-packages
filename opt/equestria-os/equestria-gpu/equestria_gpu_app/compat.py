"""Compatibility exports for existing embedded consumers; new code imports concrete modules."""
from importlib import import_module

_EXPORTS = {'BRANCHES': 'models', 'BRANCH_GPUS': 'models', 'BRANCH_PKGS': 'models', 'BranchPackagesRule': 'rules', 'COMPAT': 'commands', 'CONFIG': 'paths', 'Check': 'rules', 'CheckContext': 'rules', 'DEFAULT_THEME': 'style', 'DRIVER_CACHE': 'probes', 'DkmsRule': 'rules', 'DlssRule': 'rules', 'Dx12Rule': 'rules', 'EXTRA_PKGS': 'models', 'FAMILIES': 'models', 'Gpu': 'models', 'GpuPage': 'gpu_page', 'GpuPanel': 'panel', 'HybridGraphicsRule': 'rules', 'KEYS': 'style', 'KernelDriverRule': 'rules', 'LVL_ORDER': 'rules', 'Lib32Rule': 'rules', 'MainWindow': 'window', 'MesaDriverRule': 'rules', 'MesaVulkanRule': 'rules', 'ModesetRule': 'rules', 'NvidiaVulkanRule': 'rules', 'QSS': 'style', 'RULES': 'rules', 'Rule': 'rules', 'RunDialog': 'run_dialog', 'SYNC': 'rules', 'Sys': 'models', 'THEME': 'style', 'THEMES': 'style', 'VENDORS': 'probes', 'VENDOR_LABEL': 'probes', 'VersionMatchRule': 'rules', 'WHY': 'models', 'api_tuple': 'rules', 'apply_theme': 'style', 'branch_status': 'commands', 'build_branch_cmd': 'commands', 'build_cmd': 'commands', 'cached_pkg': 'probes', 'capabilities': 'descriptions', 'card': 'widgets', 'catalog': 'localization', 'checks_for': 'rules', 'clean_line': 'widgets', 'compat': 'commands', 'dot_icon': 'widgets', 'foreign_pkgs': 'models', 'headers_pkg': 'rules', 'launch_options': 'descriptions', 'live_i18n': 'localization', 'lvl_color': 'widgets', 'lvl_label': 'widgets', 'main': 'app', 'nv_family': 'models', 'overview_rows': 'descriptions', 'probe_avail': 'probes', 'probe_env': 'probes', 'probe_gpus': 'probes', 'probe_smi': 'probes', 'probe_system': 'probes', 'probe_vulkan': 'probes', 'read': 'probes', 'sh': 'probes', 'tips_for': 'descriptions', 'tr': 'localization'}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"equestria_gpu_app.{module}"), name)
