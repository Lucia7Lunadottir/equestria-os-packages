import os
import sys
import json
import time
import subprocess
import urllib.request
import tarfile

PROTON_DIR = os.path.expanduser("~/.local/share/Equestria OS/Proton/")
API_URL = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
UPDATE_STAMP = os.path.expanduser("~/.config/Equestria OS/Proton/last_update_check")
UPDATE_INTERVAL = 7 * 24 * 3600  # 7 days


# ─── Version helpers ─────────────────────────────────────────────────────────

def get_installed_version():
    """Return version tag of managed GE-Proton (e.g. 'GE-Proton10-1'), or None."""
    latest_link = os.path.join(PROTON_DIR, "latest")
    if os.path.islink(latest_link):
        target = os.readlink(latest_link)
        return os.path.basename(target.rstrip("/"))
    return None


def should_check_update():
    if not os.path.exists(UPDATE_STAMP):
        return True
    try:
        with open(UPDATE_STAMP) as f:
            last = float(f.read().strip())
        return (time.time() - last) >= UPDATE_INTERVAL
    except Exception:
        return True


def save_check_timestamp():
    os.makedirs(os.path.dirname(UPDATE_STAMP), exist_ok=True)
    with open(UPDATE_STAMP, "w") as f:
        f.write(str(time.time()))


# ─── GitHub API ──────────────────────────────────────────────────────────────

def get_latest_release_info():
    """Return (version_tag, download_url) of the latest GE-Proton, or (None, None)."""
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            for asset in data.get("assets", []):
                if asset["name"].endswith(".tar.gz"):
                    return data["tag_name"], asset["browser_download_url"]
    except Exception as e:
        print(f"Update check failed: {e}")
    return None, None


# ─── Download / install ──────────────────────────────────────────────────────

def download_and_install(version_tag, download_url):
    """Console-only install (no GUI)."""
    download_and_install_with_progress(version_tag, download_url, progress_cb=None)


def download_and_install_with_progress(version_tag, download_url, progress_cb=None):
    """
    Download and install GE-Proton.
    progress_cb — optional Qt signal with .emit(message: str, percent: int).
    """
    def _emit(msg, pct):
        print(f"[{pct:3d}%] {msg}")
        if progress_cb is not None:
            progress_cb.emit(msg, pct)

    os.makedirs(PROTON_DIR, exist_ok=True)
    archive_path = os.path.join(PROTON_DIR, f"{version_tag}.tar.gz")

    _emit(f"Downloading Proton {version_tag}…", 15)

    def _reporthook(block_count, block_size, total_size):
        if total_size <= 0:
            return
        downloaded = block_count * block_size
        pct = min(int(downloaded / total_size * 70) + 15, 85)
        mb_done = downloaded / 1024 / 1024
        mb_total = total_size / 1024 / 1024
        _emit(f"Downloading… {mb_done:.0f} / {mb_total:.0f} MB", pct)

    urllib.request.urlretrieve(download_url, archive_path, reporthook=_reporthook)

    _emit("Extracting archive…", 87)
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=PROTON_DIR)

    _emit("Cleaning up…", 95)
    os.remove(archive_path)

    extracted_folder = os.path.join(PROTON_DIR, version_tag)
    latest_link = os.path.join(PROTON_DIR, "latest")
    if os.path.lexists(latest_link):
        os.remove(latest_link)
    os.symlink(extracted_folder, latest_link)

    _emit(f"Proton {version_tag} installed.", 100)


# ─── Background check (spawned from launcher) ────────────────────────────────

def check_and_notify():
    """Check for a newer GE-Proton and send a desktop notification if available."""
    if not should_check_update():
        return
    save_check_timestamp()

    installed = get_installed_version()
    latest, _ = get_latest_release_info()
    if not latest or latest == installed:
        return

    try:
        subprocess.Popen([
            "notify-send",
            "--app-name=Equestria OS",
            "--icon=wine",
            "Proton update available",
            f"{latest} is ready. Open Proton Settings to update.",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--check" in sys.argv:
        check_and_notify()
    else:
        version, url = get_latest_release_info()
        if version and url:
            download_and_install(version, url)
        else:
            print("Could not find download link.")
