"""Start a Unity Editor for a project, with the display profile and arguments the user chose."""
import os
import shlex
import subprocess
from pathlib import Path

RENDERERS = ("-force-vulkan", "-force-glcore")


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

    def arguments(self, create=False, template=None):
        args = [str(self.editor), "-createProject" if create else "-projectPath", str(self.project)]
        if template:
            args.extend(["-cloneFromTemplate", str(template)])
        renderer = self.settings.get("renderer")
        if renderer in RENDERERS:
            args.append(renderer)
        project_args = self.settings.get("project_arguments", {}).get(str(self.project.resolve()), "")
        for extra in (self.settings.get("arguments", ""), self.profile.get("arguments", ""), project_args):
            args.extend(shlex.split(extra))
        return args


def launch(editor, project, settings, *, create=False, template=None):
    profile = LaunchProfile(editor, project, settings)
    env = profile.environment()
    args = profile.arguments(create, template)
    project = Path(project)
    if create:
        project.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(args, env=env, cwd=project.parent if create else project, start_new_session=True)
