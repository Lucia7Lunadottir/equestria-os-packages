"""Tutorial — embeds the real equestria-os-tutorial UI."""

from embedded_module import EmbeddedAppModule


class TutorialModule(EmbeddedAppModule):
    module_id = "mod_tutorial"
    display_name_key = "module.tutorial.name"
    description_key = "module.tutorial.desc"
    category = "appearance"
    icon = "📖"
    sort_order = 30
    required_binary = "/usr/bin/equestria-os-tutorial"
    package_name = "equestria-os-tutorial"

    lib_dir = "/usr/lib/equestria-os-tutorial"
    main_file = "main.py"
    main_class = "TutorialApp"
