"""
Read-only health check of the swap/memory setup, run as the normal user.

MemoryState takes one snapshot of the system; each Check looks at it and
returns an Issue (translation key + backend arguments that fix it) or None.
The GUI lists the issues with "Fix" buttons — no terminal needed.
"""
import os
import subprocess
from dataclasses import dataclass, field

from memory_config import (
    KNOBS, ZSWAP_PARAM, LEGACY_ZRAM_SERVICE,
    read_zram_dropin,
)

RECOMMENDED_ALGORITHM = "zstd"
RECOMMENDED_SWAPPINESS = 150


def recommended_zram_gb(ram_gb):
    return max(4, ram_gb // 2)


def read_ram_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return max(1, int(line.split()[1]) // 1024 // 1024)
    except (OSError, ValueError):
        pass
    return 8


@dataclass
class SwapArea:
    name: str
    size: str
    used: str
    kind: str


@dataclass
class ZramDevice:
    path: str
    size: str
    algorithm: str = ""
    ratio: float | None = None  # original / compressed, None while empty


@dataclass
class MemoryState:
    swaps: list = field(default_factory=list)        # [SwapArea]
    zram: list = field(default_factory=list)         # [ZramDevice] active as swap
    dropin: tuple | None = None                      # (size_mb, algorithm)
    zswap_enabled: bool | None = None
    legacy_service: bool = False
    ram_gb: int = 8
    mem_total_gib: float = 0.0
    mem_used_gib: float = 0.0
    oomd_enabled: bool = False
    values: dict = field(default_factory=dict)       # knob name -> current value

    @classmethod
    def from_system(cls):
        state = cls(ram_gb=read_ram_gb(), dropin=read_zram_dropin(),
                    legacy_service=os.path.exists(LEGACY_ZRAM_SERVICE))
        try:
            r = subprocess.run(["swapon", "--show=NAME,SIZE,USED,TYPE", "--noheadings", "--raw"],
                               capture_output=True, text=True)
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    state.swaps.append(SwapArea(*parts[:4]))
        except OSError:
            pass
        for area in state.swaps:
            if area.name.startswith("/dev/zram"):
                state.zram.append(cls._zram_device(area.name, area.size))
        state._read_meminfo()
        try:
            r = subprocess.run(["systemctl", "is-enabled", "systemd-oomd"],
                               capture_output=True, text=True)
            state.oomd_enabled = r.stdout.strip() in ("enabled", "static", "preset")
        except OSError:
            pass
        try:
            with open(ZSWAP_PARAM) as f:
                state.zswap_enabled = f.read().strip() in ("Y", "1")
        except OSError:
            state.zswap_enabled = None
        state.values = {name: knob.read() for name, knob in KNOBS.items()}
        return state

    def _read_meminfo(self):
        info = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    key, _, rest = line.partition(":")
                    info[key] = int(rest.split()[0])
        except (OSError, ValueError, IndexError):
            return
        kib = 1024 * 1024
        self.mem_total_gib = info.get("MemTotal", 0) / kib
        self.mem_used_gib = (info.get("MemTotal", 0) - info.get("MemAvailable", 0)) / kib

    @staticmethod
    def _zram_device(path, size):
        dev = ZramDevice(path, size)
        block = f"/sys/block/{os.path.basename(path)}"
        try:
            with open(f"{block}/comp_algorithm") as f:
                dev.algorithm = next((w[1:-1] for w in f.read().split()
                                      if w.startswith("[")), "")
            with open(f"{block}/mm_stat") as f:
                orig, compr = (int(x) for x in f.read().split()[:2])
            if compr:
                dev.ratio = orig / compr
        except (OSError, ValueError):
            pass
        return dev

    @property
    def zram_active(self):
        return bool(self.zram)

    def zram_target(self):
        """(size_gb, algorithm) to (re)enable zram with: our saved settings,
        or the recommended ones when there are none."""
        if self.dropin and self.dropin[0] > 0:
            size_gb = max(1, self.dropin[0] // 1024)
            return size_gb, self.dropin[1] or RECOMMENDED_ALGORITHM
        return recommended_zram_gb(self.ram_gb), RECOMMENDED_ALGORITHM


@dataclass
class Issue:
    key: str                     # translation key of the message
    fix: list                    # backend arguments that fix it
    args: tuple = ()             # values for {0}, {1}… in the message
    severity: str = "warn"       # "warn" | "info"


class Check:
    def inspect(self, state: MemoryState) -> Issue | None:
        raise NotImplementedError


def _zram_enable_args(state):
    size_gb, algo = state.zram_target()
    return ["--zram-enable", str(size_gb), algo]


class LegacyServiceCheck(Check):
    def inspect(self, state):
        if state.legacy_service:
            return Issue("health_legacy", _zram_enable_args(state))
        return None


class ExtraZramCheck(Check):
    def inspect(self, state):
        if len(state.zram) > 1:
            return Issue("health_extra_zram", _zram_enable_args(state), (len(state.zram),))
        return None


class ZramNotRunningCheck(Check):
    """Our drop-in asks for zram, but no zram swap is active (e.g. a failed start)."""

    def inspect(self, state):
        if state.dropin and state.dropin[0] > 0 and not state.zram_active:
            return Issue("health_zram_down", _zram_enable_args(state))
        return None


class NoSwapCheck(Check):
    def inspect(self, state):
        if not state.swaps and not (state.dropin and state.dropin[0] > 0):
            return Issue("health_no_swap", _zram_enable_args(state), severity="info")
        return None


class ZswapWithZramCheck(Check):
    def inspect(self, state):
        if state.zram_active and state.zswap_enabled:
            return Issue("health_zswap", ["--zswap", "off"])
        return None


class LowSwappinessCheck(Check):
    """With zram, swapping is cheap and dropping program code is not —
    a low swappiness makes the kernel re-read programs from disk (lags)."""

    def inspect(self, state):
        value = state.values.get("swappiness")
        if state.zram_active and value is not None and value < 100:
            return Issue("health_swappiness", ["--set", "swappiness", str(RECOMMENDED_SWAPPINESS)],
                         (value, RECOMMENDED_SWAPPINESS))
        return None


class PageClusterCheck(Check):
    def inspect(self, state):
        value = state.values.get("page_cluster")
        if state.zram_active and value not in (None, 0):
            return Issue("health_page_cluster", ["--set", "page_cluster", "0"], (value,))
        return None


class ThpAlwaysCheck(Check):
    """THP "always" makes processes stall on memory compaction under pressure."""

    def inspect(self, state):
        if state.values.get("thp") == "always":
            return Issue("health_thp", ["--set", "thp", "madvise"], severity="info")
        return None


CHECKS = (
    LegacyServiceCheck(), ExtraZramCheck(), ZramNotRunningCheck(), NoSwapCheck(),
    ZswapWithZramCheck(), LowSwappinessCheck(), PageClusterCheck(), ThpAlwaysCheck(),
)


def run_checks(state):
    return [issue for issue in (c.inspect(state) for c in CHECKS) if issue]


def combined_fix(issues):
    """All fixes as one backend call (one password prompt), without repeats.
    zram (re)enable goes first — it also handles zswap and page-cluster."""
    seen, ordered = set(), []
    for issue in sorted(issues, key=lambda i: i.fix[0] != "--zram-enable"):
        key = tuple(issue.fix)
        if issue.fix[0] == "--zram-enable":
            key = ("--zram-enable",)
        if key not in seen:
            seen.add(key)
            ordered.extend(issue.fix)
    return ordered
