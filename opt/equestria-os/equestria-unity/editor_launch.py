"""Start a Unity Editor for a project, with the display profile and arguments the user chose."""
import contextlib
import os
import shlex
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from unity_cli import UnityCli

RENDERERS = ("-force-vulkan", "-force-glcore")
SECRET_ARGUMENTS = ("-accessToken",)


class HubService:
    """The Editor's account services (Sign in, Asset Store, "My Assets", cloud) ask Unity Hub over a local
    socket; without an answer the Editor only says "You must install the Unity Hub". When nobody answers
    there, the launcher's own service (hub_ipc.py) is started in the background: Unity Hub is not needed.
    A running Unity Hub is left to answer by itself."""

    SOCKET = Path("/tmp/Unity-hubIPCService.sock")
    SERVICE = Path(__file__).resolve().with_name("hub_ipc.py")
    WAIT = 10.0

    def __init__(self, path=None, command=None):
        self.path = Path(path or self.SOCKET)
        self.command = command or [sys.executable, str(self.SERVICE)]

    def listening(self):
        with contextlib.closing(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)) as probe:
            try:
                probe.connect(str(self.path))
            except OSError:
                return False
        return True

    def ensure(self):
        """True when something answers on the socket, starting the launcher's service first if needed."""
        if self.listening():
            return True
        try:
            subprocess.Popen(self.command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            return False
        deadline = time.monotonic() + self.WAIT
        while time.monotonic() < deadline:
            if self.listening():
                return True
            time.sleep(0.1)
        return False


class AccountHandoff:
    """Hands the signed-in Unity account to the Editor the way Unity Hub does: an access token from the
    Unity CLI for licensing, and the Hub's socket (answered by hub_ipc.py) for everything else."""

    def __init__(self, token_source=None, hub=None):
        self.token_source = token_source
        self.hub = hub or HubService()

    def arguments(self):
        args = []
        if self.hub.ensure():
            args += ["-useHub", "-hubIPC", "-hubSessionId", str(uuid.uuid4())]
        token = (self.token_source or UnityCli.access_token)()
        if token:
            args += ["-cloudEnvironment", "production", "-accessToken", token]
        return args


def printable(args):
    """The command line for the log, with the access token hidden."""
    shown = list(args)
    for index, arg in enumerate(shown[:-1]):
        if arg in SECRET_ARGUMENTS:
            shown[index + 1] = "***"
    return shlex.join(shown)


class LaunchProfile:
    """Environment and command line for one Editor and one project. Arguments are joined in this order:
    the launcher's global ones, the Editor's, the project's."""

    def __init__(self, editor, project, settings):
        self.editor = Path(editor)
        self.project = Path(project)
        self.settings = settings
        self.profile = settings.get("editor_profiles", {}).get(str(self.editor.resolve()), {})

    def environment(self):
        env = os.environ.copy()
        if self.profile.get("x11"):
            if not env.get("DISPLAY"):
                raise ValueError("DISPLAY is unavailable (X11 / XWayland).")
            env["GDK_BACKEND"] = "x11"
            env.pop("WAYLAND_DISPLAY", None)
        return env

    def arguments(self, create=False, template=None, account=()):
        args = [str(self.editor), "-createProject" if create else "-projectPath", str(self.project)]
        if template:
            args.extend(["-cloneFromTemplate", str(template)])
        args.extend(account)
        renderer = self.settings.get("renderer")
        if renderer in RENDERERS:
            args.append(renderer)
        project_args = self.settings.get("project_arguments", {}).get(str(self.project.resolve()), "")
        for extra in (self.settings.get("arguments", ""), self.profile.get("arguments", ""), project_args):
            args.extend(shlex.split(extra))
        return args


def launch(editor, project, settings, *, create=False, template=None, account=None):
    profile = LaunchProfile(editor, project, settings)
    env = profile.environment()
    args = profile.arguments(create, template, (account or AccountHandoff()).arguments())
    project = Path(project)
    if create:
        project.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(args, env=env, cwd=project.parent if create else project, start_new_session=True)
