"""
Счётчик неудачных загрузок в настоящем GRUB (QEMU + OVMF, без root, ~1 минута):

    python3 tests/vm_grub_counter.py

Диск — GPT с одним EFI-разделом (FAT). На нём GRUB (grub-mkstandalone), наш
equestria-recovery.cfg, отрисованный текущим кодом, и файл окружения. «Обычный» пункт,
как пункты 10_linux, вызывает load_video и выключает машину — то есть каждая загрузка
для GRUB «неудачная», пока тест сам (вместо службы boot-ok) не обнулит счётчик.

Проверяется в обе стороны: после FAIL_LIMIT неудач — восстановление (и меню видно),
удачная загрузка сбрасывает счёт, пункт без load_video (Windows) не считается,
разовый флаг срабатывает один раз, предел 0 выключает всё.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from recovery_grub import EntryRenderer, GrubPath          # noqa: E402
from recovery_image import IsoInfo                          # noqa: E402
from recovery_paths import FAIL_LIMIT                       # noqa: E402

OVMF_CODE = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
OVMF_VARS = "/usr/share/edk2/x64/OVMF_VARS.4m.fd"
ESP_UUID = "ABCD-1234"
ENV_REL = "/EFI/equestria-recovery/equestria-recovery.env"

MEM_CFG = r"""insmod part_gpt
insmod fat
set timeout=0
search --no-floppy --fs-uuid --set=esp ABCD-1234
function load_video {
  insmod efi_gop
}
menuentry "Normal" --id normal {
  load_video
  echo "ENTRY normal"
  sleep 1
  halt
}
menuentry "Windows" --id win {
  echo "ENTRY win"
  sleep 1
  halt
}
set default=normal
if [ -f "(${esp})/test.env" ]; then
  load_env --file "(${esp})/test.env" testdefault
  if [ -n "${testdefault}" ]; then set default="${testdefault}"; fi
fi
source "(${esp})/rec.cfg"
echo "DECIDE default=${default} reason=${eqrec_reason} timeout=${timeout} END"
sleep 1
"""


class Disk:
    def __init__(self, work: Path):
        self.work = work
        self.img = work / "disk.img"
        self.part = f"{self.img}@@1M"
        self.env = os.environ | {"MTOOLS_SKIP_CHECK": "1"}

    def mtools(self, *cmd):
        subprocess.run(cmd, check=True, env=self.env, capture_output=True)

    def build(self):
        w = self.work
        (w / "mem.cfg").write_text(MEM_CFG)
        subprocess.run(["grub-mkstandalone", "-O", "x86_64-efi", "-o", str(w / "BOOTX64.EFI"),
                        f"boot/grub/grub.cfg={w / 'mem.cfg'}"], check=True, capture_output=True)
        info = IsoInfo("t", "/arch/boot/x86_64/vmlinuz-linux-lts",
                       ["/arch/boot/x86_64/initramfs-linux-lts.img"], "", 1)
        rec = EntryRenderer().render(info, GrubPath(ESP_UUID, "fat", "/missing.iso"),
                                     {"ram": "Recovery", "noram": "N"}, ram=32 * 1024 ** 3,
                                     env=GrubPath(ESP_UUID, "fat", ENV_REL), video_body="  insmod efi_gop")
        (w / "rec.cfg").write_text(rec)
        with open(self.img, "wb") as f:
            f.truncate(64 * 1024 * 1024)
        subprocess.run(["sfdisk", "-q", str(self.img)], check=True, text=True,
                       input="label: gpt\nstart=2048, size=120000, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B\n")
        subprocess.run(["mkfs.fat", "--offset", "2048", "-i", ESP_UUID.replace("-", ""), str(self.img), "60000"],
                       check=True, capture_output=True)
        self.mtools("mmd", "-i", self.part, "::/EFI", "::/EFI/BOOT", "::/EFI/equestria-recovery")
        self.mtools("mcopy", "-i", self.part, str(w / "BOOTX64.EFI"), "::/EFI/BOOT/")
        self.mtools("mcopy", "-i", self.part, str(w / "rec.cfg"), "::/")
        shutil.copy(OVMF_VARS, w / "vars.fd")

    # файл окружения: читаем/пишем через локальную копию и grub-editenv (как бэкенд)
    def editenv(self, *args):
        local = self.work / "env"
        try:
            self.mtools("mcopy", "-o", "-i", self.part, f"::{ENV_REL}", str(local))
        except subprocess.CalledProcessError:
            subprocess.run(["grub-editenv", str(local), "create"], check=True)
        if args:
            subprocess.run(["grub-editenv", str(local), *args], check=True)
            self.mtools("mcopy", "-o", "-i", self.part, str(local), f"::{ENV_REL}")
        out = subprocess.run(["grub-editenv", str(local), "list"], capture_output=True, text=True).stdout
        return {k: v for k, v in (ln.split("=", 1) for ln in out.splitlines() if "=" in ln) if v}

    def test_default(self, entry_id: str | None):
        if entry_id is None:
            self.mtools("mdel", "-i", self.part, "::/test.env")
            return
        t = self.work / "t.env"
        subprocess.run(["grub-editenv", str(t), "create"], check=True)
        subprocess.run(["grub-editenv", str(t), "set", f"testdefault={entry_id}"], check=True)
        self.mtools("mcopy", "-o", "-i", self.part, str(t), "::/test.env")

    def boot(self) -> dict:
        """Одна загрузка. {'default':…, 'reason':…, 'timeout':…, 'entry':…}"""
        r = subprocess.run(
            ["timeout", "25", "qemu-system-x86_64", "-machine", "q35", "-m", "256", "-nographic",
             "-no-reboot", "-net", "none",
             "-drive", f"if=pflash,format=raw,readonly=on,file={OVMF_CODE}",
             "-drive", f"if=pflash,format=raw,file={self.work / 'vars.fd'}",
             "-drive", f"file={self.img},format=raw,if=virtio"],
            capture_output=True)
        text = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", r.stdout.decode("utf-8", "replace")).replace("\r", "")
        m = re.search(r"DECIDE default=(\S*) reason=(\S*) timeout=(\S*) END", text)
        if not m:
            raise AssertionError("GRUB ничего не решил:\n" + text[-2000:])
        e = re.search(r"ENTRY (\w+)", text)
        return {"default": m.group(1), "reason": m.group(2), "timeout": m.group(3),
                "entry": e.group(1) if e else ""}


def check(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def main() -> int:
    for tool in ("qemu-system-x86_64", "grub-mkstandalone", "grub-editenv", "mcopy", "sfdisk", "mkfs.fat"):
        if not shutil.which(tool):
            print("skip: нет", tool)
            return 0
    if not os.path.isfile(OVMF_CODE):
        print("skip: нет OVMF")
        return 0
    work = Path(tempfile.mkdtemp(prefix="eqrec-grubvm-"))
    try:
        d = Disk(work)
        d.build()
        d.editenv("set", f"eqrec_limit={FAIL_LIMIT}")

        print(f"1. {FAIL_LIMIT} неудачные загрузки подряд → восстановление")
        for n in range(1, FAIL_LIMIT + 1):
            b = d.boot()
            check(b["entry"] == "normal" and d.editenv().get("eqrec_fails") == str(n),
                  f"загрузка {n}: обычный пункт, счётчик {n}")
        b = d.boot()
        check(b["default"] == "equestria-recovery" and b["reason"] == "auto", "дальше GRUB сам выбрал восстановление")
        check(b["timeout"] == "10", "меню показано (timeout 0 → 10)")
        check("eqrec_fails" not in d.editenv(), "пункт восстановления сбросил счётчик")
        check(d.boot()["entry"] == "normal", "следующая загрузка — снова обычная")

        print("2. удачная загрузка сбрасывает счёт")
        d.editenv("unset", "eqrec_fails")                  # то, что делает служба boot-ok
        for _ in range(FAIL_LIMIT - 1):
            d.boot()
        d.editenv("unset", "eqrec_fails")
        b = d.boot()
        check(b["entry"] == "normal" and d.editenv().get("eqrec_fails") == "1", "считаем с нуля")

        print("3. Windows (пункт без load_video) не считается")
        d.editenv("unset", "eqrec_fails")
        d.test_default("win")
        for _ in range(FAIL_LIMIT + 1):
            b = d.boot()
        check(b["entry"] == "win" and "eqrec_fails" not in d.editenv(), f"{FAIL_LIMIT + 1} загрузки Windows — счётчик пуст")
        d.test_default(None)

        print("4. разовый переход")
        d.editenv("set", "equestria_recovery_once=1")
        b = d.boot()
        check(b["default"] == "equestria-recovery" and b["reason"] == "manual", "в восстановление по кнопке")
        check("equestria_recovery_once" not in d.editenv(), "флаг стёрт самим GRUB")
        check(d.boot()["entry"] == "normal", "следующая загрузка — обычная")

        print("5. предел 0 — выключено")
        d.editenv("set", "eqrec_limit=0")
        d.editenv("unset", "eqrec_fails")
        for _ in range(FAIL_LIMIT + 1):
            b = d.boot()
        check(b["entry"] == "normal" and "eqrec_fails" not in d.editenv(), "не считает и не переключает")
        print("всё прошло")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
