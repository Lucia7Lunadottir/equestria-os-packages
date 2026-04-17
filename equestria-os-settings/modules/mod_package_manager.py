"""Package Manager — embeds the real equestria-os-package-manager UI."""

from embedded_module import EmbeddedAppModule


class PackageManagerModule(EmbeddedAppModule):
    module_id = "mod_package_manager"
    display_name_key = "module.packages.name"
    description_key = "module.packages.desc"
    category = "software"
    icon = "📦"
    sort_order = 20
    required_binary = "/usr/bin/equestria-os-package-manager"
    package_name = "equestria-os-package-manager"

    lib_dir = "/usr/lib/equestria-os-package-manager"
    main_file = "main.py"
    main_class = "main_app"
