"""Install the verified standalone Linux CLI from Unity's stable channel."""
import hashlib
import json
import os
import platform
import re
import tempfile
from pathlib import Path
from urllib.request import urlopen

CDN = "https://public-cdn.cloud.unity3d.com/hub/prod/cli/"


def download(destination):
    arch = {"x86_64": "x64", "aarch64": "arm64"}.get(platform.machine().lower())
    if not arch:
        raise ValueError(f"Unity CLI: {platform.machine()}")
    with urlopen(CDN + "latest.json", timeout=30) as response:
        manifest = json.load(response)
    version = manifest["version"]
    binary = manifest["binaries"][f"linux-{arch}"]
    filename = binary["filename"]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", version) or filename != f"unity-linux-{arch}":
        raise ValueError("Invalid Unity CLI release manifest")

    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        with temporary.open("wb") as output, urlopen(f"{CDN}{version}/{filename}", timeout=30) as response:
            while chunk := response.read(256 * 1024):
                output.write(chunk)
                digest.update(chunk)
        if temporary.stat().st_size != binary["size"] or digest.hexdigest() != binary["sha256"]:
            raise ValueError("Unity CLI: SHA-256 / size mismatch")
        temporary.chmod(0o755)
        os.link(temporary, destination)  # A concurrent install keeps its binary.
    finally:
        temporary.unlink(missing_ok=True)
    return version
