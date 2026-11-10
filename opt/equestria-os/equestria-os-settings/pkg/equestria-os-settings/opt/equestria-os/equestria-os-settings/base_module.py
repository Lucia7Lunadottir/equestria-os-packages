import shutil
from abc import ABC, abstractmethod
from PyQt6.QtWidgets import QWidget


class BaseModule(ABC):
    """Base class for all equestria-os-settings modules.

    To add a new module, create a file modules/mod_<name>.py with exactly one
    class inheriting BaseModule. The main window auto-discovers it at startup.
    """

    # --- Identity (set as class-level attributes in subclasses) ---
    module_id: str = ""           # unique key, e.g. "mod_auto_update"
    display_name_key: str = ""    # localization key
    description_key: str = ""     # localization key for subtitle
    category: str = "system"      # "system" | "software" | "appearance"
    icon: str = "⚙"              # unicode emoji shown in sidebar
    sort_order: int = 99          # order within category (lower = higher up)
    required_binary: str = ""     # e.g. "/usr/bin/pg-update"; "" = always available
    package_name: str = ""        # e.g. "equestria-os-disk-manager" for install hint

    def __init__(self, t_func, base_path: str):
        """
        t_func: callable(key: str) -> str  — the global t() from SettingsWindow
        base_path: absolute install path of equestria-os-settings
        """
        self.t = t_func
        self.base_path = base_path
        self._widget: QWidget | None = None

    # --- Lifecycle ---

    @abstractmethod
    def build_widget(self) -> QWidget:
        """Build and return the content widget. Called once, result is cached."""

    def get_widget(self) -> QWidget:
        """Return cached widget, building it on first call."""
        if self._widget is None:
            self._widget = self.build_widget()
        return self._widget

    def on_shown(self) -> None:
        """Called every time this module becomes visible. Use to refresh state."""

    def on_hidden(self) -> None:
        """Called when user navigates away. Use to save pending state."""

    def apply_language(self) -> None:
        """Called when the user changes language. Re-translate widget text."""

    def is_available(self) -> bool:
        """Returns True if the required binary is installed."""
        if not self.required_binary:
            return True
        return shutil.which(self.required_binary) is not None

    # --- Helpers ---

    def launch_app(self, binary: str) -> None:
        """Launch an external app non-blocking."""
        import subprocess
        subprocess.Popen([binary], start_new_session=True)

    def launch_in_terminal(self, cmd: list) -> None:
        """Run a command in the user's terminal emulator."""
        import subprocess
        for term_args in [
            ["konsole", "-e"],
            ["xterm", "-e"],
            ["gnome-terminal", "--"],
        ]:
            if shutil.which(term_args[0]):
                subprocess.Popen(term_args + cmd, start_new_session=True)
                return
