"""
Окно установленной системы: держит наготове образ восстановления.

Карточки:
  StatusCard   — установлен ли образ, версия, есть ли пункт в GRUB, хватает ли памяти;
  ImageCard    — скачать/обновить с SourceForge, взять свой ISO-файл, удалить,
                 где хранить (системный раздел или другой диск);
  RecoverCard  — как попасть в среду восстановления, «Перезагрузиться в неё»,
                 открывать ли её самой после неудачных загрузок.
В live-среде вместо этого показывается LiveCard — кнопка мастера восстановления.
"""
import os
import subprocess

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QMessageBox, QProgressBar

from recovery_paths import is_live, FAIL_LIMIT_WITH_SAVE_POINT
from recovery_image import ImageStatus
from recovery_grub import GrubIntegration
from recovery_storage import StorageLocations
from recovery_backend import fail_limit
from recovery_source import Downloader, ReleaseFeed, SourceError
from recovery_widgets import (
    CATALOG, Card, PageWindow, PrivilegedTask, backend_cmd, button, error_text,
    human_size, label, number, row, t,
)


# ── фоновые потоки ───────────────────────────────────────────────────────────

class FeedThread(QThread):
    found = pyqtSignal(object)        # Release или None
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.found.emit(ReleaseFeed().latest())
        except SourceError as e:
            self.failed.emit(t(e.args[0]))


class DownloadThread(QThread):
    progress = pyqtSignal(int, int)
    ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, release):
        super().__init__()
        self.downloader = Downloader(release)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            path = self.downloader.run(lambda d, total: self.progress.emit(d // 1048576, total // 1048576),
                                       lambda: self._cancel)
            self.ready.emit(str(path))
        except SourceError as e:
            key = e.args[0]
            detail = f"\n{e.args[1]}" if len(e.args) > 1 and key != "error.no_space" else ""
            self.failed.emit("" if key == "error.cancelled" else t(key) + detail)
        except OSError as e:
            self.failed.emit(f"{t('error.os')}\n{e}")


# ── карточки ─────────────────────────────────────────────────────────────────

class StatusCard(Card):
    def __init__(self):
        super().__init__("card.status")
        self.state_lbl = label(name="FieldLabel")
        self.detail_lbl = label(name="FieldHint")
        self.warn_lbl = label(name="FieldHint")
        self.body.addWidget(self.state_lbl)
        self.body.addWidget(self.detail_lbl)
        self.body.addWidget(self.warn_lbl)
        self.status = None
        self.release = None
        self.feed_error = ""

    def load(self, status: ImageStatus, release=None, feed_error=""):
        self.status, self.release, self.feed_error = status, release, feed_error
        self.retranslate()

    def retranslate(self):
        super().retranslate()
        s = self.status
        if s is None:
            return
        if s.location_missing:
            self.state_lbl.setText(t("status.location_missing", s.state.iso_dir))
            self.detail_lbl.setText(t("status.location_missing_hint"))
        elif not s.present:
            self.state_lbl.setText(t("status.not_installed"))
            self.detail_lbl.setText(t("status.not_installed_hint"))
        elif not s.ready:
            self.state_lbl.setText(t("status.no_entry"))
            self.detail_lbl.setText(t(s.state.grub_error) if s.state.grub_error else t("status.no_entry_hint"))
        else:
            self.state_lbl.setText(t("status.ready", s.state.version or "?"))
            self.detail_lbl.setText(t("status.ready_detail", human_size(s.file_size), s.state.iso_path))
        notes = []
        if s.present and not s.copies_to_ram:
            notes.append(t("status.low_ram", human_size(s.ram, binary=True)))
        if self.release and s.present and self.release.version > (s.state.version or ""):
            notes.append(t("status.update_available", self.release.version))
        elif self.release and not s.present:
            notes.append(t("status.latest", self.release.version, human_size(self.release.size)))
        if self.feed_error:
            notes.append(t("status.feed_error", self.feed_error))
        self.warn_lbl.setText("\n".join(notes))
        self.warn_lbl.setVisible(bool(notes))


class ImageCard(Card):
    def __init__(self, window: "RecoveryManagerApp"):
        super().__init__("card.image")
        self.win = window
        self.hint = label(name="FieldHint")
        self.download_btn = button("", window.download, "PrimaryBtn")
        self.file_btn = button("", window.choose_file)
        self.remove_btn = button("", window.remove, "DeleteBtn")
        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress_lbl = label(name="FieldHint")
        self.cancel_btn = button("", window.cancel_download)
        self.location_lbl = label(name="FieldLabel", wrap=False)
        self.location_combo = QComboBox()
        self.location_combo.activated.connect(lambda i: window.change_location(self.location_combo.itemData(i)))
        self.location_hint = label(name="FieldHint")
        self.locations = []
        self.body.addWidget(self.hint)
        self.body.addLayout(row(self.download_btn, self.file_btn, self.remove_btn))
        self.body.addLayout(row(self.location_lbl, self.location_combo))
        self.body.addWidget(self.location_hint)
        self.body.addWidget(self.progress_lbl)
        self.body.addWidget(self.progress)
        self.body.addLayout(row(self.cancel_btn))
        self.set_busy(False)

    def load_locations(self):
        self.locations = StorageLocations().all()
        self.retranslate_locations()

    def retranslate_locations(self):
        s = self.win.status
        current = StorageLocations.key_for_dir(s.state.iso_dir if s else "")
        self.location_combo.clear()
        for loc in self.locations:
            if loc.system:
                text = t("location.system", loc.mount, human_size(loc.free))
            elif loc.other_disk:
                text = t("location.other_disk", loc.mount, loc.fstype, human_size(loc.free))
            else:
                text = t("location.other", loc.mount, loc.fstype, human_size(loc.free))
            self.location_combo.addItem(text, loc.key)
        if s and s.location_missing:
            self.location_combo.addItem(s.state.iso_dir, current)
        idx = self.location_combo.findData(current)
        self.location_combo.setCurrentIndex(max(idx, 0))
        self.location_combo.setEnabled(len(self.locations) > 1)
        # совет — только если есть что выбрать, а образ сейчас на системном разделе
        on_system = current == "default"
        better = any(not loc.system and loc.other_disk for loc in self.locations)
        self.location_hint.setText(t("location.hint") if on_system and better else
                                   t("location.hint_done") if not on_system else "")
        self.location_hint.setVisible(bool(self.location_hint.text()))

    def set_busy(self, busy: bool, cancellable=False):
        self.location_combo.setEnabled(not busy and len(self.locations) > 1)
        for w in (self.download_btn, self.file_btn, self.remove_btn):
            w.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.progress_lbl.setVisible(busy)
        self.cancel_btn.setVisible(busy and cancellable)
        if not busy:
            self.update_buttons()

    def update_buttons(self):
        s, rel = self.win.status, self.win.release
        present = bool(s and s.present)
        newer = bool(rel and present and rel.version > (s.state.version or ""))
        self.download_btn.setText(t("action.update", rel.version) if newer else
                                  t("action.redownload") if present else t("action.download"))
        self.download_btn.setEnabled(not present or newer or not s.ready)
        self.remove_btn.setEnabled(present)

    def show_progress(self, done_mib, total_mib, text):
        self.progress.setRange(0, max(total_mib, 0))
        self.progress.setValue(done_mib if total_mib else 0)
        self.progress_lbl.setText(text)

    def retranslate(self):
        super().retranslate()
        self.hint.setText(t("image.hint"))
        self.file_btn.setText(t("action.choose_file"))
        self.remove_btn.setText(t("action.remove"))
        self.cancel_btn.setText(t("action.cancel"))
        self.location_lbl.setText(t("image.location"))
        self.retranslate_locations()
        self.update_buttons()


class RecoverCard(Card):
    def __init__(self, window: "RecoveryManagerApp"):
        super().__init__("card.recover")
        self.win = window
        self.how = label(name="FieldHint")
        self.reboot_btn = button("", window.reboot_to_recovery, "PrimaryBtn")
        self.reboot_hint = label(name="FieldHint")
        self.auto_box = QCheckBox()
        self.auto_box.clicked.connect(window.toggle_auto)
        self.auto_hint = label(name="FieldHint")
        self.body.addWidget(self.how)
        self.body.addLayout(row(self.reboot_btn))
        self.body.addWidget(self.reboot_hint)
        self.body.addWidget(self.auto_box)
        self.body.addWidget(self.auto_hint)
        self.supported = GrubIntegration.one_shot_supported()
        self.status = None
        self.limit = 0

    def load(self, status):
        self.status = status
        # пункт уже записан — верим тому, что проверил бэкенд (он читает grub.cfg от root)
        if status.ready:
            self.supported = status.state.one_shot_ok
        self.limit = fail_limit(status.state) if status.state.auto_fallback else 0
        self.reboot_btn.setEnabled(bool(status.ready and self.supported))
        self.retranslate()

    @property
    def auto_supported(self) -> bool:
        s = self.status
        return self.supported and not (s and s.ready and not s.state.auto_ok)

    def retranslate(self):
        super().retranslate()
        self.how.setText(t("recover.how"))
        self.reboot_btn.setText(t("action.reboot_recovery"))
        self.reboot_hint.setText("" if self.supported else t("recover.one_shot_unsupported"))
        self.reboot_hint.setVisible(not self.supported)
        s = self.status
        self.auto_box.setText(t("recover.auto"))
        self.auto_box.setEnabled(self.auto_supported)
        self.auto_box.setChecked(bool(s and s.state.auto_fallback and self.auto_supported))
        if not self.auto_supported:
            hint = t("recover.auto_unsupported")
        else:
            hint = t("recover.auto_hint")
            if self.auto_box.isChecked():
                hint += "\n" + (t("recover.auto_limit_save_point", self.limit)
                                if self.limit == FAIL_LIMIT_WITH_SAVE_POINT else
                                t("recover.auto_limit", self.limit))
        self.auto_hint.setText(hint)


class LiveCard(Card):
    def __init__(self):
        super().__init__("card.live")
        self.text = label(name="FieldHint")
        self.open_btn = button("", self._open, "PrimaryBtn")
        self.body.addWidget(self.text)
        self.body.addLayout(row(self.open_btn))

    def _open(self):
        from recovery_wizard import RescueWizard
        self._wizard = RescueWizard()
        self._wizard.show()

    def retranslate(self):
        super().retranslate()
        self.text.setText(t("live.hint"))
        self.open_btn.setText(t("action.open_wizard"))


# ── окно ─────────────────────────────────────────────────────────────────────

class RecoveryManagerApp(PageWindow):
    title_key = "app.title"
    desc_key = "app.desc"

    def __init__(self):
        super().__init__()
        self.status = ImageStatus.current()
        self.release = None
        self.feed_error = ""
        self.task = None
        self.download_thread = None
        self.cards = []
        if is_live():
            self.cards = [LiveCard()]
        else:
            self.status_card = StatusCard()
            self.image_card = ImageCard(self)
            self.recover_card = RecoverCard(self)
            self.cards = [self.status_card, self.image_card, self.recover_card]
        for card in self.cards:
            self.content.addWidget(card)
        self.content.addStretch()
        self.retranslate()
        if not is_live():
            self.reload()
            self.feed = FeedThread()
            self.feed.found.connect(self._on_release)
            self.feed.failed.connect(self._on_feed_error)
            self.feed.start()

    def retranslate(self):
        super().retranslate()
        for card in self.cards:
            card.retranslate()

    def reload(self):
        self.status = ImageStatus.current()
        self.status_card.load(self.status, self.release, self.feed_error)
        self.image_card.load_locations()
        self.image_card.update_buttons()
        self.recover_card.load(self.status)

    def _on_release(self, release):
        self.release = release
        self.reload()

    def _on_feed_error(self, text):
        self.feed_error = text
        self.reload()

    # ── действия ─────────────────────────────────────────────────────────────

    def download(self):
        if self.release is None:
            QMessageBox.warning(self, t("app.title"), self.feed_error or t("error.no_release"))
            return
        if QMessageBox.question(self, t("app.title"),
                                t("confirm.download", self.release.version, human_size(self.release.size))
                                ) != QMessageBox.StandardButton.Yes:
            return
        self.image_card.set_busy(True, cancellable=True)
        self.image_card.show_progress(0, 0, t("progress.downloading"))
        self.download_thread = DownloadThread(self.release)
        self.download_thread.progress.connect(
            lambda d, total: self.image_card.show_progress(
                d, total, t("progress.downloaded", number(d * 1048576 / 1e9, 2), number(total * 1048576 / 1e9, 2))))
        self.download_thread.ready.connect(self._on_downloaded)
        self.download_thread.failed.connect(self._on_download_failed)
        self.download_thread.start()

    def cancel_download(self):
        if self.download_thread:
            self.download_thread.cancel()

    def _on_download_failed(self, text):
        self.image_card.set_busy(False)
        if text:
            QMessageBox.critical(self, t("app.title"), text)

    def _on_downloaded(self, path):
        rel = self.release
        self._install(["install", path, "--move", "--md5", rel.md5, "--source", rel.name,
                       "--lang", CATALOG.lang])

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, t("action.choose_file"), os.path.expanduser("~"),
                                              t("dialog.iso_filter"))
        if path:
            # чужой файл: сверяем ещё и контрольную сумму системы внутри образа
            self._install(["install", path, "--verify", "--source", os.path.basename(path),
                           "--lang", CATALOG.lang])

    def _install(self, args):
        self.image_card.set_busy(True)
        self.image_card.show_progress(0, 0, t("progress.installing"))
        self._run(args, on_ok=lambda: QMessageBox.information(self, t("app.title"), t("done.installed")))

    def remove(self):
        if QMessageBox.question(self, t("app.title"), t("confirm.remove")) != QMessageBox.StandardButton.Yes:
            return
        self.image_card.set_busy(True)
        self.image_card.show_progress(0, 0, t("progress.removing"))
        self._run(["remove"])

    def change_location(self, key):
        current = StorageLocations.key_for_dir(self.status.state.iso_dir)
        if key == current:
            return
        loc = next((x for x in self.image_card.locations if x.key == key), None)
        if loc is None:
            return
        if self.status.present:
            if self.status.file_size + 512 * 1024 ** 2 > loc.free:
                QMessageBox.warning(self, t("app.title"), t("error.no_space"))
                self.image_card.retranslate_locations()
                return
            if QMessageBox.question(self, t("app.title"), t("confirm.location_move", loc.directory)) != \
                    QMessageBox.StandardButton.Yes:
                self.image_card.retranslate_locations()
                return
        self.image_card.set_busy(True)
        self.image_card.show_progress(0, 0, t("progress.moving_start"))
        self._run(["location", key, "--lang", CATALOG.lang],
                  on_ok=lambda: QMessageBox.information(self, t("app.title"),
                                                         t("done.location", loc.directory)))

    def toggle_auto(self, checked):
        self.recover_card.auto_box.setEnabled(False)
        self._run(["auto", "on" if checked else "off"])

    def reboot_to_recovery(self):
        if QMessageBox.question(self, t("app.title"), t("confirm.reboot")) != QMessageBox.StandardButton.Yes:
            return
        self._run(["one-shot"], on_ok=lambda: subprocess.Popen(["systemctl", "reboot"]))

    def _run(self, args, on_ok=None):
        self.task = PrivilegedTask(backend_cmd(*args), self)
        self.task.line.connect(self._on_line)
        self.task.done.connect(lambda code, out, err: self._on_done(code, err, on_ok))
        self.task.start()

    def _on_line(self, ln):
        parts = ln.split()
        if parts == ["verify"]:
            self.image_card.show_progress(0, 0, t("progress.verifying"))
        elif len(parts) == 3 and parts[0] == "progress":
            done, total = int(parts[1]) // 1048576, int(parts[2]) // 1048576
            self.image_card.show_progress(done, total, t("progress.copying",
                                                         number(done * 1048576 / 1e9, 2), number(total * 1048576 / 1e9, 2)))

    def _on_done(self, code, err, on_ok):
        self.image_card.set_busy(False)
        self.reload()
        if code == 0:
            if on_ok:
                on_ok()
        elif code not in (126,):   # 126 — пользователь закрыл окно пароля
            QMessageBox.critical(self, t("app.title"), error_text(err))
