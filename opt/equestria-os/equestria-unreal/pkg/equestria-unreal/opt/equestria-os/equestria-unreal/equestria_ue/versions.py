from __future__ import annotations

import os
import re
import shutil
import subprocess

from equestria_ue.kit import tr


REPO = {"ssh": "git@github.com:EpicGames/UnrealEngine.git", "https": "https://github.com/EpicGames/UnrealEngine.git"}
GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"}
STATIC_VERSIONS = [(5, 8, 0), (5, 7, 4), (5, 7, 0), (5, 6, 1), (5, 5, 4), (5, 4, 4), (5, 3, 2), (5, 2, 1), (5, 1, 1), (5, 0, 3),
                   (4, 27, 2), (4, 26, 2), (4, 25, 4), (4, 24, 3)]
TAG_RX = re.compile(r"refs/tags/(\d+)\.(\d+)\.(\d+)-release\s*$", re.M)
DEPS = ["git", "make", "gcc", "cmake", "python", "unzip", "dos2unix", "sdl2", "libxcursor", "libxi", "libxrandr",
        "libxkbcommon", "nss", "alsa-lib", "libpulse", "vulkan-icd-loader", "mesa", "icu", "openssl", "zlib", "curl"]


def sh(cmd: list, timeout: int = 15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def git_env() -> dict:
    env = os.environ.copy()
    env.update(GIT_ENV)
    return env


def fetch_tags(access: str):
    """(список версий | None, текст ошибки)."""
    try:
        r = subprocess.run(["git", "ls-remote", "--tags", "--refs", REPO[access], "refs/tags/*-release"],
                           capture_output=True, text=True, timeout=90, env=git_env())
    except Exception as ex:
        return None, str(ex)
    if r.returncode != 0:
        lines = [x for x in r.stderr.strip().splitlines() if x.strip()]
        return None, lines[-1] if lines else tr("git ls-remote завершился с ошибкой")
    vs = sorted({tuple(int(x) for x in m.groups()) for m in TAG_RX.finditer(r.stdout)}, reverse=True)
    return (vs or None), ("" if vs else tr("В репозитории не найдено релизных тегов"))


def explain_git_error(err: str) -> str:
    e = err.lower()
    if "permission denied" in e or "publickey" in e:
        return tr("SSH-ключ не принят GitHub. Добавьте публичный ключ (~/.ssh/id_ed25519.pub) в GitHub → Settings → "
                  "SSH keys, либо переключитесь на HTTPS в настройках. Ключ с паролем должен быть загружен в ssh-agent.")
    if "not found" in e or "could not read" in e or "404" in e:
        return tr("Ключ рабочий, но у аккаунта нет доступа к репозиторию Epic: свяжите GitHub с Epic-аккаунтом и "
                  "примите письмо-приглашение в организацию EpicGames. Или скачайте готовую сборку — это не требует GitHub.")
    if "could not resolve" in e or "timed out" in e or "unable to access" in e:
        return tr("Нет связи с github.com — проверьте интернет.")
    return err

def latest_patch(versions: list, ver: tuple):
    c = [v for v in versions if v[:2] == ver[:2]]
    return max(c, default=None)


def missing_deps(ue4: bool) -> list:
    if not shutil.which("pacman"):
        return []
    have = set(sh(["pacman", "-Qq"], 20).split())
    return [p for p in DEPS + (["mono"] if ue4 else []) if p not in have]


def vstr(v: tuple) -> str:
    return ".".join(map(str, v))

PREBUILT_SEED = {(5, 8, i) for i in range(5)} | {(5, 7, i) for i in range(5)}
PREBUILT_SIZE = 37.08e9
