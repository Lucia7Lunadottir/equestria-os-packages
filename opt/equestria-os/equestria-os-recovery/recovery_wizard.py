"""
Мастер восстановления в live-среде.

Шаги (QStackedWidget):
  StartPage    — что это и кнопка «Найти мою систему»;
  ChoosePage   — найденные системы, «сначала проверить диск»;
  RepairPage   — найденные поломки с кнопками «Исправить», «Исправить всё»
                 и инструменты (пересобрать загрузку, GRUB, обновление, терминал…).
Под шагами — журнал команд (кнопка «Подробности»).

Всё, что требует root, делает recovery_rescue.py через sudo (PrivilegedTask);
окно только показывает результат. Порядок вызовов задаёт RescueWizard.
"""
import os
import shutil
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QHBoxLayout, QMessageBox, QPlainTextEdit, QProgressBar,
    QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
)

from recovery_paths import RESCUE_MNT, booted_for_recovery, recovery_reason
from recovery_widgets import (
    Card, PageWindow, PrivilegedTask, button, human_size, json_result, label, row, rescue_cmd,
    error_text, t,
)

# Исправления, перед которыми спрашиваем (удаляют файлы или долго идут через интернет)
CONFIRM = {"clean-cache": "confirm.clean_cache", "remove-fallback": "confirm.remove_fallback",
           "reinstall": "confirm.reinstall", "finish-update": "confirm.finish_update",
           "repair-grub": "confirm.repair_grub"}
NETWORK = ("reinstall", "finish-update")
# в каком порядке чинить «всё сразу»: сначала то, без чего не работает остальное
FIX_ORDER = ("unlock", "clean-cache", "remove-fallback", "reinstall", "finish-update",
             "rebuild-boot", "repair-grub")


class StartPage(QWidget):
    def __init__(self, wizard):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.card = Card("start.title")
        self.text = label(name="FieldHint")
        self.find_btn = button("", wizard.scan, "PrimaryBtn")
        self.card.body.addWidget(self.text)
        self.card.body.addLayout(row(self.find_btn))
        lay.addWidget(self.card)
        lay.addStretch()          # карточка по содержимому, а не на всю высоту окна

    def retranslate(self):
        self.card.retranslate()
        if not booted_for_recovery():
            key = "start.text"
        elif recovery_reason() == "auto":
            key = "start.text_auto"      # GRUB открыл сам: система не загрузилась несколько раз подряд
        else:
            key = "start.text_recovery"
        self.text.setText(t(key))
        self.find_btn.setText(t("action.find_system"))


class ChoosePage(QWidget):
    def __init__(self, wizard):
        super().__init__()
        self.wizard = wizard
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.card = Card("choose.title")
        self.list_box = QVBoxLayout()
        self.empty = label(name="FieldHint")
        self.fsck = QCheckBox()
        self.fsck.setChecked(True)   # после сбоя питания это первое, что нужно проверить
        self.fsck_hint = label(name="FieldHint")
        self.next_btn = button("", self._next, "PrimaryBtn")
        self.rescan_btn = button("", wizard.scan)
        self.card.body.addLayout(self.list_box)
        self.card.body.addWidget(self.empty)
        self.card.body.addWidget(self.fsck)
        self.card.body.addWidget(self.fsck_hint)
        self.card.body.addLayout(row(self.next_btn, self.rescan_btn))
        lay.addWidget(self.card)
        lay.addStretch()          # карточка по содержимому, а не на всю высоту окна
        self.group = QButtonGroup(self)
        self.group.idToggled.connect(lambda *_: self._sync())
        self.systems = []

    def load(self, systems):
        for b in self.group.buttons():
            self.group.removeButton(b)
            b.deleteLater()
        self.systems = systems
        for i, s in enumerate(systems):
            rb = QRadioButton()
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(rb, i)
            self.list_box.addWidget(rb)
        if systems:
            self.group.button(0).setChecked(True)
        self.retranslate()

    def selected(self):
        i = self.group.checkedId()
        return self.systems[i] if 0 <= i < len(self.systems) else None

    def _sync(self):
        s = self.selected()
        self.next_btn.setEnabled(s is not None)
        busy = bool(s and s["busy"])
        self.fsck.setEnabled(not busy)
        if busy:
            self.fsck.setChecked(False)
        self.fsck_hint.setText(t("choose.fsck_busy") if busy else t("choose.fsck_hint"))

    def _next(self):
        s = self.selected()
        if s:
            self.wizard.open_system(s, self.fsck.isChecked())

    def retranslate(self):
        self.card.retranslate()
        for i, s in enumerate(self.systems):
            where = s["device"] + (f" [{s['subvol']}]" if s["subvol"] else "")
            self.group.button(i).setText(t("choose.item", s["name"] or "Linux", where,
                                           s["fstype"], human_size(s["size"])))
        self.empty.setText(t("choose.none"))
        self.empty.setVisible(not self.systems)
        self.fsck.setText(t("choose.fsck"))
        self.fsck.setVisible(bool(self.systems))
        self.fsck_hint.setVisible(bool(self.systems))
        self.next_btn.setText(t("action.continue"))
        self.next_btn.setVisible(bool(self.systems))
        self.rescan_btn.setText(t("action.rescan"))
        self._sync()


class ProblemRow(QWidget):
    def __init__(self, problem, on_fix):
        super().__init__()
        self.problem = problem
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        mark = "⚠" if problem["severity"] == "warning" else "✖"
        self.text = label(name="FieldLabel")
        self.mark = label(mark, name="FieldLabel", wrap=False)
        self.fix_btn = button("", lambda: on_fix(problem["fix"], problem["fix_args"]))
        self.fix_btn.setVisible(bool(problem["fix"]))
        lay.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.fix_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.retranslate()

    def retranslate(self):
        self.text.setText(t(self.problem["key"], *self.problem["args"]))
        self.fix_btn.setText(t("action.fix"))


class RepairPage(QWidget):
    def __init__(self, wizard):
        super().__init__()
        self.wizard = wizard
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.result = Card("repair.title")
        self.summary = label(name="FieldLabel")
        self.rows_box = QVBoxLayout()
        self.fix_all_btn = button("", wizard.fix_all, "PrimaryBtn")
        self.recheck_btn = button("", wizard.diagnose)
        self.result.body.addWidget(self.summary)
        self.result.body.addLayout(self.rows_box)
        self.result.body.addLayout(row(self.fix_all_btn, self.recheck_btn))
        lay.addWidget(self.result)

        self.tools = Card("tools.title")
        self.tools_hint = label(name="FieldHint")
        self.tools.body.addWidget(self.tools_hint)
        self.tool_buttons = {
            "rebuild-boot": button("", lambda: wizard.fix("rebuild-boot", [])),
            "repair-grub": button("", lambda: wizard.fix("repair-grub", [])),
            "finish-update": button("", lambda: wizard.fix("finish-update", [])),
            "terminal": button("", wizard.open_terminal),
            "files": button("", wizard.open_files),
            "reinstall": button("", wizard.reinstall, "DeleteBtn"),
            "reboot": button("", wizard.reboot, "PrimaryBtn"),
        }
        b = self.tool_buttons
        self.tools.body.addLayout(row(b["rebuild-boot"], b["repair-grub"], b["finish-update"]))
        self.tools.body.addLayout(row(b["terminal"], b["files"]))
        self.reinstall_hint = label(name="FieldHint")
        self.tools.body.addLayout(row(b["reinstall"]))
        self.tools.body.addWidget(self.reinstall_hint)
        self.tools.body.addLayout(row(b["reboot"]))
        lay.addWidget(self.tools)
        lay.addStretch()
        self.rows = []
        self.problems = []

    def load(self, problems):
        for r in self.rows:
            r.deleteLater()
        self.problems = problems
        self.rows = [ProblemRow(p, self.wizard.fix) for p in problems]
        for r in self.rows:
            self.rows_box.addWidget(r)
        self.retranslate()

    def retranslate(self):
        self.result.retranslate()
        self.tools.retranslate()
        errors = [p for p in self.problems if p["severity"] == "error"]
        fixable = [p for p in self.problems if p["fix"]]
        self.summary.setText(t("repair.none") if not self.problems else
                             t("repair.found", len(self.problems)) if errors else t("repair.warnings_only"))
        self.fix_all_btn.setText(t("action.fix_all"))
        self.fix_all_btn.setVisible(bool(fixable))
        self.recheck_btn.setText(t("action.recheck"))
        for r in self.rows:
            r.retranslate()
        self.tools_hint.setText(t("tools.hint", RESCUE_MNT))
        for key, btn in self.tool_buttons.items():
            btn.setText(t(f"tool.{key}"))
        can_reinstall = self.wizard.can_reinstall()
        self.tool_buttons["reinstall"].setEnabled(can_reinstall)
        self.reinstall_hint.setText(t("tools.reinstall_hint" if can_reinstall else "tools.reinstall_blocked"))


class RescueWizard(PageWindow):
    title_key = "wizard.title"
    desc_key = "wizard.desc"

    def __init__(self):
        super().__init__()
        self.task = None
        self.system = None
        self.queue = []

        self.stack = QStackedWidget()
        self.start_page = StartPage(self)
        self.choose_page = ChoosePage(self)
        self.repair_page = RepairPage(self)
        for p in (self.start_page, self.choose_page, self.repair_page):
            self.stack.addWidget(p)
        self.content.addWidget(self.stack)

        self.busy_lbl = label(name="FieldHint")
        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setFixedHeight(6)
        self.busy_bar.setTextVisible(False)
        self.content.addWidget(self.busy_lbl)
        self.content.addWidget(self.busy_bar)

        self.log_btn = button("", self._toggle_log, "OpenAppBtn")
        self.log_btn.setCheckable(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(220)
        self.log.setVisible(False)
        self.content.addLayout(row(self.log_btn))
        self.content.addWidget(self.log)
        self.content.addStretch()
        self._set_busy("")
        self.retranslate()

    # ── общее ────────────────────────────────────────────────────────────────

    def retranslate(self):
        super().retranslate()
        for p in (self.start_page, self.choose_page, self.repair_page):
            p.retranslate()
        self.log_btn.setText(t("log.hide" if self.log_btn.isChecked() else "log.show"))

    def _toggle_log(self, shown):
        self.log.setVisible(shown)
        self.log_btn.setText(t("log.hide" if shown else "log.show"))

    def _set_busy(self, text):
        busy = bool(text)
        self.busy_lbl.setText(text)
        self.busy_lbl.setVisible(busy)
        self.busy_bar.setVisible(busy)
        self.stack.setEnabled(not busy)

    def _rescue(self, args, busy_text, on_done):
        """Запустить rescue-команду; on_done(код, stdout, stderr)."""
        self._set_busy(busy_text)
        self.log.appendPlainText(f"▶ {' '.join(args)}")
        self.task = PrivilegedTask(rescue_cmd(*args), self)
        self.task.line.connect(lambda ln: None if ln.startswith("json ") else self.log.appendPlainText(ln))

        def finished(code, out, err):
            self._set_busy("")
            if err.strip():
                self.log.appendPlainText(err.strip())
            on_done(code, out, err)
        self.task.done.connect(finished)
        self.task.start()

    def _fail(self, err):
        QMessageBox.critical(self, t("wizard.title"), error_text(err))

    # ── шаги ─────────────────────────────────────────────────────────────────

    def scan(self):
        def done(code, out, err):
            if code != 0:
                return self._fail(err)
            self.choose_page.load(json_result(out) or [])
            self.stack.setCurrentWidget(self.choose_page)
        self._rescue(["scan"], t("busy.scan"), done)

    def open_system(self, system, check_fs):
        self.system = system
        if check_fs:
            self._fscheck(repair=False)
        else:
            self._mount()

    def _fscheck(self, repair):
        args = ["fscheck", self.system["device"]] + (["--repair"] if repair else [])

        def done(code, out, err):
            if code in (0, 1):
                if code == 1:
                    QMessageBox.information(self, t("wizard.title"), t("done.fs_repaired"))
                return self._mount()
            if code == 4 and not repair:
                if self.system["fstype"] == "btrfs":
                    QMessageBox.warning(self, t("wizard.title"), t("fs.btrfs_errors"))
                    return self._mount()
                if QMessageBox.question(self, t("wizard.title"), t("confirm.fs_repair")) == \
                        QMessageBox.StandardButton.Yes:
                    return self._fscheck(repair=True)
                return
            self._fail(err or t("error.fs_failed"))
        self._rescue(args, t("busy.fscheck"), done)

    def _mount(self):
        args = ["mount", self.system["device"]] + (["--subvol", self.system["subvol"]]
                                                   if self.system["subvol"] else [])

        def done(code, out, err):
            if code != 0:
                return self._fail(err)
            self.stack.setCurrentWidget(self.repair_page)
            self.diagnose()
        self._rescue(args, t("busy.mount"), done)

    def diagnose(self):
        def done(code, out, err):
            if code != 0:
                return self._fail(err)
            self.repair_page.load(json_result(out) or [])
        self._rescue(["diagnose"], t("busy.diagnose"), done)

    # ── исправления ──────────────────────────────────────────────────────────

    def _confirm(self, fix_ids) -> bool:
        notes = [t(CONFIRM[f]) for f in fix_ids if f in CONFIRM]
        if any(f in NETWORK for f in fix_ids):
            notes.append(t("confirm.network"))
        if not notes:
            return True
        return QMessageBox.question(self, t("wizard.title"), "\n\n".join(notes)) == \
            QMessageBox.StandardButton.Yes

    def fix(self, fix_id, args):
        if not self._confirm([fix_id]):
            return
        self._run_fix(fix_id, args, then=self.diagnose)

    def fix_all(self):
        planned = {}
        for p in self.repair_page.problems:
            if p["fix"]:
                planned.setdefault(p["fix"], [])
                planned[p["fix"]] += [a for a in p["fix_args"] if a not in planned[p["fix"]]]
        # полное обновление уже включает переустановку пакетов
        if "reinstall" in planned and "finish-update" in planned:
            planned.pop("finish-update")
        ordered = [(f, planned[f]) for f in FIX_ORDER if f in planned]
        if not ordered or not self._confirm([f for f, _ in ordered]):
            return
        self.queue = ordered
        self._next_in_queue()

    def _next_in_queue(self):
        if not self.queue:
            return
        fix_id, args = self.queue.pop(0)
        if not self.queue:
            self._run_fix(fix_id, args, then=self._after_all)
        else:
            self._run_fix(fix_id, args, then=self._next_in_queue)

    def _after_all(self):
        self.diagnose()

    def _run_fix(self, fix_id, args, then):
        def done(code, out, err):
            if code != 0:
                self.queue = []
                self.log_btn.setChecked(True)
                self._toggle_log(True)
                details = "\n" + error_text(err) if err.strip() else ""
                QMessageBox.warning(self, t("wizard.title"),
                                    t("error.fix_failed", t(f"fixname.{fix_id}")) + details)
                return self.diagnose()
            then()
        self._rescue(["fix", fix_id, *args], t("busy.fix", t(f"fixname.{fix_id}")), done)

    # ── инструменты ──────────────────────────────────────────────────────────

    def open_terminal(self):
        term = shutil.which("konsole")
        if term:
            subprocess.Popen([term, "-e", "sudo", "arch-chroot", RESCUE_MNT])

    def open_files(self):
        target = os.path.join(RESCUE_MNT, "home")
        subprocess.Popen(["xdg-open", target if os.path.isdir(target) else RESCUE_MNT])

    def can_reinstall(self) -> bool:
        # без copytoram образ читается с раздела системы — переустановка его бы стёрла.
        # Если ISO лежит на другом разделе, системный раздел свободен.
        if self.system is not None:
            return not self.system["busy"]
        return not booted_for_recovery() or os.path.isdir("/run/archiso/copytoram")

    def reinstall(self):
        if QMessageBox.question(self, t("wizard.title"), t("confirm.reinstall_system")) != \
                QMessageBox.StandardButton.Yes:
            return

        def done(code, out, err):
            installer = "/usr/local/bin/install-equestria.sh"
            cmd = ["sudo", installer] if os.path.isfile(installer) else ["sudo", "-E", "calamares"]
            subprocess.Popen(cmd)
        self._rescue(["umount"], t("busy.umount"), done)

    def reboot(self):
        def done(code, out, err):
            if code != 0 and QMessageBox.question(self, t("wizard.title"), t("confirm.reboot_anyway")) != \
                    QMessageBox.StandardButton.Yes:
                return
            subprocess.Popen(["systemctl", "reboot"])
        self._rescue(["umount"], t("busy.umount"), done)
