"""Swap Manager — embeds equestria-os-swap-manager."""

from embedded_module import EmbeddedAppModule


class SwapManagerModule(EmbeddedAppModule):
    module_id        = "mod_swap_manager"
    display_name_key = "module.swap_manager.name"
    description_key  = "module.swap_manager.desc"
    category         = "system"
    icon             = "💾"
    sort_order       = 35
    required_binary  = "/usr/bin/equestria-swap-manager"
    package_name     = "equestria-os-swap-manager"

    lib_dir    = "/opt/equestria-os/equestria-os-swap-manager"
    main_file  = "swap_app.py"
    main_class = "SwapManagerApp"
