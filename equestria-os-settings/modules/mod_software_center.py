"""Software Center — embeds the real equestria-os-software-center UI."""

from embedded_module import EmbeddedAppModule


class SoftwareCenterModule(EmbeddedAppModule):
    module_id = "mod_software_center"
    display_name_key = "module.software_center.name"
    description_key = "module.software_center.desc"
    category = "software"
    icon = "🏪"
    sort_order = 10
    required_binary = "/usr/bin/equestria-os-software-center"
    package_name = "equestria-os-software-center"

    lib_dir = "/usr/lib/equestria-os-software-center"
    main_file = "main.py"
    main_class = "main_app"
