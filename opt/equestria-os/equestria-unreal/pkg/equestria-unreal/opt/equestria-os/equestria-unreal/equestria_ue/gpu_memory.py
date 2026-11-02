from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

# Сколько видеопамяти просит редактор UE 5 с Lumen, Nanite и трассировкой лучей.
# Когда её не хватает, VulkanRHI не может выделить память и падает: «Out of memory
# on Vulkan» или segfault в распределителе памяти чуть позже (журналы 2026-11-02/03).
NEEDED_MIB = 5000


@dataclass
class VramReport:
    total_mib: int
    free_mib: int
    consumers: list = field(default_factory=list)   # [(название, МиБ)] по убыванию

    @property
    def enough(self) -> bool:
        return self.free_mib >= NEEDED_MIB


def _short_name(path: str) -> str:
    name = path.split()[0].rsplit("/", 1)[-1] if path else "?"
    return {"unityhub-bin": "Unity Hub", "Unity": "Unity", "kwin_wayland": "KWin"}.get(name, name)


def query() -> VramReport | None:
    """Свободная видеопамять NVIDIA и кто её занимает (nvidia-smi). None — не NVIDIA или нет nvidia-smi."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        mem = subprocess.run(["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
        total, free = (int(x) for x in mem[0].split(","))
        apps = subprocess.run(["nvidia-smi", "--query-compute-apps=process_name,used_memory",
                               "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
    usage: dict[str, int] = {}
    for line in apps.splitlines():
        name, _, mib = line.rpartition(",")
        try:
            usage[_short_name(name.strip())] = usage.get(_short_name(name.strip()), 0) + int(mib)
        except ValueError:
            continue
    consumers = sorted(((n, m) for n, m in usage.items() if m >= 100), key=lambda x: -x[1])
    return VramReport(total, free, consumers)
