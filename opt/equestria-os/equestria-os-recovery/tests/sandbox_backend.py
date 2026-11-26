"""
Root-бэкенд целиком, но в песочнице: `python3 tests/sandbox_backend.py`.

Скрипт сам перезапускается в `unshare -r` (пространство имён, где процесс — root только
для себя): так проходят проверки «владелец — root» и chown, а настоящие /var/lib,
/boot/grub и разделы не трогаются — все пути подменены на временную папку.
Подменены и вызовы, которым нужен настоящий диск (grub-probe), и поиск разделов.
ISO — маленький настоящий (bsdtar, ISO 9660) со структурой archiso.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

if os.geteuid() != 0 and not os.environ.get("EQREC_SANDBOX"):
    if not shutil.which("unshare"):
        print("skip: нет unshare")
        sys.exit(0)
    os.environ["EQREC_SANDBOX"] = "1"
    os.execvp("unshare", ["unshare", "-r", sys.executable, *sys.argv])

import recovery_backend as backend      # noqa: E402
import recovery_grub as grub            # noqa: E402
import recovery_image as image          # noqa: E402
from recovery_storage import StorageLocation   # noqa: E402

LOOPBACK = """menuentry "Equestria OS" {
  linux /arch/boot/x86_64/vmlinuz-linux-lts archisobasedir=arch img_dev=$imgdevpath img_loop=$iso_path quiet splash
  initrd /arch/boot/x86_64/initramfs-linux-lts.img
}
"""
GRUB_CFG = """function load_video {
  insmod efi_gop
}
menuentry 'Equestria OS' {
\tload_video
\tlinux /vmlinuz-linux-lts root=UUID=x rw
}
"""


def make_iso(path: Path, rootfs: bytes = b"squashfs" * 4096, damaged=False):
    tree = path.parent / "isotree"
    for rel, data in {"boot/grub/loopback.cfg": LOOPBACK.encode(), "arch/version": b"2026.11.26\n",
                      "arch/boot/x86_64/vmlinuz-linux-lts": b"k" * 4096,
                      "arch/boot/x86_64/initramfs-linux-lts.img": b"i" * 4096,
                      "arch/x86_64/airootfs.sfs": rootfs}.items():
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (tree / rel).write_bytes(data)
    digest = hashlib.sha512(rootfs + (b"x" if damaged else b"")).hexdigest()
    (tree / "arch/x86_64/airootfs.sha512").write_text(f"{digest}  airootfs.sfs\n")
    subprocess.run(["bsdtar", "--format", "iso9660", "-cf", str(path), "-C", str(tree), "boot", "arch"],
                   check=True)
    shutil.rmtree(tree)


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="eqrec-sandbox-"))
        self.state_dir = self.t / "var/lib/equestria-recovery"
        self.grub_dir = self.t / "boot/grub"
        self.other = self.t / "mnt/Main"
        for d in (self.state_dir, self.grub_dir, self.other):
            d.mkdir(parents=True)
        (self.grub_dir / "grub.cfg").write_text(GRUB_CFG)
        self.env_path = str(self.grub_dir / "equestria-recovery.env")
        self.iso = self.t / "download.iso"
        make_iso(self.iso)
        self.broken_dirs = set()          # где «GRUB не находит образ»

        self._saved = []
        self.patch(backend, "STATE_DIR", str(self.state_dir))
        self.patch(image, "STATE_DIR", str(self.state_dir))
        self.patch(image, "STATE_FILE", str(self.state_dir / "state.json"))
        for mod in (backend, grub):
            self.patch(mod, "GRUB_CFG", str(self.grub_dir / "grub.cfg"))
            self.patch(mod, "GRUB_ENTRY_CFG", str(self.grub_dir / "equestria-recovery.cfg"))
        self.patch(grub, "env_location", lambda: self.env_path)
        self.patch(backend, "save_point_rolls_back", lambda: False)
        self.patch(grub.GrubIntegration, "available", staticmethod(lambda: True))

        def probe(path):
            if any(str(path).startswith(str(d)) for d in self.broken_dirs):
                raise grub.GrubError("error.grub_probe")
            fs = "fat" if str(path).endswith(".env") else "ext2"
            return grub.GrubPath(uuid="U-" + Path(path).parent.name, fs=fs, relpath=str(path))
        self.patch(grub.GrubPath, "probe", staticmethod(probe))

        locations = {
            "default": StorageLocation("default", "/", str(self.state_dir), "/dev/sys", "SYS", "ext4",
                                       10 ** 12, True, False),
            str(self.other): StorageLocation(str(self.other), str(self.other),
                                             str(self.other / ".equestria-recovery"), "/dev/other",
                                             "OTHER", "btrfs", 10 ** 12, False, True),
        }
        self.patch(backend.StorageLocations, "find", lambda _self, key: locations.get(key))

    def patch(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def tearDown(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)
        shutil.rmtree(self.t)

    def installer(self):
        return backend.ImageInstaller()

    def env(self):
        return grub.EnvFile(self.env_path).values()

    def entry_cfg(self):
        return (self.grub_dir / "equestria-recovery.cfg").read_text()

    # ── установка ──────────────────────────────────────────────────────────

    def test_install_registers_everything(self):
        self.installer().install(str(self.iso), move=False, md5="", source="x.iso", lang="en", verify=True)
        state = image.RecoveryState.load()
        self.assertTrue(os.path.isfile(state.iso_path))
        self.assertEqual(state.version, "2026.11.26")
        self.assertTrue(state.one_shot_ok and state.auto_ok)
        self.assertIn("function load_video", self.entry_cfg())
        self.assertIn(state.iso_path, self.entry_cfg())
        self.assertIn(grub.GRUB_BLOCK_BEGIN, (self.grub_dir / "grub.cfg").read_text())
        self.assertEqual(self.env(), {"eqrec_limit": "2"})
        self.assertTrue(self.iso.exists())                 # без --move исходник на месте

    def test_install_rejects_damaged_image(self):
        bad = self.t / "bad.iso"
        make_iso(bad, damaged=True)
        with self.assertRaises(backend.BackendError) as e:
            self.installer().install(str(bad), move=False, md5="", source="", lang="", verify=True)
        self.assertEqual(e.exception.args[0], "error.checksum")
        self.assertEqual(os.listdir(self.state_dir), [])   # ни образа, ни .tmp

    def test_no_counter_without_load_video(self):
        (self.grub_dir / "grub.cfg").write_text(GRUB_CFG.replace("\tload_video\n", ""))
        self.installer().install(str(self.iso), move=False, md5="", source="", lang="", verify=False)
        state = image.RecoveryState.load()
        self.assertTrue(state.one_shot_ok)
        self.assertFalse(state.auto_ok)
        self.assertNotIn("function load_video", self.entry_cfg())

    # ── место хранения ─────────────────────────────────────────────────────

    def test_relocate_moves_image(self):
        inst = self.installer()
        inst.install(str(self.iso), move=False, md5="", source="", lang="", verify=False)
        inst.relocate(str(self.other), "")
        state = image.RecoveryState.load()
        new = self.other / ".equestria-recovery" / "equestria-recovery.iso"
        self.assertEqual(state.iso_path, str(new))
        self.assertTrue(new.is_file())
        self.assertFalse((self.state_dir / "equestria-recovery.iso").exists())
        self.assertIn(str(new), self.entry_cfg())
        self.assertEqual(oct(new.parent.stat().st_mode & 0o777), "0o755")
        inst.relocate("default", "")                       # и обратно
        state = image.RecoveryState.load()
        self.assertEqual(state.iso_dir, "")
        self.assertTrue(os.path.isfile(state.iso_path))
        self.assertFalse(new.parent.exists())

    def test_relocate_rolls_back_when_grub_cannot_read(self):
        inst = self.installer()
        inst.install(str(self.iso), move=False, md5="", source="", lang="", verify=False)
        self.broken_dirs.add(self.other)
        with self.assertRaises(backend.BackendError):
            inst.relocate(str(self.other), "")
        state = image.RecoveryState.load()
        self.assertEqual(state.iso_dir, "")
        self.assertEqual(state.grub_error, "")
        self.assertTrue(os.path.isfile(state.iso_path))
        self.assertFalse((self.other / ".equestria-recovery" / "equestria-recovery.iso").exists())
        self.assertIn(str(self.state_dir), self.entry_cfg())

    def test_relocate_without_image_only_remembers(self):
        self.installer().relocate(str(self.other), "")
        self.assertEqual(image.RecoveryState.load().iso_dir, str(self.other / ".equestria-recovery"))
        self.installer().install(str(self.iso), move=True, md5="", source="", lang="", verify=False)
        self.assertTrue((self.other / ".equestria-recovery" / "equestria-recovery.iso").is_file())
        self.assertFalse(self.iso.exists())                # --move: исходник убран

    def test_unknown_location_refused(self):
        with self.assertRaises(backend.BackendError) as e:
            self.installer().relocate("/etc", "")
        self.assertEqual(e.exception.args[0], "error.location_invalid")

    def test_symlinked_folder_refused(self):
        (self.other / ".equestria-recovery").symlink_to(self.t / "elsewhere")
        (self.t / "elsewhere").mkdir()
        with self.assertRaises(OSError):
            self.installer().relocate(str(self.other), "")
        self.assertEqual(os.listdir(self.t / "elsewhere"), [])

    # ── счётчик ────────────────────────────────────────────────────────────

    def test_boot_ok_and_auto_switch(self):
        inst = self.installer()
        inst.install(str(self.iso), move=False, md5="", source="", lang="", verify=False)
        grub.EnvFile(self.env_path).set(eqrec_fails=2, equestria_recovery_once=1)
        inst.boot_ok()
        self.assertEqual(self.env(), {"eqrec_limit": "2"})
        inst.set_auto(False)
        self.assertEqual(self.env(), {"eqrec_limit": "0"})
        inst.boot_ok()                                     # после перезагрузки выключенное не включается
        self.assertEqual(self.env(), {"eqrec_limit": "0"})
        inst.set_auto(True)
        self.patch(backend, "save_point_rolls_back", lambda: True)
        inst.boot_ok()
        self.assertEqual(self.env(), {"eqrec_limit": "4"})

    def test_boot_ok_without_image_does_nothing(self):
        self.installer().boot_ok()
        self.assertFalse(os.path.exists(self.env_path))

    def test_remove_cleans_up(self):
        inst = self.installer()
        inst.install(str(self.iso), move=False, md5="", source="", lang="", verify=False)
        inst.remove()
        self.assertFalse((self.grub_dir / "equestria-recovery.cfg").exists())
        self.assertFalse(os.path.exists(self.env_path))
        self.assertFalse((self.state_dir / "equestria-recovery.iso").exists())

    # ── установщик ─────────────────────────────────────────────────────────

    def test_import_live_from_device(self):
        """Флешка: ISO в начале устройства, дальше — чужие данные. Копируется ровно образ."""
        target = self.t / "target"
        (target / "etc").mkdir(parents=True)
        device = self.t / "usb.img"
        data = self.iso.read_bytes()
        device.write_bytes(data + b"\xff" * 1_000_000)
        size = len(data)
        self.patch(backend.LiveMedium, "detect",
                   classmethod(lambda cls: cls(path=str(device), size=size, kind="device")))
        imp = backend.LiveImporter(str(target))
        imp.register_cmd = ["true"]
        imp.run("ru")
        copied = target / str(self.state_dir).lstrip("/") / "equestria-recovery.iso"
        self.assertEqual(copied.read_bytes(), data)
        st = image.RecoveryState.load(str(copied.parent / "state.json"))
        self.assertEqual((st.source, st.version), ("live-device", "2026.11.26"))

    def test_import_live_rejects_damaged_medium(self):
        target = self.t / "target"
        (target / "etc").mkdir(parents=True)
        bad = self.t / "bad.iso"
        make_iso(bad, damaged=True)
        self.patch(backend.LiveMedium, "detect",
                   classmethod(lambda cls: cls(path=str(bad), size=bad.stat().st_size, kind="file")))
        imp = backend.LiveImporter(str(target))
        imp.register_cmd = ["false"]
        with self.assertRaises(backend.BackendError):
            imp.run("")
        folder = target / str(self.state_dir).lstrip("/")
        self.assertEqual(os.listdir(folder), [])

    def test_import_live_refuses_live_root(self):
        with self.assertRaises(backend.BackendError):
            backend.LiveImporter("/").run("")


if __name__ == "__main__":
    unittest.main(verbosity=2)
