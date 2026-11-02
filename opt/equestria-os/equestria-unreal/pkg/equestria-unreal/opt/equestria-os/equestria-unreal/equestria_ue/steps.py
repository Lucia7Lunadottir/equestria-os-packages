from __future__ import annotations

import sys
from pathlib import Path

from equestria_ue.config import Config
from equestria_ue.engines import Engine
from equestria_ue.jobs import Step
from equestria_ue.kit import tr
from equestria_ue.versions import GIT_ENV, REPO, missing_deps, vstr


UNZIP_SCRIPT = r'''
import os, sys, zipfile
z = zipfile.ZipFile(sys.argv[1]); items = z.infolist(); n = max(len(items), 1)
for i, m in enumerate(items):
    path = z.extract(m, sys.argv[2])
    mode = (m.external_attr >> 16) & 0o7777
    if mode & 0o111 and os.path.isfile(path):
        os.chmod(path, mode)
    if i % 300 == 0:
        print("%s: %d%%" % (sys.argv[3], i * 100 // n), flush=True)
print("%s: 100%%" % sys.argv[3], flush=True)
'''


def build_chain(dest: str) -> list:
    return [Step(tr("Setup.sh — загрузка зависимостей движка"), ["bash", "./Setup.sh"], dest),
            Step("GenerateProjectFiles.sh", ["bash", "./GenerateProjectFiles.sh"], dest),
            Step(tr("Сборка редактора (make) — это долго"), ["make"], dest)]


def install_steps(cfg: Config, ver: tuple, dest: str) -> list:
    steps = []
    miss = missing_deps(ver[0] == 4) if cfg["deps"] else []
    if miss:
        steps.append(Step(tr("Зависимости (pacman)"), ["pkexec", "pacman", "-S", "--needed", "--noconfirm", *miss]))
    if not (Path(dest) / ".git").exists():
        steps.append(Step(tr("Загрузка исходников {} (git clone --depth 1)", vstr(ver)),
                          ["git", "clone", "--depth", "1", "--progress", "--branch", f"{vstr(ver)}-release",
                           REPO[cfg["access"]], dest], "", GIT_ENV))
    return steps + build_chain(dest)


def update_steps(cfg: Config, path: str, ver: tuple) -> list:
    tag = f"{vstr(ver)}-release"
    return [Step(tr("Загрузка {}", tag), ["git", "fetch", "--depth", "1", "origin", "tag", tag], path, GIT_ENV),
            Step(tr("Переключение на {}", tag), ["git", "checkout", "-f", f"tags/{tag}"], path)] + build_chain(path)


DOWNLOAD_SCRIPT = r'''
import os, sys, time, urllib.request
url, out, unit, speed, done_txt = sys.argv[1:6]
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
have = os.path.getsize(out) if os.path.exists(out) else 0
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **({"Range": f"bytes={have}-"} if have else {})})
r = urllib.request.urlopen(req, timeout=60)
if have and r.status != 206:
    have = 0
total = have + int(r.headers.get("Content-Length") or 0)
done, t0, last = have, time.time(), 0
with open(out, "ab" if have else "wb") as f:
    while True:
        b = r.read(1 << 20)
        if not b:
            break
        f.write(b); done += len(b)
        if time.time() - last > 1:
            last = time.time()
            sp = (done - have) / max(last - t0, 0.1) / 1e6
            pc = f"{done * 100 / total:.1f}% " if total else ""
            print(f"{pc}{done / 1e9:.2f}/{total / 1e9:.2f} {unit} · {sp:.0f} {speed}", flush=True)
print(f"100% {done_txt}", flush=True)
'''


def download_steps(url: str, zip_path: str) -> list:
    return [Step(tr("Скачивание архива (докачка поддерживается)"),
                 [sys.executable, "-c", DOWNLOAD_SCRIPT, url, zip_path, tr("ГБ"), tr("МБ/с"), tr("готово")])]


def zip_steps(zip_path: str, dest: str) -> list:
    return [Step(tr("Распаковка архива"), [sys.executable, "-c", UNZIP_SCRIPT, zip_path, dest, tr("Распаковка")])]


def project_steps(kind: str, eng: Engine, uproject: str) -> list:
    bat = f"{eng.path}/Engine/Build/BatchFiles/Linux"
    if kind == "gen":
        return [Step(tr("Генерация файлов проекта"), ["bash", f"{bat}/GenerateProjectFiles.sh", f"-project={uproject}", "-game"], eng.path)]
    name = Path(uproject).stem
    return [Step(tr("Сборка {}Editor (Development)", name),
                 ["bash", f"{bat}/Build.sh", f"{name}Editor", "Linux", "Development", f"-project={uproject}", "-progress"], eng.path)]
