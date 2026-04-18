"""Character Theme — embeds the real equestria-os-character-theme UI."""

from embedded_module import EmbeddedAppModule


class CharacterThemeModule(EmbeddedAppModule):
    module_id = "mod_character_theme"
    display_name_key = "module.character_theme.name"
    description_key = "module.character_theme.desc"
    category = "appearance"
    icon = "🎨"
    sort_order = 10
    required_binary = "/usr/bin/equestria-os-character-theme"
    package_name = "equestria-os-character-theme"

    lib_dir = "/usr/lib/equestria-os-character-theme"
    main_file = "main.py"
    main_class = "EGThemeSwitcher"
