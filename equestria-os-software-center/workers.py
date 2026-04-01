import os
import gzip
import json
import hashlib
import shutil
import subprocess
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.parse import quote

from PyQt6.QtCore import QThread, pyqtSignal

from models import StoreData
from utils import (
    FLATPAK_APPSTREAM, FLATPAK_ICONS_DIR, SCREENSHOT_CACHE_DIR,
    extract_appstream_text, guess_cat,
    _GENERIC_PACMAN_DESC, _GENERIC_FLATPAK_DESC,
)

_AUR_POPULAR = [
    "yay", "paru", "google-chrome", "visual-studio-code-bin",
    "spotify", "zoom", "slack-desktop", "brave-bin",
    "1password", "jetbrains-toolbox", "timeshift", "pamac-aur",
    "dbeaver", "stacer", "ventoy-bin", "balena-etcher",
    "proton-ge-custom-bin", "obs-studio-browser", "wps-office",
    "nvm", "anydesk-bin", "megasync-bin", "onlyoffice-bin",
]


class AppStoreLoader(QThread):
    """Loads all available Pacman packages with descriptions.

    Tries expac first (fast, includes real descriptions), then falls back to pacman -Sl.
    """
    finished = pyqtSignal(list)

    def run(self):
        pkgs = self._load_with_expac() or self._load_with_pacman()
        self.finished.emit(pkgs)

    def _load_with_expac(self):
        try:
            res = subprocess.run(
                ["expac", "-S", "%n\t%v\t%d\t%r"],
                capture_output=True, text=True
            )
            if res.returncode != 0 or not res.stdout.strip():
                return []
            pkgs = []
            for line in res.stdout.splitlines():
                parts = line.split('\t', 3)
                if len(parts) >= 2:
                    name = parts[0]
                    version = parts[1]
                    desc = parts[2].strip() if len(parts) > 2 else ""
                    repo = parts[3].strip() if len(parts) > 3 else "pacman"
                    d = StoreData(name, version, desc or _GENERIC_PACMAN_DESC, repo)
                    d.category = guess_cat(name)
                    pkgs.append(d)
            return pkgs
        except FileNotFoundError:
            return []

    def _load_with_pacman(self):
        pkgs = []
        try:
            res = subprocess.run(["pacman", "-Sl"], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                p = line.split()
                if len(p) >= 3:
                    d = StoreData(p[1], p[2], _GENERIC_PACMAN_DESC, p[0])
                    d.category = guess_cat(p[1])
                    pkgs.append(d)
        except Exception:
            pass
        return pkgs


class FlatpakLoader(QThread):
    """Parses the Flathub appstream.xml.gz cache into StoreData objects."""
    finished = pyqtSignal(list)

    def run(self):
        pkgs = []
        if not shutil.which("flatpak") or not os.path.exists(FLATPAK_APPSTREAM):
            self.finished.emit(pkgs)
            return
        try:
            with gzip.open(FLATPAK_APPSTREAM, 'rb') as f:
                data = f.read()
            root = ET.fromstring(data)
            media_baseurl = root.get('media_baseurl', '').rstrip('/')
            for comp in root.findall('.//component'):
                try:
                    pkg = self._parse_component(comp, media_baseurl)
                    if pkg:
                        pkgs.append(pkg)
                except Exception:
                    continue

            pkgs = self._deduplicate(pkgs)
        except Exception:
            pass
        self.finished.emit(pkgs)

    def _parse_component(self, comp, media_baseurl):
        app_id_el = comp.find('id')
        if app_id_el is None or not app_id_el.text:
            return None
        app_id = app_id_el.text

        name = self._get_name(comp) or app_id
        all_versions = self._get_versions(comp)
        version = all_versions[0] if all_versions else ""
        desc = self._get_desc(comp)
        icon_url = self._get_icon(app_id)
        screenshot_urls = self._get_screenshots(comp, media_baseurl)

        pkg = StoreData(name, version, desc or _GENERIC_FLATPAK_DESC, "Flathub",
                        source_type="flatpak", app_id=app_id,
                        icon_url=icon_url, screenshot_urls=screenshot_urls)
        pkg.all_versions = all_versions
        pkg.category = guess_cat(name)
        return pkg

    def _get_name(self, comp):
        for n_el in comp.findall('name'):
            if n_el.get('{http://www.w3.org/XML/1998/namespace}lang') is None and n_el.text:
                return n_el.text
        for n_el in comp.findall('name'):
            if n_el.text:
                return n_el.text
        return None

    def _get_versions(self, comp):
        versions = []
        releases = comp.find('releases')
        if releases is not None:
            for rel in releases.findall('release'):
                v = rel.get('version', '')
                if v and v not in versions:
                    versions.append(v)
        return versions

    def _get_desc(self, comp):
        desc_el = comp.find('description')
        if desc_el is not None:
            return extract_appstream_text(desc_el)[:200]
        return ""

    def _get_icon(self, app_id):
        icon_file = os.path.join(FLATPAK_ICONS_DIR, f"{app_id}.png")
        return icon_file if os.path.exists(icon_file) else None

    def _get_screenshots(self, comp, media_baseurl):
        urls = []
        screenshots_el = comp.find('screenshots')
        if screenshots_el is None:
            return urls
        for ss in screenshots_el.findall('screenshot')[:5]:
            best_url = None
            for img in ss.findall('image'):
                if img.get('type', '') == 'thumbnail' and img.text:
                    best_url = img.text
                    break
            if not best_url:
                for img in ss.findall('image'):
                    if img.text:
                        best_url = img.text
                        break
            if best_url:
                if media_baseurl and not best_url.startswith('http'):
                    best_url = f"{media_baseurl}/{best_url.lstrip('/')}"
                urls.append(best_url)
        return urls

    def _deduplicate(self, pkgs):
        seen = {}
        for pkg in pkgs:
            key = pkg.app_id
            if key not in seen:
                seen[key] = pkg
            else:
                ex = seen[key]
                for v in pkg.all_versions:
                    if v not in ex.all_versions:
                        ex.all_versions.append(v)
                if not ex.screenshot_urls and pkg.screenshot_urls:
                    ex.screenshot_urls = pkg.screenshot_urls
                if not ex.icon_url and pkg.icon_url:
                    ex.icon_url = pkg.icon_url
                if not ex.desc or ex.desc == _GENERIC_FLATPAK_DESC:
                    if pkg.desc and pkg.desc != _GENERIC_FLATPAK_DESC:
                        ex.desc = pkg.desc
        result = list(seen.values())
        for pkg in result:
            pkg.all_versions = sorted(set(pkg.all_versions), reverse=True)
            if pkg.all_versions:
                pkg.version = pkg.all_versions[0]
        return result


class AURSearchThread(QThread):
    """Searches AUR RPC v5 for a given query."""
    finished = pyqtSignal(list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        pkgs = []
        try:
            url = f"https://aur.archlinux.org/rpc/v5/search/{quote(self.query)}"
            req = Request(url, headers={'User-Agent': 'equestria-os-software-center/1.0'})
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            results = sorted(data.get('results', [])[:100],
                             key=lambda x: x.get('NumVotes', 0), reverse=True)
            for item in results:
                pkg = StoreData(
                    item.get('Name', ''),
                    item.get('Version', ''),
                    item.get('Description') or 'AUR package',
                    'AUR',
                    source_type='aur'
                )
                pkg.num_votes = item.get('NumVotes', 0)
                pkg.category = guess_cat(pkg.name)
                pkgs.append(pkg)
        except Exception:
            pass
        self.finished.emit(pkgs)


class AURPopularLoader(QThread):
    """Fetches metadata for a curated list of popular AUR packages."""
    finished = pyqtSignal(list)

    def run(self):
        pkgs = []
        try:
            args = "&".join(f"arg[]={name}" for name in _AUR_POPULAR)
            url = f"https://aur.archlinux.org/rpc/v5/info?{args}"
            req = Request(url, headers={'User-Agent': 'equestria-os-software-center/1.0'})
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            for item in sorted(data.get('results', []),
                               key=lambda x: x.get('NumVotes', 0), reverse=True):
                pkg = StoreData(
                    item.get('Name', ''),
                    item.get('Version', ''),
                    item.get('Description') or 'AUR package',
                    'AUR',
                    source_type='aur'
                )
                pkg.num_votes = item.get('NumVotes', 0)
                pkg.category = guess_cat(pkg.name)
                pkgs.append(pkg)
        except Exception:
            pass
        self.finished.emit(pkgs)


class ScreenshotDownloadThread(QThread):
    """Downloads a single screenshot URL to the local cache."""
    done = pyqtSignal(str, str)  # (url, local_path)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        os.makedirs(SCREENSHOT_CACHE_DIR, exist_ok=True)
        sha = hashlib.sha256(self.url.encode()).hexdigest()
        local_path = os.path.join(SCREENSHOT_CACHE_DIR, f"{sha}.jpg")
        if os.path.exists(local_path):
            self.done.emit(self.url, local_path)
            return
        try:
            req = Request(self.url, headers={'User-Agent': 'equestria-os-software-center/1.0'})
            with urlopen(req, timeout=15) as resp:
                with open(local_path, 'wb') as f:
                    f.write(resp.read())
            self.done.emit(self.url, local_path)
        except Exception:
            self.done.emit(self.url, "")


class LocalAppStreamLoader(QThread):
    """Searches /usr/share/metainfo for screenshot URLs of a Pacman package."""
    finished = pyqtSignal(list)

    def __init__(self, pkg_name):
        super().__init__()
        self.pkg_name = pkg_name

    def run(self):
        urls = []
        for d in ('/usr/share/metainfo', '/usr/share/appdata'):
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if self.pkg_name in fname and fname.endswith('.xml'):
                    urls = self._parse_screenshots(os.path.join(d, fname))
                    if urls:
                        break
            if urls:
                break
        self.finished.emit(urls)

    def _parse_screenshots(self, path):
        urls = []
        try:
            root = ET.parse(path).getroot()
            screenshots_el = root.find('screenshots')
            if screenshots_el is not None:
                for ss in screenshots_el.findall('screenshot')[:5]:
                    for img in ss.findall('image'):
                        if img.text:
                            urls.append(img.text)
                            break
        except Exception:
            pass
        return urls


class PacmanInfoLoader(QThread):
    """Fetches a single package description via `pacman -Si`.

    Used to enrich generic 'Arch Repository' descriptions on-demand when
    expac is not installed and the detail page is opened.
    """
    finished = pyqtSignal(str)  # emits description string (may be empty)

    def __init__(self, pkg_name):
        super().__init__()
        self.pkg_name = pkg_name

    def run(self):
        desc = ""
        try:
            res = subprocess.run(
                ["pacman", "-Si", self.pkg_name],
                capture_output=True, text=True
            )
            for line in res.stdout.splitlines():
                if line.startswith("Description"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        desc = parts[1].strip()
                    break
        except Exception:
            pass
        self.finished.emit(desc)
