class EssentialData:
    def __init__(self, pkg, display, cat, desc):
        self.package_name = pkg
        self.display_name = display
        self.category_key = cat.strip()
        self.desc_key = desc
        self.is_selected = False
        self.is_installed = False


class StoreData:
    def __init__(self, name, version, desc, source,
                 source_type="pacman", app_id=None,
                 icon_url=None, screenshot_urls=None):
        self.name = name
        self.version = version
        self.desc = desc
        self.source = source
        self.category = "Software"
        self.status = "available"
        self.source_type = source_type   # "pacman" | "aur" | "flatpak"
        self.app_id = app_id             # Flatpak app ID
        self.icon_url = icon_url
        self.screenshot_urls = screenshot_urls or []
        self.all_versions = []           # all known versions (newest first)
        self.num_votes = 0               # AUR NumVotes
