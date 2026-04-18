"""Disk Manager — embeds the real equestria-os-disk-manager UI."""

from embedded_module import EmbeddedAppModule


class DiskManagerModule(EmbeddedAppModule):
    module_id = "mod_disk_manager"
    display_name_key = "module.disk.name"
    description_key = "module.disk.desc"
    category = "system"
    icon = "💾"
    sort_order = 40
    required_binary = "/usr/bin/equestria-disk-manager"
    package_name = "equestria-os-disk-manager"

    lib_dir = "/usr/lib/equestria-os-disk-manager"
    main_file = "disk_app.py"
    main_class = "DiskManagerApp"
