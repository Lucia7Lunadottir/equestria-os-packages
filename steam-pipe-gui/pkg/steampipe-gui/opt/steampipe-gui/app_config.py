import os
import json
from dataclasses import dataclass, asdict

CONFIG_DIR = os.path.expanduser("~/.config/SteamPipeGUI")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

@dataclass
class AppConfig:
    last_username: str = ""
    sdk_folder: str = ""
    steamcmd_path: str = ""
    default_content_path: str = ""
    last_appid: str = ""
    last_branch: str = "default"
    set_live_after_upload: bool = False
    log_max_lines: int = 500

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(asdict(self), f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    @classmethod
    def load(cls) -> 'AppConfig':
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception as e:
                print(f"Failed to load config: {e}")
        return cls()
