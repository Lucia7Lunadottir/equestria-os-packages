"""
Тесты без root и без сети: `python3 tests/test_recovery.py`.
Каждая проверка — в обе стороны: заведомая поломка должна найтись, исправное — нет.
"""
import hashlib
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import recovery_rescue as rescue                          # noqa: E402
from recovery_grub import (EntryRenderer, EnvFile, GrubPath, IsoLocation, HOOK_BLOCK,   # noqa: E402
                           entries_call_load_video, video_body_from)
from recovery_livemedia import RootfsVerifier, image_size_on_device   # noqa: E402
from recovery_storage import StorageLocations                       # noqa: E402
from recovery_image import IsoInfo, copytoram_fits, version_from_filename   # noqa: E402
from recovery_source import Downloader, Release, ReleaseFeed, SourceError   # noqa: E402

GIB = 1024 ** 3


# ── GRUB ─────────────────────────────────────────────────────────────────────

class GrubEntryTest(unittest.TestCase):
    INFO = IsoInfo(version="2026.11.21", kernel="/arch/boot/x86_64/vmlinuz-linux-lts",
                   initrds=["/arch/boot/x86_64/initramfs-linux-lts.img"],
                   options="quiet splash", rootfs_size=int(4.4 * GIB))

    ENV = GrubPath("ABCD-1234", "fat", "/EFI/equestria-recovery/equestria-recovery.env")

    def render(self, fs="ext2", ram=32 * GIB, titles=None, env=ENV, video_body=""):
        loc = IsoLocation("1234-uuid", fs, "/var/lib/equestria-recovery/equestria-recovery.iso")
        return EntryRenderer().render(self.INFO, loc, titles or {"ram": "R", "noram": "N"}, ram=ram,
                                      env=env, video_body=video_body)

    @staticmethod
    def script_ok(text) -> bool:
        with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
            f.write(text)
        r = subprocess.run(["grub-script-check", f.name], capture_output=True)
        os.unlink(f.name)
        return r.returncode == 0

    def test_syntax_valid(self):
        if not shutil.which("grub-script-check"):
            self.skipTest("grub-script-check")
        for text in (self.render(), self.render("btrfs"), HOOK_BLOCK,
                     self.render(env=None), self.render(video_body=None),
                     self.render(video_body="  insmod all_video"),
                     self.render(titles={"ram": 'a "b" $c \\d', "noram": "Восстановление"})):
            self.assertTrue(self.script_ok(text), text)

    def test_syntax_check_catches_broken(self):   # контроль: проверка вообще что-то ловит
        if not shutil.which("grub-script-check"):
            self.skipTest("grub-script-check")
        with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
            f.write(self.render()[:-40])
        r = subprocess.run(["grub-script-check", f.name], capture_output=True)
        os.unlink(f.name)
        self.assertNotEqual(r.returncode, 0)

    def test_copytoram_first_when_ram_enough(self):
        text = self.render(ram=32 * GIB)
        first = text.index("--id equestria-recovery ")
        self.assertIn("copytoram=y", text[first:text.index("\n}", first)])

    def test_noram_first_when_ram_low(self):
        text = self.render(ram=6 * GIB)
        first = text.index("--id equestria-recovery ")
        self.assertIn("copytoram=n", text[first:text.index("\n}", first)])

    def test_btrfs_uses_top_level(self):
        self.assertIn("img_flags=subvolid=5", self.render("btrfs"))
        self.assertNotIn("img_flags", self.render("ext2"))

    def test_flag_and_one_shot(self):
        text = self.render()
        self.assertIn("equestria.recovery=1", text)
        self.assertIn('set default="equestria-recovery"', text)

    def test_counter_only_with_env_and_video(self):
        self.assertIn("function load_video", self.render())
        self.assertIn("eqrec_count_boot", self.render())
        self.assertNotIn("function load_video", self.render(video_body=None))   # текстовое меню
        self.assertNotIn("eqrec_reason=\"auto\"", self.render(video_body=None))
        no_env = self.render(env=None)
        self.assertNotIn("load_env", no_env)
        self.assertNotIn("function load_video", no_env)
        self.assertIn("equestria.recovery_reason=", no_env)

    def test_system_video_body_kept(self):
        text = self.render(video_body="  insmod my_video_driver")
        body = text[text.index("function load_video {"):]
        self.assertIn("insmod my_video_driver", body[:body.index("\n}")])
        self.assertIn("insmod efi_gop", self.render(video_body=""))   # не нашли — стандартное тело

    def test_counter_chain_capped(self):
        text = self.render()
        self.assertIn('set eqrec_fails="9"', text)
        self.assertNotIn('set eqrec_fails="10"', text)

    def test_recovery_entry_resets_counter(self):
        text = self.render()
        for entry in ("--id equestria-recovery ", "--id equestria-recovery-noram "):
            start = text.index(entry)
            self.assertIn('set eqrec_fails=""', text[start:text.index("\n}", start)])

    def test_copytoram_fits(self):
        self.assertTrue(copytoram_fits(int(4.4 * GIB), 32 * GIB))
        self.assertFalse(copytoram_fits(int(4.4 * GIB), 6 * GIB))
        self.assertFalse(copytoram_fits(0, 32 * GIB))


GRUB_CFG_SAMPLE = """### BEGIN /etc/grub.d/00_header ###
function load_video {
  if [ x$feature_all_video_module = xy ]; then
    insmod all_video
  else
    insmod efi_gop
  fi
}
if loadfont unicode ; then
  load_video
fi
menuentry 'Equestria OS' --class arch {
	load_video
	set gfxpayload=keep
	linux /vmlinuz-linux-lts root=UUID=x rw
}
menuentry 'Windows Boot Manager' {
	chainloader /EFI/Microsoft/Boot/bootmgfw.efi
}
"""


class GrubCfgParseTest(unittest.TestCase):
    def test_video_body(self):
        body = video_body_from(GRUB_CFG_SAMPLE)
        self.assertIn("insmod all_video", body)
        self.assertNotIn("function", body)
        self.assertEqual(video_body_from("menuentry x {\n}\n"), "")

    def test_entries_call_load_video(self):
        self.assertTrue(entries_call_load_video(GRUB_CFG_SAMPLE))
        # GRUB_GFXPAYLOAD_LINUX=text: load_video только в шапке — пункты не считаются
        text_mode = GRUB_CFG_SAMPLE.replace("\tload_video\n", "")
        self.assertFalse(entries_call_load_video(text_mode))


class EnvFileTest(unittest.TestCase):
    def setUp(self):
        if not shutil.which("grub-editenv"):
            self.skipTest("grub-editenv")
        self.dir = tempfile.mkdtemp()
        self.env = EnvFile(os.path.join(self.dir, "EFI/equestria-recovery/equestria-recovery.env"))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_cycle(self):
        self.env.create()
        self.assertEqual(os.path.getsize(self.env.path), 1024)     # GRUB пишет только поверх блока 1 КиБ
        self.env.set(eqrec_limit=2)
        self.env.set(eqrec_fails=2, equestria_recovery_once=1)
        self.assertEqual(self.env.values(), {"eqrec_limit": "2", "eqrec_fails": "2",
                                             "equestria_recovery_once": "1"})
        self.assertTrue(self.env.unset("eqrec_fails", "equestria_recovery_once", "absent"))
        self.assertFalse(self.env.unset("eqrec_fails"))            # уже нет — ничего не делает
        self.assertEqual(self.env.values(), {"eqrec_limit": "2"})
        self.env.remove()
        self.assertFalse(os.path.exists(os.path.dirname(self.env.path)))


class LiveMediumTest(unittest.TestCase):
    @staticmethod
    def head(gpt_backup_lba=None, iso_blocks=1000):
        data = bytearray(20 * 2048)
        if gpt_backup_lba is not None:
            data[512:520] = b"EFI PART"
            data[512 + 32:512 + 40] = gpt_backup_lba.to_bytes(8, "little")
        if iso_blocks:
            data[16 * 2048 + 1:16 * 2048 + 6] = b"CD001"
            data[16 * 2048 + 80:16 * 2048 + 84] = iso_blocks.to_bytes(4, "little")
        return bytes(data)

    def test_size_from_gpt(self):
        # GPT описывает весь образ вместе с EFI-разделом после тома ISO 9660
        self.assertEqual(image_size_on_device(self.head(4999, 1000), 10 ** 9), 5000 * 512)

    def test_size_from_iso9660_without_gpt(self):
        self.assertEqual(image_size_on_device(self.head(None, 1000), 10 ** 9), 1000 * 2048)

    def test_not_iso(self):
        self.assertEqual(image_size_on_device(self.head(4999, 0), 10 ** 9), 0)
        self.assertEqual(image_size_on_device(bytes(20 * 2048), 10 ** 9), 0)

    def test_bigger_than_device(self):
        self.assertEqual(image_size_on_device(self.head(4999, 1000), 4000 * 512), 0)

    def test_real_iso_if_present(self):
        out = Path("/mnt/NewBaseD/FromSystem/equestria-out")
        isos = sorted(out.glob("equestria-os-*.iso")) if out.is_dir() else []
        if not isos:
            self.skipTest("нет собранных ISO")
        for iso in (isos[0], isos[-1]):
            with open(iso, "rb") as f:
                head = f.read(40960)
            self.assertEqual(image_size_on_device(head, iso.stat().st_size + 10 ** 9), iso.stat().st_size)


class RootfsVerifierTest(unittest.TestCase):
    def setUp(self):
        if not shutil.which("bsdtar"):
            self.skipTest("bsdtar")
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def make_iso(self, payload: bytes, recorded: bytes | None) -> str:
        tree = self.dir / "tree"
        (tree / "arch/x86_64").mkdir(parents=True, exist_ok=True)
        (tree / "arch/x86_64/airootfs.sfs").write_bytes(payload)
        if recorded is not None:
            digest = hashlib.sha512(recorded).hexdigest()
            (tree / "arch/x86_64/airootfs.sha512").write_text(f"{digest}  airootfs.sfs\n")
        iso = self.dir / "t.iso"
        subprocess.run(["bsdtar", "--format", "iso9660", "-cf", str(iso), "-C", str(tree), "arch"], check=True)
        shutil.rmtree(tree)
        return str(iso)

    def test_intact(self):
        self.assertIs(RootfsVerifier().verify(self.make_iso(b"system" * 1000, b"system" * 1000)), True)

    def test_damaged(self):
        self.assertIs(RootfsVerifier().verify(self.make_iso(b"system" * 1000, b"other" * 1000)), False)

    def test_no_checksum(self):
        self.assertIsNone(RootfsVerifier().verify(self.make_iso(b"system", None)))


class StorageTest(unittest.TestCase):
    def test_key_for_dir(self):
        self.assertEqual(StorageLocations.key_for_dir(""), "default")
        self.assertEqual(StorageLocations.key_for_dir("/var/lib/equestria-recovery/"), "default")
        self.assertEqual(StorageLocations.key_for_dir("/mnt/Main/.equestria-recovery"), "/mnt/Main")

    def test_default_first(self):
        locs = StorageLocations().all()
        self.assertTrue(locs and locs[0].key == "default" and locs[0].system)
        self.assertEqual(len({x.uuid for x in locs}), len(locs))     # один раздел — одна строка
        for loc in locs[1:]:
            self.assertNotIn(loc.mount, ("/boot", "/boot/efi", "/efi", "/tmp"))


# ── лента и загрузка ─────────────────────────────────────────────────────────

FEED = b"""<?xml version="1.0"?><rss xmlns:media="http://video.search.yahoo.com/mrss/"><channel>
<item><title><![CDATA[/README.md]]></title><media:content filesize="10"><media:hash algo="md5">x</media:hash></media:content></item>
<item><title><![CDATA[/equestria-os-2026.10.28-x86_64.iso]]></title><media:content filesize="5"><media:hash algo="md5">AA</media:hash></media:content></item>
<item><title><![CDATA[/equestria-os-2026.11.05-x86_64.iso]]></title><media:content filesize="7"><media:hash algo="md5">BB</media:hash></media:content></item>
</channel></rss>"""


class FeedTest(unittest.TestCase):
    def test_parse_only_isos(self):
        rel = ReleaseFeed.parse(FEED)
        self.assertEqual([r.version for r in rel], ["2026.10.28", "2026.11.05"])
        self.assertEqual(rel[1].md5, "bb")

    def test_bad_feed(self):
        with self.assertRaises(SourceError):
            ReleaseFeed.parse(b"<rss><oops")

    def test_version_from_filename(self):
        self.assertEqual(version_from_filename("equestria-os-2026.11.05-x86_64.iso"), "2026.11.05")
        self.assertEqual(version_from_filename("other.iso"), "")


class RangeHandler(http.server.BaseHTTPRequestHandler):
    payload = b""
    fail_after = None          # оборвать соединение после стольких байт

    def log_message(self, *a):
        pass

    def do_GET(self):
        data, start = self.payload, 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.fail_after is not None and not rng:
            self.wfile.write(body[:self.fail_after])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(body)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = os.urandom(3 * 1024 * 1024 + 123)
        RangeHandler.payload = self.data
        RangeHandler.fail_after = None
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        shutil.rmtree(self.tmp)

    def release(self, md5=None):
        port = self.server.server_address[1]
        rel = Release("equestria-os-2026.11.05-x86_64.iso", "2026.11.05", len(self.data),
                      md5 if md5 is not None else hashlib.md5(self.data).hexdigest())
        Release.url = property(lambda self: f"http://127.0.0.1:{port}/iso")
        return rel

    def test_full_download(self):
        path = Downloader(self.release(), self.tmp).run()
        self.assertEqual(path.read_bytes(), self.data)

    def test_resume_after_break(self):
        RangeHandler.fail_after = 1024 * 1024
        d = Downloader(self.release(), self.tmp)
        with self.assertRaises(SourceError) as cm:
            d.run()
        self.assertEqual(cm.exception.args[0], "error.incomplete")
        self.assertEqual(d.part_path.stat().st_size, 1024 * 1024)
        RangeHandler.fail_after = None
        self.assertEqual(d.run().read_bytes(), self.data)   # докачка с середины

    def test_checksum_mismatch_deletes(self):
        d = Downloader(self.release(md5="0" * 32), self.tmp)
        with self.assertRaises(SourceError) as cm:
            d.run()
        self.assertEqual(cm.exception.args[0], "error.checksum")
        self.assertFalse(d.part_path.exists())
        self.assertFalse(d.final_path.exists())

    def test_cancel(self):
        d = Downloader(self.release(), self.tmp)
        with self.assertRaises(SourceError) as cm:
            d.run(cancelled=lambda: True)
        self.assertEqual(cm.exception.args[0], "error.cancelled")


# ── движок ремонта на поддельной системе ─────────────────────────────────────

class FakeTarget(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        rescue.RESCUE_MNT = str(self.root)
        mod = self.root / "usr/lib/modules/6.18.65-1-lts"
        mod.mkdir(parents=True)
        (mod / "pkgbase").write_text("linux-lts\n")
        (mod / "vmlinuz").write_bytes(b"K" * 4096)
        (mod / "modules.dep").write_text("")
        (self.root / "boot").mkdir()
        (self.root / "boot/vmlinuz-linux-lts").write_bytes(b"K" * 4096)
        good = Path("/tmp/claude-1000/-mnt-NewBaseD-FromSystem-Git-Projects/58ec26a8-ba18-4242-8bf3-040bc20b8aa0/scratchpad/iso/arch/boot/x86_64/initramfs-linux-lts.img")
        self.good_initrd = good if good.exists() else None
        if self.good_initrd:
            shutil.copy(good, self.root / "boot/initramfs-linux-lts.img")
            os.chmod(self.root / "boot/initramfs-linux-lts.img", 0o644)
        (self.root / "var/lib/pacman").mkdir(parents=True)
        self.state = rescue.TargetState(device="/dev/x", fstype="ext4", mounted=["/"])

    def tearDown(self):
        shutil.rmtree(self.root)

    def keys(self, check):
        return [p.key for p in check.run(self.state)]

    def test_healthy_kernel(self):
        if not self.good_initrd:
            self.skipTest("нет извлечённого initramfs")
        self.assertEqual(self.keys(rescue.KernelCheck()), [])

    def test_truncated_initramfs(self):
        img = self.root / "boot/initramfs-linux-lts.img"
        img.write_bytes(img.read_bytes()[:20_000_000] if self.good_initrd else b"x" * 2_000_000)
        self.assertIn("problem.initramfs_broken", self.keys(rescue.KernelCheck()))

    def test_missing_initramfs_and_kernel(self):
        (self.root / "boot/vmlinuz-linux-lts").unlink()
        (self.root / "boot/initramfs-linux-lts.img").unlink(missing_ok=True)
        keys = self.keys(rescue.KernelCheck())
        self.assertIn("problem.kernel_missing", keys)
        self.assertIn("problem.initramfs_missing", keys)

    def test_kernel_hole(self):   # тот самый btrfs-случай: хвост ядра обнулён
        (self.root / "boot/vmlinuz-linux-lts").write_bytes(b"K" * 2048 + b"\0" * 2048)
        self.assertIn("problem.kernel_mismatch", self.keys(rescue.KernelCheck()))

    def test_modules_dep(self):
        (self.root / "usr/lib/modules/6.18.65-1-lts/modules.dep").unlink()
        self.assertIn("problem.modules_broken", self.keys(rescue.KernelCheck()))

    def test_pacman_lock(self):
        self.assertEqual(self.keys(rescue.PacmanLockCheck()), [])
        (self.root / "var/lib/pacman/db.lck").write_text("")
        self.assertEqual(self.keys(rescue.PacmanLockCheck()), ["problem.pacman_lock"])

    def test_mount_failed(self):
        self.assertEqual(self.keys(rescue.MountCheck()), [])
        self.state.failed = ["/boot"]
        self.assertEqual(self.keys(rescue.MountCheck()), ["problem.mount_failed"])

    def test_bootloader_not_grub_ignored(self):
        self.assertEqual(self.keys(rescue.BootloaderCheck()), [])
        (self.root / "var/lib/pacman/local/grub-2:2.14-1").mkdir(parents=True)
        self.assertIn("problem.grub_cfg", self.keys(rescue.BootloaderCheck()))
        (self.root / "boot/grub").mkdir()
        (self.root / "boot/grub/grub.cfg").write_text("menuentry x {}\n")
        self.assertNotIn("problem.grub_cfg", self.keys(rescue.BootloaderCheck()))

    def test_package_files_parse(self):
        out = ("warning: linux-lts: /usr/lib/modules/6.18.65-1-lts/kernel/x.ko.zst (No such file or directory)\n"
               "warning: foo: /usr/share/man/man1/foo.1.gz (No such file or directory)\n"
               "warning: aurpkg: /usr/bin/aurpkg (No such file or directory)\n")
        calls = {"pacman -Qk": out, "pacman -Qmq": "aurpkg\n", "pacman -Dk": ""}

        def fake(*cmd):
            return subprocess.CompletedProcess(cmd, 0, calls.get(" ".join(cmd), ""), "")
        old = rescue.chroot_capture
        rescue.chroot_capture = fake
        try:
            problems = rescue.PackageFilesCheck().run(self.state)
        finally:
            rescue.chroot_capture = old
        by_key = {p.key: p for p in problems}
        self.assertEqual(by_key["problem.files_missing"].fix_args, ["linux-lts"])   # man-страницы не в счёт
        self.assertIn("problem.foreign_broken", by_key)

    def test_fstab(self):
        fstab = ("UUID=a / btrfs rw,subvol=/@,compress=zstd 0 0\n# comment\n"
                 "UUID=b /boot/efi vfat umask=0077 0 2\n")
        entries = rescue.parse_fstab(fstab)
        self.assertEqual([e["mp"] for e in entries], ["/", "/boot/efi"])
        self.assertEqual(rescue.subvol_of(entries[0]["opts"]), "@")


if __name__ == "__main__":
    unittest.main(verbosity=2)
