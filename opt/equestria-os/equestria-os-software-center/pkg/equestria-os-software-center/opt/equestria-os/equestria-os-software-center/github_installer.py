"""Установка программ из GitHub Releases как НАСТОЯЩИХ pacman-пакетов.

Релизный архив скачивается и проверяется по SHA-256, из него на лету
собирается локальный пакет (makepkg, без root) и ставится через
`pacman -U`. Поэтому программа попадает в базу pacman: видна в
`pacman -Q`, удаляется `pacman -Rns`, проверяется `pacman -Qkk`, а менеджер
пакетов Equestria OS показывает и удаляет её как любой другой пакет.

Модуль работает и как библиотека (GithubAppRegistry — для main.py), и как
CLI: центр запускает его в панели установки, и весь вывод идёт в панель.

    python3 github_installer.py install artcraft-launcher
    python3 github_installer.py uninstall artcraft-launcher
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
from dataclasses import dataclass, field

PREFIX_IN_CSV = "github:"          # CSV: PackageName = "github:<key>"
_API = "https://api.github.com/repos/{repo}/releases/latest"
_TIMEOUT = 60


@dataclass(frozen=True)
class GithubApp:
    """Описание программы: откуда брать релиз и как оформить пакет."""
    key: str                    # имя пакета pacman и имя после "github:" в CSV
    repo: str                   # "владелец/репозиторий"
    asset_suffix: str           # окончание файла релиза, напр. "-linux-x86_64.tar.gz"
    pkgdesc: str
    url: str
    licenses: tuple = ()
    depends: tuple = ()
    checksums_asset: str = "SHA256SUMS.txt"
    # Каталоги архива, которые кладутся в /usr (остальное игнорируется).
    install_dirs: tuple = ("bin", "share")


APPS = {
    app.key: app for app in (
        GithubApp(
            key="artcraft-launcher",
            repo="storytold/craft-launcher",
            asset_suffix="-linux-x86_64.tar.gz",
            pkgdesc="ArtCraft launcher: install and run the ArtCraft app suite",
            url="https://getartcraft.com/apps",
            licenses=("MIT", "Apache-2.0"),
            depends=("glibc", "gcc-libs", "hicolor-icon-theme"),
        ),
    )
}


@dataclass
class Release:
    tag: str
    assets: dict = field(default_factory=dict)   # имя файла -> URL


class ReleaseClient:
    """Тонкая обёртка над GitHub API."""

    def latest(self, repo):
        req = urllib.request.Request(
            _API.format(repo=repo), headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.load(r)
        return Release(data["tag_name"],
                       {a["name"]: a["browser_download_url"] for a in data.get("assets", [])})

    def read_text(self, url):
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")


class PkgbuildWriter:
    """Генерирует PKGBUILD для релизного архива."""

    @staticmethod
    def pkgver(tag):
        return tag.lstrip("vV").replace("-", "_")

    def render(self, app, release, asset, sha256):
        ver = self.pkgver(release.tag)
        archive_dir = asset[:-len(".tar.gz")] if asset.endswith(".tar.gz") else asset
        dirs = " ".join(app.install_dirs)
        q = lambda items: " ".join(f"'{i}'" for i in items)
        return textwrap.dedent(f"""\
            # Сгенерировано центром приложений Equestria OS из GitHub Releases.
            pkgname={app.key}
            pkgver={ver}
            pkgrel=1
            pkgdesc='{app.pkgdesc}'
            arch=('x86_64')
            url='{app.url}'
            license=({q(app.licenses)})
            depends=({q(app.depends)})
            options=('!strip')
            source=('{release.assets[asset]}')
            sha256sums=('{sha256}')

            package() {{
                cd '{archive_dir}'
                install -d "$pkgdir/usr"
                for d in {dirs}; do
                    [ -d "$d" ] && cp -a "$d" "$pkgdir/usr/"
                done
                find "$pkgdir/usr" -type d -exec chmod 755 {{}} +
                find "$pkgdir/usr/share" -type f -exec chmod 644 {{}} +
                for f in share/doc/{app.key}/LICENSE*; do
                    [ -f "$f" ] && install -Dm644 "$f" "$pkgdir/usr/share/licenses/{app.key}/$(basename "$f")"
                done
                return 0
            }}
            """)


class GithubAppInstaller:
    def __init__(self, client=None, writer=None):
        self.client = client or ReleaseClient()
        self.writer = writer or PkgbuildWriter()

    def install(self, app):
        print(f"==> {app.key}: запрашиваю последний релиз {app.repo}...", flush=True)
        release = self.client.latest(app.repo)
        asset = next((n for n in release.assets if n.endswith(app.asset_suffix)), None)
        if not asset:
            raise RuntimeError(f"в релизе {release.tag} нет файла '*{app.asset_suffix}'")
        sha256 = self._expected_sha256(app, release, asset)
        print(f"==> Найден {asset} ({release.tag}), SHA-256 {sha256[:12]}...", flush=True)

        with tempfile.TemporaryDirectory(prefix="equestria-gh-") as tmp:
            with open(os.path.join(tmp, "PKGBUILD"), "w", encoding="utf-8") as f:
                f.write(self.writer.render(app, release, asset, sha256))
            print("==> Собираю пакет (makepkg скачает архив и сверит контрольную сумму)...",
                  flush=True)
            self._run(["makepkg", "-f", "--noconfirm", "--nocolor"], cwd=tmp,
                      env={**os.environ, "PKGDEST": tmp})
            pkgs = [n for n in os.listdir(tmp) if n.endswith(".pkg.tar.zst")]
            if not pkgs:
                raise RuntimeError("makepkg не создал пакет")
            print("==> Устанавливаю в систему (pacman -U)...", flush=True)
            self._run(["pkexec", "pacman", "-U", "--noconfirm"]
                      + [os.path.join(tmp, p) for p in pkgs])
        print(f"==> Готово: {app.key} {release.tag}", flush=True)

    def uninstall(self, app):
        self._run(["pkexec", "pacman", "-Rns", "--noconfirm", app.key])

    def _expected_sha256(self, app, release, asset):
        if app.checksums_asset not in release.assets:
            raise RuntimeError(f"в релизе нет {app.checksums_asset} — не могу проверить файл")
        text = self.client.read_text(release.assets[app.checksums_asset])
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1].lstrip("*") == asset:
                return parts[0].lower()
        raise RuntimeError(f"{asset} не найден в {app.checksums_asset}")

    @staticmethod
    def _run(cmd, **kw):
        if subprocess.run(cmd, **kw).returncode != 0:
            raise RuntimeError(f"команда завершилась с ошибкой: {' '.join(cmd[:3])}")


class GithubAppRegistry:
    """Фасад для main.py: что из CSV относится к GitHub и как это узнаётся."""

    @staticmethod
    def owns(package_name):
        return package_name.startswith(PREFIX_IN_CSV)

    @staticmethod
    def key_of(package_name):
        return package_name[len(PREFIX_IN_CSV):]

    def is_installed(self, package_name, installed_packages):
        # Это обычный пакет pacman — «установлено» ровно как у остальных.
        return self.key_of(package_name) in installed_packages


def main(argv):
    if len(argv) < 3 or argv[1] not in ("install", "uninstall"):
        print(__doc__)
        return 2
    installer = GithubAppInstaller()
    failed = False
    for key in argv[2:]:
        app = APPS.get(key)
        try:
            if not app:
                raise RuntimeError("неизвестная программа")
            getattr(installer, argv[1])(app)
        except Exception as e:          # CLI: любая ошибка -> строка в панели + код 1
            print(f"ОШИБКА [{key}]: {e}", flush=True)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
