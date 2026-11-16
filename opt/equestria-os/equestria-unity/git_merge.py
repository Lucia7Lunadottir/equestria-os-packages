"""Resolving merge conflicts, one file at a time. Synchronous: the Git panel runs these off the interface thread.

Nothing here guesses: a file changes only when the user picks a side, or when Unity's own merge tool
(UnityYAMLMerge) reports a clean merge of a scene or prefab — otherwise the conflict is left as it was."""
import shutil
import subprocess
import tempfile
from pathlib import Path

from git_info import git_environment

# Unity's text-serialized assets that UnityYAMLMerge understands.
UNITY_YAML = (".unity", ".prefab", ".asset", ".mat", ".anim", ".controller", ".overridecontroller",
              ".physicmaterial", ".lighting", ".playable", ".mask", ".preset", ".spriteatlas", ".terrainlayer")
MARKERS = ("<<<<<<< ", ">>>>>>> ")
OURS_DELETED = ("DU", "DD")      # our side deleted the file
THEIRS_DELETED = ("UD", "DD")    # their side deleted the file


class GitStepError(Exception):
    """A step Git refused; the message is Git's own output."""


def git(root, *args, check=True, timeout=60):
    env = git_environment()
    env["GIT_LITERAL_PATHSPECS"] = "1"   # file names are names, never patterns
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitStepError(str(error)) from error
    if check and result.returncode != 0:
        raise GitStepError((result.stderr or result.stdout).decode(errors="replace").strip())
    return result


def take(root, change, side):
    """Resolve a conflict by keeping one side whole: "ours" (this branch) or "theirs" (the one merged in).
    When the chosen side deleted the file, the file is deleted."""
    deleted = change.code in (OURS_DELETED if side == "ours" else THEIRS_DELETED)
    if deleted:
        git(root, "rm", "--quiet", "--", change.path)
    else:
        git(root, "checkout", f"--{side}", "--", change.path)
        git(root, "add", "--", change.path)


def has_markers(root, path):
    """Conflict markers left in a text file (the user marked it resolved too early?)."""
    try:
        with open(Path(root) / path, "rb") as file:
            text = file.read(8 * 1024 * 1024).decode(errors="ignore")
    except OSError:
        return False
    return any(line.startswith(MARKERS) for line in text.splitlines())


def mark_resolved(root, change):
    """The user fixed the file by hand: record it as resolved (a file they deleted stays deleted)."""
    if (Path(root) / change.path).exists():
        git(root, "add", "--", change.path)
    else:
        git(root, "rm", "--quiet", "--cached", "--", change.path)


def is_unity_yaml(path):
    return Path(path).suffix.casefold() in UNITY_YAML


def unity_merge_tool(editor):
    """UnityYAMLMerge shipped with an Editor executable, or None."""
    tool = Path(editor).parent / "Data/Tools/UnityYAMLMerge"
    return tool if tool.is_file() else None


def stage(root, number, path):
    """One side of a conflict as Git keeps it: 1 the common base, 2 ours, 3 theirs (None if that side has none)."""
    result = git(root, "show", f":{number}:{path}", check=False)
    return result.stdout if result.returncode == 0 else None


def smart_merge(root, change, tool):
    """Merge a scene or prefab with UnityYAMLMerge, which understands Unity objects rather than text lines.
    Writes the file and marks it resolved only when the tool reports a clean merge; returns whether it did."""
    if change.code != "UU" or not is_unity_yaml(change.path) or tool is None:
        return False
    base, ours, theirs = (stage(root, number, change.path) for number in (1, 2, 3))
    if base is None or ours is None or theirs is None or not ours.lstrip().startswith(b"%YAML"):
        return False
    suffix = Path(change.path).suffix
    with tempfile.TemporaryDirectory(prefix="equestria-unity-merge-") as folder:
        folder = Path(folder)
        files = {}
        for name, data in (("base", base), ("theirs", theirs), ("ours", ours)):
            files[name] = folder / f"{name}{suffix}"
            files[name].write_bytes(data)
        merged = folder / f"merged{suffix}"
        try:
            # The order Unity documents for Git: base, remote (theirs), local (ours), result.
            result = subprocess.run([str(tool), "merge", "-p", str(files["base"]), str(files["theirs"]),
                                     str(files["ours"]), str(merged)], capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0 or not merged.is_file() or not merged.stat().st_size:
            return False
        shutil.copyfile(merged, Path(root) / change.path)
    git(root, "add", "--", change.path)
    return True


def finish_merge(root):
    """Commit the merge with Git's own message ("Merge branch …")."""
    git(root, "commit", "--no-edit")


def abort_merge(root):
    """Return to exactly the state before the merge began."""
    git(root, "merge", "--abort")
