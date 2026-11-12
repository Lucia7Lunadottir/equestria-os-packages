"""
Single description of every memory setting the Swap Manager touches.

Shared by the GUI (reads current values, lists the config files) and the
root backend (applies and persists), so paths and limits live in one place.
Reading works as a normal user; apply() needs root.
"""
import os

SYSCTL_DIR = "/etc/sysctl.d"
TMPFILES_DIR = "/etc/tmpfiles.d"

SWAPPINESS_FILE = os.path.join(SYSCTL_DIR, "99-swappiness.conf")
MEMORY_FILE = os.path.join(SYSCTL_DIR, "99-memory.conf")
ZRAM_SYSCTL_FILE = os.path.join(SYSCTL_DIR, "99-zram.conf")
TUNING_FILE = os.path.join(SYSCTL_DIR, "99-vm-tuning.conf")
MM_TMPFILES = os.path.join(TMPFILES_DIR, "equestria-swap-manager-mm.conf")

# zram is configured through zram-generator (one device, zram0) via our own
# drop-in, so it can't collide with a system-wide zram-generator.conf.
ZRAM_GENERATOR = "/usr/lib/systemd/system-generators/zram-generator"
ZRAM_BASE_CONF = "/etc/systemd/zram-generator.conf"
ZRAM_DROPIN = "/etc/systemd/zram-generator.conf.d/90-equestria-swap-manager.conf"
ZRAM_DEVICE = "zram0"
# Old versions created their own device with this service — on top of
# zram-generator's, giving two zram devices at once.
LEGACY_ZRAM_SERVICE = "/etc/systemd/system/equestria-zram.service"
ZSWAP_PARAM = "/sys/module/zswap/parameters/enabled"
ZSWAP_TMPFILES = os.path.join(TMPFILES_DIR, "equestria-swap-manager-zswap.conf")
FSTAB_PATH = "/etc/fstab"

ZRAM_ALGORITHMS = ("zstd", "lz4", "lzo-rle")

MIB = 1024 * 1024


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _write(path, value):
    with open(path, "w") as f:
        f.write(str(value))


def replace_line(path, prefix, line):
    """Keep every line of `path` except the one starting with `prefix`;
    append `line` (or just drop the old one when `line` is None)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    if os.path.exists(path):
        with open(path) as f:
            lines = [l for l in f.readlines() if not l.startswith(prefix)]
    if line is not None:
        lines.append(line + "\n")
    with open(path, "w") as f:
        f.writelines(lines)


# ── knobs ─────────────────────────────────────────────────────────────────────

class Knob:
    """One kernel setting: how to read it, check a new value and apply it."""

    def __init__(self, name, persist_path):
        self.name = name
        self.persist_path = persist_path

    @property
    def available(self) -> bool:
        return True

    def read(self):
        raise NotImplementedError

    def validate(self, value):
        """Return the value normalized for apply(); raise ValueError if bad."""
        raise NotImplementedError

    def apply(self, value):
        raise NotImplementedError


class SysctlKnob(Knob):
    """Integer sysctl, persisted as `key=value` in a sysctl.d file."""

    def __init__(self, name, key, persist_path, minimum, maximum, default):
        super().__init__(name, persist_path)
        self.key = key
        self.minimum = minimum
        self.maximum = maximum
        self.default = default

    @staticmethod
    def proc_path(key):
        return "/proc/sys/" + key.replace(".", "/")

    @property
    def available(self) -> bool:
        return os.path.exists(self.proc_path(self.key))

    def read(self):
        raw = _read(self.proc_path(self.key))
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def validate(self, value):
        value = int(value)
        if not self.minimum <= value <= self.maximum:
            raise ValueError(f"{self.name}: {value} is outside {self.minimum}..{self.maximum}")
        return value

    def apply(self, value):
        value = self.validate(value)
        if not self.available:
            return  # not compiled into this kernel — nothing to set
        _write(self.proc_path(self.key), value)
        replace_line(self.persist_path, f"{self.key}=", f"{self.key}={value}")


class DirtyKnob(SysctlKnob):
    """
    Writeback threshold shown in MiB.

    The kernel has a *_bytes and a *_ratio form of the same limit; setting one
    zeroes the other. *_bytes refuses 0, so "0 MiB" means "back to the
    kernel's percentage default" and writes the ratio instead.
    """

    def __init__(self, name, bytes_key, ratio_key, default_ratio, maximum_mib):
        super().__init__(name, bytes_key, TUNING_FILE, 0, maximum_mib, 0)
        self.ratio_key = ratio_key
        self.default_ratio = default_ratio

    def read(self):
        raw = super().read()
        return None if raw is None else raw // MIB

    def apply(self, value):
        value = self.validate(value)
        if value == 0:
            _write(self.proc_path(self.ratio_key), self.default_ratio)
            replace_line(self.persist_path, f"{self.key}=", None)
            replace_line(self.persist_path, f"{self.ratio_key}=",
                         f"{self.ratio_key}={self.default_ratio}")
        else:
            _write(self.proc_path(self.key), value * MIB)
            replace_line(self.persist_path, f"{self.ratio_key}=", None)
            replace_line(self.persist_path, f"{self.key}=", f"{self.key}={value * MIB}")


class SysfsChoiceKnob(Knob):
    """
    sysfs file with a fixed set of words, e.g. "always [madvise] never".
    sysfs has no config file of its own, so a tmpfiles.d `w` line re-applies
    the value on every boot.
    """

    def __init__(self, name, path, choices, default):
        super().__init__(name, MM_TMPFILES)
        self.path = path
        self.choices = choices
        self.default = default

    @property
    def available(self) -> bool:
        return os.path.exists(self.path)

    def read(self):
        raw = _read(self.path)
        if raw is None:
            return None
        for word in raw.split():
            if word.startswith("[") and word.endswith("]"):
                return word[1:-1]
        return raw

    def validate(self, value):
        if value not in self.choices:
            raise ValueError(f"{self.name}: {value!r} is not one of {', '.join(self.choices)}")
        return value

    def apply(self, value):
        value = self.validate(value)
        if not self.available:
            return
        _write(self.path, value)
        replace_line(self.persist_path, f"w {self.path} ", f"w {self.path} - - - - {value}")


THP_ENABLED = "/sys/kernel/mm/transparent_hugepage/enabled"
THP_DEFRAG = "/sys/kernel/mm/transparent_hugepage/defrag"

KNOBS = {k.name: k for k in (
    SysctlKnob("swappiness", "vm.swappiness", SWAPPINESS_FILE, 0, 200, 60),
    SysctlKnob("overcommit", "vm.overcommit_memory", MEMORY_FILE, 0, 2, 0),
    SysctlKnob("panic_on_oom", "kernel.panic_on_oom", MEMORY_FILE, 0, 2, 0),
    SysctlKnob("page_cluster", "vm.page-cluster", ZRAM_SYSCTL_FILE, 0, 10, 3),
    SysctlKnob("vfs_cache_pressure", "vm.vfs_cache_pressure", TUNING_FILE, 1, 1000, 100),
    SysctlKnob("watermark_boost_factor", "vm.watermark_boost_factor", TUNING_FILE, 0, 30000, 15000),
    SysctlKnob("watermark_scale_factor", "vm.watermark_scale_factor", TUNING_FILE, 1, 3000, 10),
    DirtyKnob("dirty_background_mb", "vm.dirty_background_bytes", "vm.dirty_background_ratio", 10, 65536),
    DirtyKnob("dirty_mb", "vm.dirty_bytes", "vm.dirty_ratio", 20, 65536),
    SysfsChoiceKnob("thp", THP_ENABLED, ("always", "madvise", "never"), "always"),
    SysfsChoiceKnob("thp_defrag", THP_DEFRAG,
                    ("always", "defer", "defer+madvise", "madvise", "never"), "madvise"),
)}


# ── zram drop-in ──────────────────────────────────────────────────────────────

def read_zram_dropin():
    """(size_mb, algorithm) from our zram-generator drop-in, or None."""
    raw = _read(ZRAM_DROPIN)
    if raw is None:
        return None
    size, algo = None, None
    for line in raw.splitlines():
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key == "zram-size":
            try:
                size = int(value)
            except ValueError:
                pass
        elif key == "compression-algorithm":
            algo = value
    return (size, algo) if size is not None else None


# ── files for the "Configuration files" panel ─────────────────────────────────

# (translation key of the description, path); the GUI shows each with
# "open" / "show in folder" buttons.
CONFIG_FILES = (
    ("files_zram_dropin", ZRAM_DROPIN),
    ("files_zram_base", ZRAM_BASE_CONF),
    ("files_swappiness", SWAPPINESS_FILE),
    ("files_memory", MEMORY_FILE),
    ("files_zram_sysctl", ZRAM_SYSCTL_FILE),
    ("files_tuning", TUNING_FILE),
    ("files_mm_tmpfiles", MM_TMPFILES),
    ("files_zswap", ZSWAP_TMPFILES),
    ("files_fstab", FSTAB_PATH),
)
