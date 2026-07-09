"""
pacman_repo.py — Equestria OS Software Center
Read/write support for custom repository sections in /etc/pacman.conf.

Safety model — a malformed pacman.conf breaks *all* pacman operations on the
whole system, not just the one bad repo (verified: an invalid SigLevel value
or an inline "# comment" after a directive makes `pacman-conf`/`pacman` fail
to parse the entire file). This module therefore defends in depth:
  1. PacmanRepository.validate() rejects anything outside pacman's actual
     accepted grammar (repo name, SigLevel keywords) before it is ever staged.
  2. FileRepositoryStore re-validates the fully rendered document with
     pacman's own `pacman-conf` parser before any privileged write is
     attempted, so a bug in our own serializer can never reach disk unnoticed.
  3. PrivilegedWriter stages the new content next to the target file and
     replaces it with an atomic rename, so an interrupted/cancelled write can
     never leave a truncated pacman.conf behind.

Design (SOLID):
  - PacmanRepository is a plain data model for one custom [section] entry.
  - PacmanConfDocument parses pacman.conf into an ordered list of blocks and
    serializes itself back to text, preserving everything it does not manage
    (official repos, [options], comments) exactly as found on disk.
  - RepositoryStore is the abstract contract the UI depends on (DIP) so a
    future backend (e.g. a polkit/DBus helper) can replace direct file
    access without any UI changes (OCP).
  - FileRepositoryStore is the concrete implementation used today; it
    delegates privileged writes to PrivilegedWriter (SRP).
"""

import os
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod

PACMAN_CONF_PATH = "/etc/pacman.conf"

# Sections that ship with a stock Arch/Equestria install. Anything else found
# in the file is treated as a user-managed "custom" repository.
_PROTECTED_SECTIONS = {
    "options", "core", "extra", "multilib",
    "core-testing", "extra-testing", "multilib-testing",
    "community", "community-testing",
    "gnome-unstable", "kde-unstable",
}

# pacman's own SigLevel grammar (see pacman.conf(5)): a space-separated list
# of these keywords, each optionally prefixed with "Package:" or "Database:".
_SIGLEVEL_KEYWORDS = {"Never", "Optional", "Required", "TrustAll", "TrustedOnly"}

_SECTION_RE = re.compile(r"^\[([^\]]+)\]\s*$")
_KEY_VALUE_RE = re.compile(r"^([A-Za-z]+)\s*=\s*(.*?)\s*$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


class RepositoryError(Exception):
    """Raised when a repository could not be read, validated, or written."""


def _validate_siglevel(value: str) -> None:
    if not value:
        return  # empty = inherit from [options], always valid
    for token in value.split():
        prefix, _, bare = token.partition(":")
        if bare:
            if prefix not in ("Package", "Database"):
                raise RepositoryError(f"Invalid SigLevel prefix: {prefix!r}")
        else:
            bare = prefix
        if bare not in _SIGLEVEL_KEYWORDS:
            raise RepositoryError(f"Invalid SigLevel keyword: {bare!r}")


class PacmanRepository:
    """Value object describing one custom [section] entry in pacman.conf."""

    def __init__(self, name: str, servers=None, siglevel: str = "", extra_lines=None):
        self.name = name
        self.servers = list(servers or [])
        self.siglevel = siglevel
        # Directives this tool doesn't model explicitly (e.g. "Usage = ...").
        # Carried through untouched so editing a repo never silently drops
        # settings the user (or another tool) configured.
        self.extra_lines = list(extra_lines or [])

    def validate(self):
        if not self.name or not _NAME_RE.match(self.name):
            raise RepositoryError(f"Invalid repository name: {self.name!r}")
        if self.name.lower() in _PROTECTED_SECTIONS:
            raise RepositoryError(f"'{self.name}' is a protected repository name")
        if not self.servers:
            raise RepositoryError("At least one Server/Include line is required")
        for server in self.servers:
            if not server.strip() or any(c in server for c in "\n\r"):
                raise RepositoryError(f"Invalid Server/Include value: {server!r}")
        if any(c in self.siglevel for c in "\n\r#"):
            raise RepositoryError(f"Invalid SigLevel value: {self.siglevel!r}")
        _validate_siglevel(self.siglevel)

    def to_conf_lines(self):
        lines = [f"[{self.name}]"]
        if self.siglevel:
            lines.append(f"SigLevel = {self.siglevel}")
        for server in self.servers:
            directive = "Include" if server.strip().startswith("/") else "Server"
            lines.append(f"{directive} = {server}")
        lines.extend(self.extra_lines)
        return lines

    def __eq__(self, other):
        return (isinstance(other, PacmanRepository) and self.name == other.name
                and self.servers == other.servers and self.siglevel == other.siglevel)


class _RawBlock:
    """A verbatim chunk of pacman.conf that this tool leaves untouched."""

    def __init__(self, lines):
        self.lines = list(lines)

    def render(self):
        return list(self.lines)


class _CustomRepoBlock:
    """A parsed custom [section], editable via a PacmanRepository object."""

    def __init__(self, repo: PacmanRepository):
        self.repo = repo

    def render(self):
        return self.repo.to_conf_lines()


class PacmanConfDocument:
    """Parses/serializes pacman.conf, preserving everything outside custom
    repository sections exactly as found on disk. Comments placed *inside* a
    custom repository section are not preserved across an edit, since that
    section is regenerated from its structured fields."""

    def __init__(self, blocks):
        self._blocks = blocks

    @classmethod
    def parse(cls, text: str) -> "PacmanConfDocument":
        blocks = []
        raw_lines = []
        current_repo = None
        current_lines = []

        def flush_raw():
            nonlocal raw_lines
            if raw_lines:
                blocks.append(_RawBlock(raw_lines))
                raw_lines = []

        def flush_repo():
            nonlocal current_repo, current_lines
            if current_repo is not None:
                _apply_repo_lines(current_repo, current_lines)
                blocks.append(_CustomRepoBlock(current_repo))
            current_repo = None
            current_lines = []

        for line in text.splitlines():
            section_match = _SECTION_RE.match(line.strip())
            if section_match:
                flush_repo()
                name = section_match.group(1).strip()
                if name.lower() in _PROTECTED_SECTIONS:
                    raw_lines.append(line)
                else:
                    flush_raw()
                    current_repo = PacmanRepository(name)
                continue
            if current_repo is not None:
                current_lines.append(line)
            else:
                raw_lines.append(line)

        flush_repo()
        flush_raw()
        return cls(blocks)

    def repositories(self):
        return [b.repo for b in self._blocks if isinstance(b, _CustomRepoBlock)]

    def add(self, repo: PacmanRepository):
        if any(b.repo.name == repo.name for b in self._blocks if isinstance(b, _CustomRepoBlock)):
            raise RepositoryError(f"Repository '{repo.name}' already exists")
        self._blocks.append(_CustomRepoBlock(repo))

    def replace(self, old_name: str, repo: PacmanRepository):
        for i, block in enumerate(self._blocks):
            if isinstance(block, _CustomRepoBlock) and block.repo.name == old_name:
                if repo.name != old_name and any(
                    isinstance(other, _CustomRepoBlock) and other.repo.name == repo.name
                    for other in self._blocks if other is not block
                ):
                    raise RepositoryError(f"Repository '{repo.name}' already exists")
                self._blocks[i] = _CustomRepoBlock(repo)
                return
        raise RepositoryError(f"Repository '{old_name}' not found")

    def remove(self, name: str):
        before = len(self._blocks)
        self._blocks = [b for b in self._blocks
                         if not (isinstance(b, _CustomRepoBlock) and b.repo.name == name)]
        if len(self._blocks) == before:
            raise RepositoryError(f"Repository '{name}' not found")

    def render(self) -> str:
        lines = []
        for block in self._blocks:
            # Separate consecutive custom repo sections with a blank line,
            # unless the preceding raw content already ends in one.
            if isinstance(block, _CustomRepoBlock) and lines and lines[-1].strip():
                lines.append("")
            lines.extend(block.render())
        text = "\n".join(lines)
        return text if text.endswith("\n") else text + "\n"


def _apply_repo_lines(repo: PacmanRepository, lines):
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        match = _KEY_VALUE_RE.match(stripped)
        if not match:
            continue
        key, value = match.group(1).lower(), match.group(2)
        if key == "siglevel":
            repo.siglevel = value
        elif key in ("server", "include"):
            repo.servers.append(value)
        else:
            # Directive this tool has no explicit model for (e.g. "Usage").
            # Preserve verbatim so an edit never silently drops it.
            repo.extra_lines.append(stripped)


def _validate_with_pacman_conf(content: str) -> None:
    """Pre-flight check using pacman's own config parser, unprivileged.

    This is the last line of defense: even if our own parser/serializer has
    a bug we haven't thought of, we refuse to write anything pacman itself
    would reject — so we never touch /etc/pacman.conf, let alone prompt for
    root, on invalid content.
    """
    if not shutil.which("pacman-conf"):
        return
    fd, tmp_path = tempfile.mkstemp(prefix="equestria-pacman-conf-check-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        result = subprocess.run(
            ["pacman-conf", "--config", tmp_path, "--repo-list"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RepositoryError(
                "Refusing to save: resulting pacman.conf would be invalid.\n"
                + (result.stderr.strip() or "unknown parse error")
            )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


class PrivilegedWriter:
    """Writes a system file that requires root, via pkexec.

    Content is staged to a temp file, then copied to "<path>.new" and only
    swapped into place with an atomic rename — all inside one pkexec
    transaction. If authentication is cancelled or the copy fails, the live
    file is never touched; if the process is interrupted after the copy but
    before the rename, the live file is *still* untouched (rename is atomic),
    at worst leaving a harmless "<path>.new" behind.
    """

    def write(self, path: str, content: str) -> None:
        fd, tmp_path = tempfile.mkstemp(prefix="equestria-pacman-conf-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            staged_path = f"{path}.new"
            script = 'install -m 644 -o root -g root -T "$1" "$2" && mv -f "$2" "$3"'
            result = subprocess.run(
                ["pkexec", "sh", "-c", script, "_", tmp_path, staged_path, path],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RepositoryError(
                    result.stderr.strip() or "Failed to write file (authentication cancelled?)"
                )
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


class RepositoryStore(ABC):
    """Abstraction the UI depends on (DIP), independent of storage backend."""

    @abstractmethod
    def list_repositories(self) -> list:
        ...

    @abstractmethod
    def add_repository(self, repo: PacmanRepository) -> None:
        ...

    @abstractmethod
    def update_repository(self, old_name: str, repo: PacmanRepository) -> None:
        ...

    @abstractmethod
    def remove_repository(self, name: str) -> None:
        ...


class FileRepositoryStore(RepositoryStore):
    """Reads/writes custom repositories directly in /etc/pacman.conf."""

    def __init__(self, conf_path: str = PACMAN_CONF_PATH, writer: PrivilegedWriter = None):
        self._conf_path = conf_path
        self._writer = writer or PrivilegedWriter()

    def _read_document(self) -> PacmanConfDocument:
        try:
            with open(self._conf_path, encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            raise RepositoryError(f"Cannot read {self._conf_path}: {exc}")
        return PacmanConfDocument.parse(text)

    def list_repositories(self):
        return self._read_document().repositories()

    def add_repository(self, repo: PacmanRepository):
        repo.validate()
        doc = self._read_document()
        doc.add(repo)
        rendered = doc.render()
        _validate_with_pacman_conf(rendered)
        self._writer.write(self._conf_path, rendered)

    def update_repository(self, old_name: str, repo: PacmanRepository):
        repo.validate()
        doc = self._read_document()
        doc.replace(old_name, repo)
        rendered = doc.render()
        _validate_with_pacman_conf(rendered)
        self._writer.write(self._conf_path, rendered)

    def remove_repository(self, name: str):
        doc = self._read_document()
        doc.remove(name)
        rendered = doc.render()
        _validate_with_pacman_conf(rendered)
        self._writer.write(self._conf_path, rendered)
