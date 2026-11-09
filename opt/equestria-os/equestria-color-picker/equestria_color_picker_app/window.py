"""color-picker: window."""
from __future__ import annotations

import json
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget
)
from equestria_kit import qt as kit_qt
from equestria_kit.widgets import small_btn
from .capture import Overlay, ScreenPicker
from .color import ColorState, contrast, grade, luminance, parse_hex
from .format_dialog import FormatDialog
from .formats import CATS, FormatBook, MY
from .localization import catalog, live_i18n, tr
from .paths import CONFIG
from .style import THEME, apply_theme
from .widgets import HueBar, SVBox, Swatch, flag


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        catalog.set_language(catalog.lang, persist=False)
        self.cfg = cfg
        self.theme = cfg["theme"]
        self.color = ColorState()
        self.book = FormatBook(cfg)
        self.overlay = None
        self.picker = ScreenPicker(self)
        self.picker.picked.connect(self._screen_picked)
        self.picker.cancelled.connect(self._pick_finished)
        self.picker.failed.connect(self._pick_failed)
        self.save_timer = QTimer(self, singleShot=True, interval=400)
        self.save_timer.timeout.connect(self.save)
        self.toast_timer = QTimer(self, singleShot=True, interval=3500)
        live_i18n.call(self.setWindowTitle, "Equestria Picker")
        self.setMinimumSize(920, 660)
        self.resize(1040, 740)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        title = live_i18n.call(QLabel, "Equestria Picker")
        title.setObjectName("h2")
        theme_btn = small_btn(tr("window.theme"))
        theme_btn.clicked.connect(lambda: self._theme_menu(theme_btn))
        top.addWidget(title)
        top.addStretch()
        self.language_combo = catalog.selector(self)
        top.addWidget(self.language_combo)
        top.addWidget(theme_btn)
        root.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)
        body.addWidget(self._build_color_column())
        body.addLayout(self._build_formats_column(), 1)

        self.color.load_hex(cfg["color"])
        self._reload_formats()
        self._rebuild_history()
        self._changed(None)

    # --- построение окна
    def _build_color_column(self) -> QWidget:
        """Левая колонка: пипетка, образец, выбор цвета, поля HEX/RGBA, контраст, история."""
        left = QVBoxLayout()
        left.setSpacing(10)
        row = QHBoxLayout()
        self.pick_btn = live_i18n.call(QPushButton, tr("window.eyedropper"))
        self.pick_btn.setObjectName("primary")
        self.pick_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pick_btn.clicked.connect(self.start_pick)
        self.copy_btn = live_i18n.call(QPushButton, tr("window.copy"))
        self.copy_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_btn.clicked.connect(lambda: self.copy_format(self.book.primary))
        row.addWidget(self.pick_btn, 1)
        row.addWidget(self.copy_btn, 1)
        left.addLayout(row)
        self.swatch = Swatch()
        left.addWidget(self.swatch)
        self.sv = SVBox()
        self.sv.changed.connect(self._sv_changed)
        left.addWidget(self.sv, 1)
        self.hue = HueBar()
        self.hue.changed.connect(self._hue_changed)
        left.addWidget(self.hue)
        arow = QHBoxLayout()
        arow.addWidget(live_i18n.call(QLabel, tr("window.alpha")))
        self.alpha = QSlider(Qt.Orientation.Horizontal)
        self.alpha.setRange(0, 255)
        self.alpha.setValue(255)
        self.alpha.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.alpha.valueChanged.connect(self._alpha_changed)
        arow.addWidget(self.alpha, 1)
        left.addLayout(arow)
        erow = QHBoxLayout()
        self.hex_edit = QLineEdit()
        live_i18n.call(self.hex_edit.setPlaceholderText, "#RRGGBB")
        self.hex_edit.textEdited.connect(self._hex_edited)
        erow.addWidget(self.hex_edit, 2)
        self.rgb_edits = []
        for lab in "RGBA":
            e = QLineEdit()
            live_i18n.call(e.setPlaceholderText, lab)
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e.setMaximumWidth(58)
            e.textEdited.connect(self._rgb_edited)
            self.rgb_edits.append(e)
            erow.addWidget(e)
        left.addLayout(erow)
        self.contrast_label = live_i18n.call(QLabel, "")
        self.contrast_label.setObjectName("hint")
        self.contrast_label.setWordWrap(True)
        left.addWidget(self.contrast_label)
        hrow = QHBoxLayout()
        hl = live_i18n.call(QLabel, tr("window.history"))
        hl.setObjectName("h2")
        clr = small_btn(tr("window.clear"))
        clr.clicked.connect(self._clear_history)
        hrow.addWidget(hl)
        hrow.addStretch()
        hrow.addWidget(clr)
        left.addLayout(hrow)
        self.hist_box = QWidget()
        self.hist_lay = QHBoxLayout(self.hist_box)
        self.hist_lay.setContentsMargins(0, 0, 0, 0)
        self.hist_lay.setSpacing(6)
        left.addWidget(self.hist_box)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(400)
        return lw

    def _build_formats_column(self) -> QVBoxLayout:
        """Правая колонка: поиск и список форматов, параметры, свой формат."""
        cfg = self.cfg
        right = QVBoxLayout()
        right.setSpacing(8)
        frow = QHBoxLayout()
        self.search = QLineEdit()
        live_i18n.call(self.search.setPlaceholderText, tr("window.search_format"))
        self.search.textChanged.connect(self._rebuild_list)
        self.cat = QComboBox()
        
        for category in CATS:
            live_i18n.call(self.cat.addItem, tr(category), category)
        self.cat.currentIndexChanged.connect(self._rebuild_list)
        frow.addWidget(self.search, 1)
        frow.addWidget(self.cat)
        right.addLayout(frow)
        self.list = QListWidget()
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(lambda it: self.copy_format(it.data(Qt.ItemDataRole.UserRole)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        right.addWidget(self.list, 1)
        self.toast = live_i18n.call(QLabel, tr("window.click_format_copy_make_primary"))
        self.toast.setObjectName("hint")
        self.toast.setWordWrap(True)
        self.toast_timer.timeout.connect(lambda: live_i18n.call(self.toast.setText, tr("window.click_format_copy_make_primary")))
        right.addWidget(self.toast)
        orow = QHBoxLayout()
        orow.setSpacing(6)
        self.opt_auto = small_btn(tr("window.auto_copy_after_eyedropper"), True)
        self.opt_upper = small_btn(tr("window.uppercase_hex"), True)
        self.opt_trim = small_btn(tr("window.trim_zeros"), True)
        self.opt_hide = small_btn(tr("window.hide_window_while_picking"), True,
                                  tr("window.window_hides_during_eyedropper_returns"))
        for b, key in ((self.opt_auto, "autocopy"), (self.opt_hide, "hide"),
                       (self.opt_upper, "upper"), (self.opt_trim, "trim")):
            b.setChecked(bool(cfg[key]))
            b.toggled.connect(lambda on, k=key: self._opt(k, on))
            orow.addWidget(b)
        self.prec = QComboBox()
        for n in (2, 3, 4, 6):
            live_i18n.call(self.prec.addItem, tr("window.digits", n), n)
        self.prec.setCurrentIndex(max(0, self.prec.findData(int(cfg["precision"]))))
        self.prec.currentIndexChanged.connect(lambda _: self._opt("precision", self.prec.currentData()))
        orow.addWidget(self.prec)
        orow.addStretch()
        add = small_btn(tr("window.custom_format"))
        add.clicked.connect(lambda: self._edit_custom(None))
        orow.addWidget(add)
        right.addLayout(orow)
        return right

    # --- состояние цвета
    def fields(self) -> dict:
        return self.color.fields(int(self.cfg["precision"]), bool(self.cfg["trim"]), bool(self.cfg["upper"]))

    # --- синхронизация UI
    def _changed(self, source) -> None:
        c = self.color
        r, g, b = c.rgb()
        A = c.alpha255()
        self.swatch.set_color(QColor(r, g, b, A))
        self.sv.set_hsv(c.h, c.s, c.v)
        if source != "hue":
            self.hue.set_hue(c.h)
        self.alpha.blockSignals(True)
        self.alpha.setValue(A)
        self.alpha.blockSignals(False)
        if source != "hex":
            hx = live_i18n.format_text('#{0:02x}{1:02x}{2:02x}', r, g, b) + (live_i18n.format_text('{0:02x}', A) if A != 255 else "")
            live_i18n.call(self.hex_edit.setText, hx.upper() if self.cfg["upper"] else hx)
            flag(self.hex_edit, False)
        if source != "rgb":
            for e, val in zip(self.rgb_edits, (r, g, b, A)):
                live_i18n.call(e.setText, str(val))
                flag(e, False)
        lum = luminance(r, g, b)
        cw, cb = contrast(lum, 1.0), contrast(lum, 0.0)
        live_i18n.call(self.contrast_label.setText, tr("window.contrast_with_white_1_with", cw, grade(cw), cb, grade(cb)))
        self._update_values()
        self.cfg["color"] = c.hex8()
        self.save_timer.start()

    def _sv_changed(self, s, v):
        self.color.s, self.color.v = s, v
        self._changed("sv")

    def _hue_changed(self, h):
        self.color.h = h
        self._changed("hue")

    def _alpha_changed(self, val):
        self.color.a = val / 255
        self._changed("alpha")

    def _hex_edited(self, text):
        p = parse_hex(text)
        flag(self.hex_edit, bool(text.strip()) and p is None)
        if p:
            self.color.set_rgb(p[0], p[1], p[2], p[3])
            self._changed("hex")

    def _rgb_edited(self, _):
        try:
            vals = [int(e.text()) for e in self.rgb_edits]
            ok = all(0 <= x <= 255 for x in vals)
        except ValueError:
            ok = False
        for e in self.rgb_edits:
            flag(e, not ok and bool(e.text().strip()))
        if ok:
            self.color.set_rgb(*vals)
            self._changed("rgb")

    # --- форматы
    def _reload_formats(self) -> None:
        self.book.reload()
        self._rebuild_list()

    def _rebuild_list(self, *_) -> None:
        self.list.clear()
        for fid in self.book.matching(self.cat.currentData(), self.search.text()):
            it = live_i18n.call(QListWidgetItem, )
            it.setData(Qt.ItemDataRole.UserRole, fid)
            live_i18n.call(self.list.addItem, it)
        self._update_values()

    def _update_values(self) -> None:
        if not self.book.formats:
            return
        fl = self.fields()
        for i in range(self.list.count()):
            it = self.list.item(i)
            fid = it.data(Qt.ItemDataRole.UserRole)
            c, n, _t, custom = self.book.formats[fid]
            c = tr(c)
            n = n if custom else tr(n)
            val = self.book.render(fid, fl)
            star = "★ " if fid == self.book.primary else ""
            head = n if self.cat.currentData() != "common.all" else live_i18n.format_text("{} · {}", c, n)
            live_i18n.call(it.setText, live_i18n.format_text("{}{}\n{}", star, head, val if val is not None else tr("window.template_error")))

    def value_of(self, fid: str):
        return self.book.render(fid, self.fields())

    def copy_format(self, fid: str) -> None:
        if fid not in self.book.formats:
            return
        val = self.value_of(fid)
        if val is None:
            self._toast(tr("window.template_error_fix_rmb_edit"))
            return
        live_i18n.call(QGuiApplication.clipboard().setText, val)
        self.book.primary = fid
        self._toast(tr("window.copied", val))
        self._add_history()
        self._update_values()
        self.save_timer.start()

    def _toast(self, text: str) -> None:
        live_i18n.call(self.toast.setText, text if len(text) <= 160 else text[:157] + "…")
        self.toast_timer.start()

    def _list_menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        if not it:
            return
        fid = it.data(Qt.ItemDataRole.UserRole)
        c, n, t, custom = self.book.formats[fid]
        menu = QMenu(self)
        live_i18n.call(menu.addAction, tr("window.copy")).triggered.connect(lambda: self.copy_format(fid))
        live_i18n.call(menu.addAction, tr("window.make_primary_without_copying")).triggered.connect(lambda: self._make_primary(fid))
        live_i18n.call(menu.addAction, tr("window.custom_format_based")).triggered.connect(lambda: self._edit_custom(None, n, t))
        if custom:
            live_i18n.call(menu.addAction, tr("window.edit")).triggered.connect(lambda: self._edit_custom(fid))
            live_i18n.call(menu.addAction, tr("window.delete")).triggered.connect(lambda: self._delete_custom(fid))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def _make_primary(self, fid: str) -> None:
        self.book.primary = fid
        self._update_values()
        self.save_timer.start()

    def _edit_custom(self, fid, name: str = "", tpl: str = "") -> None:
        if fid:
            _, name, tpl, _ = self.book.formats[fid]
        dlg = FormatDialog(self, self.fields, name, tpl)
        if not dlg.exec():
            return
        self.book.save_custom(fid, *dlg.result_data())
        self._rebuild_list()
        self.cat.setCurrentIndex(max(0, self.cat.findData(MY)))
        self.save()

    def _delete_custom(self, fid: str) -> None:
        self.book.delete_custom(fid)
        self._rebuild_list()
        self.save()

    def _opt(self, key: str, val) -> None:
        self.cfg[key] = val
        self._changed(None)

    # --- история
    def _add_history(self) -> None:
        h8 = self.color.hex8()
        hist = [x for x in self.cfg["history"] if x != h8]
        self.cfg["history"] = ([h8] + hist)[:18]
        self._rebuild_history()

    def _clear_history(self) -> None:
        self.cfg["history"] = []
        self._rebuild_history()
        self.save()

    def _rebuild_history(self) -> None:
        while self.hist_lay.count():
            w = self.hist_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for h8 in self.cfg["history"]:
            p = parse_hex(h8)
            if not p:
                continue
            b = live_i18n.call(QPushButton, )
            b.setFixedSize(24, 24)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            live_i18n.call(b.setToolTip, "#" + h8.upper())
            b.setStyleSheet(live_i18n.format_text('QPushButton {{ background: rgba({0},{1},{2},{3:.3f}); border: 1px solid {4}; border-radius: 6px; padding: 0; }}', p[0], p[1], p[2], p[3] / 255, THEME['surface2']))
            b.clicked.connect(lambda _=False, x=h8: self._restore(x))
            self.hist_lay.addWidget(b)
        self.hist_lay.addStretch()

    def _restore(self, h8: str) -> None:
        self.color.load_hex(h8)
        self._changed(None)

    # --- пипетка
    def start_pick(self) -> None:
        self.pick_btn.setEnabled(False)
        hide = bool(self.cfg["hide"])
        if hide:
            self.hide()  # окно вернётся само в _pick_finished
        if QGuiApplication.platformName() == "wayland":
            self._toast(tr("window.pick_color_screen_esc_cancel"))
            # даём окну время исчезнуть, чтобы оно не попало в кадр
            QTimer.singleShot(250 if hide else 0, self.picker.start)
        else:
            QTimer.singleShot(250 if hide else 0, self._start_overlay)

    def _start_overlay(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.overlay = Overlay(screen)
        self.overlay.picked.connect(self._screen_picked)
        self.overlay.cancelled.connect(self._pick_finished)
        self.overlay.showFullScreen()
        self.overlay.activateWindow()
        self.overlay.setFocus()

    def _screen_picked(self, c: QColor) -> None:
        self.color.set_rgb(c.red(), c.green(), c.blue(), 255)
        self._changed(None)
        self._add_history()
        self._pick_finished()
        if self.cfg["autocopy"]:
            self.copy_format(self.book.primary)

    def _pick_failed(self, msg: str) -> None:
        self._toast(msg)
        self._pick_finished()

    def _pick_finished(self) -> None:
        # освобождаем оверлей только после выхода из его обработчика события
        QTimer.singleShot(0, lambda: setattr(self, "overlay", None))
        self.pick_btn.setEnabled(True)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    # --- тема / настройки
    def _theme_menu(self, btn) -> None:
        kit_qt.theme_menu(self, btn, self.theme, self._set_theme)

    def _set_theme(self, name: str) -> None:
        self.theme = apply_theme(name)
        self.cfg["theme"] = self.theme
        self._rebuild_history()
        self.save()

    def save(self) -> None:
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def closeEvent(self, e) -> None:
        self.save()
        super().closeEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.matches(QKeySequence.StandardKey.Copy):
            self.copy_format(self.book.primary)
        else:
            super().keyPressEvent(e)
