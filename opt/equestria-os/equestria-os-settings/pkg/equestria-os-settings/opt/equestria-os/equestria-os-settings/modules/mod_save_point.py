"""Save Point — embeds the real equestria-os-save-point UI."""

from embedded_module import EmbeddedAppModule


class SavePointModule(EmbeddedAppModule):
    module_id = "mod_save_point"
    display_name_key = "module.save_point.name"
    description_key = "module.save_point.desc"
    category = "system"
    icon = "✨"
    sort_order = 50
    required_binary = "/usr/bin/equestria-os-save-point"
    package_name = "equestria-os-save-point"

    lib_dir = "/opt/equestria-os/equestria-os-save-point"
    main_file = "main.py"
    main_class = "main_app"
