"""What a project's Git repository looks like, read from the .git files: no git process is started,
so the whole project list can be read in one scan."""
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

REMOTE = re.compile(r'^\[remote\s+"([^"]+)"\]\s*$')
URL = re.compile(r"^\s*url\s*=\s*(\S.*?)\s*$")


def web_remote(remote):
    """Convert a normal SSH or HTTPS remote to a credential-free web URL."""
    scp = re.fullmatch(r"(?:[\w.-]+@)?([\w.-]+):([\w./-]+)", remote)
    if scp and "://" not in remote:
        host, path = scp.groups()
    else:
        url = urlsplit(remote)
        if url.scheme not in ("ssh", "https", "http") or not url.hostname:
            return ""
        host, path = url.hostname, url.path.strip("/")
        if url.scheme in ("http", "https") and url.port:
            host += f":{url.port}"
    path = path.removesuffix(".git").strip("/")
    return f"https://{host}/{path}" if "/" in path else ""


@dataclass
class Change:
    kind: str         # modified, added, deleted, renamed, untracked, conflict
    path: str         # relative to the repository root
    original: str = ""   # the old path of a renamed file

    def paths(self):
        """Everything a commit of this change has to include (both sides of a rename)."""
        return [self.path, self.original] if self.original else [self.path]


@dataclass
class GitStatus:
    """What `git status` knows without asking the server: changes here, commits ahead of / behind the
    last known state of the remote branch."""
    upstream: str = ""            # e.g. origin/main; "" when the branch is not connected to a remote one
    ahead: int = 0                # commits made here and not sent yet
    behind: int = 0               # commits on the server (as of the last fetch) not received yet
    changes: list = field(default_factory=list)


@dataclass
class GitInfo:
    root: Path        # the repository's top folder (the project can be inside it)
    branch: str       # current branch, or a short commit when detached
    remote: str       # URL of origin (or the first remote), "" without one
    status: GitStatus | None = None

    @property
    def web(self):
        return web_remote(self.remote) if self.remote else ""

    @property
    def host(self):
        return (urlsplit(self.web).hostname or "") if self.web else ""

    @property
    def reviews(self):
        """Pull requests on GitHub, merge requests on GitLab; "" elsewhere."""
        return {"github.com": self.web + "/pulls", "gitlab.com": self.web + "/-/merge_requests"}.get(self.host, "")


def git_dir(folder):
    """The .git folder of the repository that contains `folder`, and the repository's root."""
    for root in (folder, *folder.parents):
        dot = root / ".git"
        if dot.is_dir():
            return dot, root
        if dot.is_file():  # a worktree or a submodule: "gitdir: <path>"
            try:
                text = dot.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                return None, None
            if text.startswith("gitdir:"):
                target = Path(text[7:].strip())
                return (target if target.is_absolute() else (root / target).resolve()), root
            return None, None
    return None, None


def read_git(folder):
    """GitInfo for the repository around `folder`, or None when it is not in one."""
    folder = Path(folder).absolute()
    dot, root = git_dir(folder)
    if dot is None:
        return None
    try:
        head = (dot / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    branch = head[16:] if head.startswith("ref: refs/heads/") else head[:7]
    common = dot
    commondir = dot / "commondir"   # worktrees keep their config in the main repository
    if commondir.is_file():
        try:
            common = (dot / commondir.read_text(encoding="utf-8").strip()).resolve()
        except (OSError, UnicodeError):
            pass
    remotes = {}
    current = None
    try:
        lines = (common / "config").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        lines = []
    for line in lines:
        section = REMOTE.match(line.strip())
        if section:
            current = section.group(1)
        elif line.strip().startswith("["):
            current = None
        elif current:
            url = URL.match(line)
            if url:
                remotes.setdefault(current, url.group(1))
    remote = remotes.get("origin") or next(iter(remotes.values()), "")
    return GitInfo(root, branch, remote)


KINDS = {"M": "modified", "T": "modified", "A": "added", "D": "deleted", "R": "renamed", "C": "added"}


def git_environment():
    env = dict(os.environ)
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", LC_ALL="C")  # reading must not lock or ask
    return env


def read_status(root, timeout=10):
    """GitStatus of a repository, or None when git is missing, the folder is broken or git takes too long."""
    try:
        result = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v2", "--branch", "-z",
                                 "--untracked-files=normal"], capture_output=True, timeout=timeout,
                                env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    status = GitStatus()
    records = result.stdout.decode(errors="replace").split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if record.startswith("# branch.upstream "):
            status.upstream = record[18:]
        elif record.startswith("# branch.ab "):
            ahead, behind = record[12:].split()
            status.ahead, status.behind = int(ahead.lstrip("+")), int(behind.lstrip("-"))
        elif record.startswith("1 "):
            parts = record.split(" ", 8)
            status.changes.append(Change(change_kind(parts[1]), parts[8]))
        elif record.startswith("2 "):
            parts = record.split(" ", 9)
            original = records[index] if index < len(records) else ""
            status.changes.append(Change("renamed", parts[9], original))
            index += 1  # the original path was its own record
        elif record.startswith("u "):
            status.changes.append(Change("conflict", record.split(" ", 10)[10]))
        elif record.startswith("? "):
            status.changes.append(Change("untracked", record[2:]))
    return status


def change_kind(xy):
    """XY of porcelain v2: index and work tree state; the work tree wins when both changed."""
    for letter in (xy[1], xy[0]):
        if letter in KINDS:
            return KINDS[letter]
    return "modified"


def read_git_with_status(folder, cache=None):
    """read_git() plus GitStatus; projects in one repository share one `git status` through `cache`."""
    info = read_git(folder)
    if info is not None:
        cache = {} if cache is None else cache
        if info.root not in cache:
            cache[info.root] = read_status(info.root)
        info.status = cache[info.root]
    return info


def read_branches(root, timeout=10):
    """Local branch names, the current one included."""
    try:
        result = subprocess.run(["git", "-C", str(root), "for-each-ref", "--format=%(refname:short)", "refs/heads"],
                                capture_output=True, timeout=timeout, env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return []
    return sorted(line for line in result.stdout.decode(errors="replace").splitlines() if line)
