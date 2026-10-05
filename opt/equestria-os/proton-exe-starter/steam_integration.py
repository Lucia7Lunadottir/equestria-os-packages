"""
Steam-интеграция: узнаёт, что запускаемый .exe — игра из Steam, и готовит
окружение так, чтобы steam_api64.dll нашла работающий клиент Steam.

Без этого игра с Steamworks (DMC5 и т.п.) запускается как «чужая» программа
в отдельном префиксе: Proton не знает ни AppID, ни где лежит Steam, мост
lsteamclient не поднимается, и SteamAPI_Init падает ("Steam must be running").
"""
import os
import re

_INSTALLDIR_RE = re.compile(r'"installdir"\s+"([^"]*)"', re.IGNORECASE)
_MANIFEST_RE = re.compile(r"^appmanifest_(\d+)\.acf$")


class SteamGame:
    """Игра из Steam-библиотеки: AppID, папка установки и сама библиотека."""

    def __init__(self, app_id, install_dir, library_path):
        self.app_id = app_id
        self.install_dir = install_dir
        self.library_path = library_path

    @classmethod
    def from_exe(cls, exe_path):
        """SteamGame для .exe внутри <библиотека>/steamapps/common/<игра>/…, иначе None."""
        parts = os.path.abspath(exe_path).split(os.sep)
        # Берём ближайшее к файлу вхождение steamapps/common — вложенные
        # библиотеки на практике не встречаются, а так проще и однозначно.
        for i in range(len(parts) - 3, 0, -1):
            if parts[i] == "common" and parts[i - 1] == "steamapps":
                steamapps = os.sep.join(parts[:i]) or os.sep
                game_dir = parts[i + 1]
                app_id = cls._find_app_id(steamapps, game_dir)
                if app_id:
                    install = os.path.join(steamapps, "common", game_dir)
                    return cls(app_id, install, os.path.dirname(steamapps))
        return None

    @staticmethod
    def _find_app_id(steamapps, game_dir):
        try:
            names = os.listdir(steamapps)
        except OSError:
            return None
        for name in names:
            m = _MANIFEST_RE.match(name)
            if not m:
                continue
            try:
                with open(os.path.join(steamapps, name), "r", encoding="utf-8", errors="replace") as f:
                    im = _INSTALLDIR_RE.search(f.read())
            except OSError:
                continue
            if im and im.group(1) == game_dir:
                return m.group(1)
        return None


class SteamClient:
    """Установленный клиент Steam на этой машине."""

    CANDIDATES = (
        "~/.steam/steam",
        "~/.local/share/Steam",
        "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
    )

    @classmethod
    def find_root(cls):
        for c in cls.CANDIDATES:
            p = os.path.realpath(os.path.expanduser(c))
            if os.path.isdir(os.path.join(p, "steamapps")) or os.path.isdir(os.path.join(p, "ubuntu12_32")):
                return p
        return None


def apply_steam_env(env, exe_path):
    """
    Если exe_path — игра из Steam, дописывает в env переменные, по которым
    Proton/umu связывают игру с клиентом Steam. Возвращает SteamGame или None.
    GAMEID становится umu-<AppID>: umu заодно применяет свои протонфиксы для игры.
    """
    game = SteamGame.from_exe(exe_path)
    if game is None:
        return None
    env["SteamAppId"] = game.app_id
    env["SteamGameId"] = game.app_id
    env["STEAM_COMPAT_APP_ID"] = game.app_id
    env["GAMEID"] = "umu-" + game.app_id
    env["STEAM_COMPAT_INSTALL_PATH"] = game.install_dir
    env["STEAM_COMPAT_LIBRARY_PATHS"] = game.library_path
    root = SteamClient.find_root()
    if root:
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = root
    return game
