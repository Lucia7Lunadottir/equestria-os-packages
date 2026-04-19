"""Mirror Manager — embeds the real pg-rankmirrors UI."""

from embedded_module import EmbeddedAppModule


class MirrorsModule(EmbeddedAppModule):
    module_id = "mod_mirrors"
    display_name_key = "module.mirrors.name"
    description_key = "module.mirrors.desc"
    category = "system"
    icon = "🌐"
    sort_order = 20
    required_binary = "/usr/bin/pg-rankmirrors"
    package_name = "pg-rankmirrors"

    lib_dir = "/usr/lib/pg-rankmirrors"
    main_file = "main.py"
    main_class = "main_app"
