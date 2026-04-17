"""Services Manager — embeds the real equestria-os-services-manager UI."""

from embedded_module import EmbeddedAppModule


class ServicesModule(EmbeddedAppModule):
    module_id = "mod_services"
    display_name_key = "module.services.name"
    description_key = "module.services.desc"
    category = "system"
    icon = "⚙"
    sort_order = 30
    required_binary = "/usr/bin/equestria-os-services-manager"
    package_name = "equestria-os-services-manager"

    lib_dir = "/usr/lib/equestria-os-services-manager"
    main_file = "main.py"
    main_class = "ServicesApp"
