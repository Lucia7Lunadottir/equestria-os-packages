import sys, os, subprocess, threading, re
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QComboBox
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, pyqtSignal
from ui_services import Ui_ServicesManager, ServiceRow, GroupHeader
from service_groups import GROUPS, DEFAULT_FAVORITES, group_of
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit import live_i18n
from equestria_kit.widgets import font_families

# Переводы лежат в locales/<язык>.json рядом с main.py (ключ -> текст)
CATALOG = live_i18n.Catalog("equestria-os-services-manager", __file__)


class ServiceData:
    def __init__(self, name, unit_file_state="", scope="system"):
        self.name = name
        self.scope = scope  # "system" or "user"
        self.description = ""
        self.active_state = "inactive"
        self.sub_state = "dead"
        self.unit_file_state = unit_file_state

    @property
    def uid(self):
        return f"{self.scope}:{self.name}"

    @property
    def is_running(self):
        return self.active_state == "active"

    @property
    def is_enabled(self):
        return self.unit_file_state in ("enabled", "enabled-runtime")

    @property
    def display_name(self):
        if self.description:
            return self.description
        return self.name.removesuffix(".service")


def _fetch_scope(scope):
    """Fetch all services for the given scope ('system' or 'user')."""
    flag = ["--user"] if scope == "user" else ["--system"]
    services = {}

    r1 = subprocess.run(
        ["systemctl"] + flag + ["list-unit-files", "--type=service", "--no-pager", "--no-legend"],
        capture_output=True, text=True
    )
    for line in r1.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(".service"):
            services[parts[0]] = ServiceData(name=parts[0], unit_file_state=parts[1], scope=scope)

    r2 = subprocess.run(
        ["systemctl"] + flag + ["list-units", "--all", "--type=service", "--no-pager", "--no-legend", "--full"],
        capture_output=True, text=True
    )
    for line in r2.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        tokens = line.split(None, 5)
        if not tokens:
            continue
        if tokens[0] in ("●", "✗", "▷", "○", "×"):
            tokens = tokens[1:]
        elif tokens[0] and tokens[0][0] in "●✗▷○×":
            tokens[0] = tokens[0][1:]

        if len(tokens) < 4:
            continue

        name = tokens[0]
        if not name.endswith(".service"):
            continue

        active = tokens[2]
        sub = tokens[3]
        desc = tokens[4].strip() if len(tokens) > 4 else ""

        if name in services:
            services[name].active_state = active
            services[name].sub_state = sub
            if desc:
                services[name].description = desc
        else:
            svc = ServiceData(name=name, unit_file_state="transient", scope=scope)
            svc.active_state = active
            svc.sub_state = sub
            svc.description = desc
            services[name] = svc

    return services


def _fetch_all_services():
    system = _fetch_scope("system")
    user = _fetch_scope("user")
    all_svcs = list(system.values()) + list(user.values())
    return sorted(all_svcs, key=lambda s: (s.scope, s.name))


def _refresh_single(svc_name, scope="system"):
    flag = ["--user"] if scope == "user" else ["--system"]
    r = subprocess.run(
        ["systemctl"] + flag + ["show", svc_name, "--no-pager",
         "--property=Description,ActiveState,SubState,UnitFileState"],
        capture_output=True, text=True
    )
    props = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k] = v
    return props



class ServicesApp(QMainWindow, Ui_ServicesManager):
    fetch_finished = pyqtSignal(list)
    action_finished = pyqtSignal(bool, str)
    row_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.fetch_finished.connect(self.on_fetch_finished)
        self.action_finished.connect(self.on_action_finished)
        self.row_updated.connect(self._on_row_updated)

        f_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(f_path):
            families = font_families(f_path)
            if families:
                font = QFont(families[0])
                self.title_label.setFont(QFont(families[0], 28, QFont.Weight.Bold))
                self.modal_title.setFont(QFont(families[0], 20, QFont.Weight.Bold))

        q_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(q_path):
            kit_qt.style(self, open(q_path).read())

        icon_path = os.path.join(self.base_path, "equestria-os-services-manager.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        QApplication.setDesktopFileName("equestria-os-services-manager")

        self.current_lang = CATALOG.lang or "en"

        self.all_services = []
        self._rows = {}
        self._headers = {}          # ключ группы -> GroupHeader
        self._group_rows = {}       # ключ группы -> [ServiceRow]
        self.pending_action = None  # (ServiceData, action_str)
        # избранное и свёрнутые группы — у каждого пользователя свои
        self.config = kit_qt.JsonConfig("equestria-os-services-manager",
                                        {"favorites": list(DEFAULT_FAVORITES), "collapsed": {}})

        self.setup_logic()
        self.apply_localization()
        self.refresh_services()

    def t(self, key):
        return str(CATALOG.tr(key))

    def _row_labels(self):
        return {
            "running":           self.t("state.running"),
            "stopped":           self.t("state.stopped"),
            "failed":            self.t("state.failed"),
            "activating":        self.t("state.activating"),
            "enabled":           self.t("state.enabled"),
            "disabled":          self.t("state.disabled"),
            "static":            self.t("state.static"),
            "masked":            self.t("state.masked"),
            "generated":         self.t("state.generated"),
            "restart":           self.t("btn.restart"),
            "tip.restart_btn":   self.t("tip.restart_btn"),
            "tip.fav_add":       self.t("tip.fav_add"),
            "tip.fav_remove":    self.t("tip.fav_remove"),
            "start":             self.t("btn.start"),
            "stop":              self.t("btn.stop"),
            "enable":            self.t("btn.enable"),
            "disable":           self.t("btn.disable"),
            "n_a":               self.t("btn.na"),
            "tip.running":       self.t("tip.running"),
            "tip.stopped":       self.t("tip.stopped"),
            "tip.failed":        self.t("tip.failed"),
            "tip.autostart_on":  self.t("tip.autostart_on"),
            "tip.autostart_off": self.t("tip.autostart_off"),
            "tip.static":        self.t("tip.static"),
            "tip.masked":        self.t("tip.masked"),
            "tip.enable_btn":    self.t("tip.enable_btn"),
            "tip.disable_btn":   self.t("tip.disable_btn"),
            "tip.start_btn":     self.t("tip.start_btn"),
            "tip.stop_btn":      self.t("tip.stop_btn"),
            "scope.system":      self.t("scope.system"),
            "scope.user":        self.t("scope.user"),
        }

    def setup_logic(self):
        self.search_field.textChanged.connect(self.apply_filters)
        self.category_dropdown.currentIndexChanged.connect(self.apply_filters)
        self.scope_dropdown.currentIndexChanged.connect(self.apply_filters)
        self.btn_refresh.clicked.connect(self.refresh_services)
        self.btn_confirm_cancel.clicked.connect(self.modal_overlay.hide)
        self.btn_confirm_ok.clicked.connect(self.execute_action)

        # Компактный выпадающий список языков вместо ряда кнопок
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        # языки — найденные файлы locales/*.json, названия — из них же (_language_name)
        for code in CATALOG.languages:
            self.lang_combo.addItem(CATALOG.language_name(code), code)
        idx = self.lang_combo.findData(self.current_lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        # activated срабатывает только при выборе пользователем — без рекурсии
        self.lang_combo.activated.connect(
            lambda i: self.change_lang(self.lang_combo.itemData(i)))
        self.lang_layout.addWidget(self.lang_combo)

    def resizeEvent(self, event):
        self.modal_overlay.resize(event.size())
        super().resizeEvent(event)

    def change_lang(self, lang):
        self.current_lang = CATALOG.set_language(lang) or lang  # ещё и сохраняет выбор
        idx = self.lang_combo.findData(lang)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
        self.apply_localization()

    def apply_localization(self):
        title = self.t("ui.title")
        self.title_label.setText(title)
        self.setWindowTitle(title)
        self.search_field.setPlaceholderText(self.t("search.ph"))
        self.modal_title.setText(self.t("modal.title"))
        self.btn_confirm_cancel.setText(self.t("btn.cancel"))
        self.btn_confirm_ok.setText(self.t("btn.confirm"))
        self.btn_refresh.setText("⟳  " + self.t("btn.refresh"))
        self.btn_refresh.setToolTip(self.t("tip.refresh"))

        # фильтры хранят ключ в данных пункта: при смене языка выбор не сбрасывается
        for box, items in ((self.category_dropdown, ("all", "running", "stopped", "enabled", "disabled", "failed")),
                           (self.scope_dropdown, ("all", "system", "user"))):
            prefix = "cat" if box is self.category_dropdown else "scope"
            current = box.currentData() or "all"
            box.blockSignals(True)
            box.clear()
            for key in items:
                box.addItem(self.t(f"{prefix}.{key}"), key)
            box.setCurrentIndex(max(0, box.findData(current)))
            box.blockSignals(False)

        labels = self._row_labels()
        for row in self._rows.values():
            row.update_labels(labels)
        for key, header in self._headers.items():
            header.set_title(self.t(f"group.{key}"))

        self.apply_filters()

    def refresh_services(self):
        self.btn_refresh.setEnabled(False)

        def _run():
            self.fetch_finished.emit(_fetch_all_services())
        threading.Thread(target=_run, daemon=True).start()

    def on_fetch_finished(self, services):
        self.all_services = services
        self.btn_refresh.setEnabled(True)
        self._build_list()

    @property
    def favorites(self) -> set:
        return set(self.config.data.get("favorites", []))

    def _is_expanded(self, group) -> bool:
        return not self.config.data.get("collapsed", {}).get(group.key, group.collapsed)

    def _build_list(self):
        scroll = self.scroll_area.verticalScrollBar().value()
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().hide()          # иначе старые строки видны поверх новых до удаления
                item.widget().deleteLater()
        self._rows, self._headers, self._group_rows = {}, {}, {}

        favorites = self.favorites
        members = {g.key: [] for g in GROUPS}
        for svc in self.all_services:
            members[group_of(svc, favorites).key].append(svc)

        labels = self._row_labels()
        for group in GROUPS:
            svcs = sorted(members[group.key], key=lambda s: s.display_name.lower())
            if not svcs:
                continue
            header = GroupHeader(group, self._toggle_group)
            header.setChecked(self._is_expanded(group))
            header.set_title(self.t(f"group.{group.key}"))
            self.list_layout.addWidget(header)
            self._headers[group.key] = header
            rows = []
            for svc in svcs:
                row = ServiceRow(svc, labels, self._confirm_start_stop, self._confirm_enable_disable,
                                 self._restart, self._toggle_favorite, svc.uid in favorites)
                self.list_layout.addWidget(row)
                self._rows[svc.uid] = row
                rows.append(row)
            self._group_rows[group.key] = rows

        self.apply_filters()
        self.scroll_area.verticalScrollBar().setValue(scroll)

    def _toggle_group(self, group, expanded):
        self.config.data.setdefault("collapsed", {})[group.key] = not expanded
        self.config.save()
        self.apply_filters()

    def _toggle_favorite(self, svc):
        favorites = self.config.data.setdefault("favorites", [])
        if svc.uid in favorites:
            favorites.remove(svc.uid)
        else:
            favorites.append(svc.uid)
        self.config.save()
        self._build_list()

    def _matches(self, svc, query, cat, scope_filter) -> bool:
        if query and query not in svc.name.lower() and query not in svc.description.lower():
            return False
        if scope_filter in ("system", "user") and svc.scope != scope_filter:
            return False
        return {
            "running": svc.active_state == "active",
            "stopped": svc.active_state not in ("active", "failed"),
            "enabled": svc.is_enabled,
            "disabled": svc.unit_file_state == "disabled",
            "failed": svc.active_state == "failed",
        }.get(cat, True)

    def apply_filters(self):
        query = self.search_field.text().lower().strip()
        cat = self.category_dropdown.currentData() or "all"
        scope_filter = self.scope_dropdown.currentData() or "all"

        for key, rows in self._group_rows.items():
            header = self._headers[key]
            matching = [row for row in rows if self._matches(row.svc_data, query, cat, scope_filter)]
            header.set_count(len(matching))
            header.setVisible(bool(matching))
            # при поиске найденное видно и в свёрнутых группах
            expanded = header.isChecked() or bool(query)
            shown = set(map(id, matching)) if expanded else set()
            for row in rows:
                row.setVisible(id(row) in shown)

    def _confirm_start_stop(self, svc):
        action = "stop" if svc.active_state == "active" else "start"
        self.pending_action = (svc, action)
        self.modal_text.setText(self.t(f"modal.{action}").format(svc.display_name))
        self._show_modal()

    def _confirm_enable_disable(self, svc):
        action = "disable" if svc.is_enabled else "enable"
        self.pending_action = (svc, action)
        self.modal_text.setText(self.t(f"modal.{action}").format(svc.display_name))
        self._show_modal()

    def _restart(self, svc):
        """Перезапуск без окна «Вы уверены?»: безопасное действие, а для системных служб пароль
        всё равно спросит pkexec. Упавший plasmashell — один клик."""
        self.pending_action = (svc, "restart")
        self.execute_action()
        self.modal_overlay.show()
        self.modal_overlay.raise_()

    def _show_modal(self):
        self.btn_confirm_ok.show()
        self.btn_confirm_cancel.show()
        self.modal_overlay.show()
        self.modal_overlay.raise_()

    def execute_action(self):
        if not self.pending_action:          # «ОК» в окне ошибки
            self._close_error()
            return
        svc, action = self.pending_action
        self.modal_text.setText(self.t("modal.wait"))
        self.btn_confirm_ok.hide()
        self.btn_confirm_cancel.hide()

        if svc.scope == "user":
            cmd = ["systemctl", "--user", action, svc.name]
        else:
            cmd = ["pkexec", "systemctl", action, svc.name]

        def _run():
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self._last_error = (proc.stderr or proc.stdout).strip()
            self.action_finished.emit(proc.returncode == 0, svc.uid)

        self.pending_action = None
        threading.Thread(target=_run, daemon=True).start()

    def on_action_finished(self, success, svc_uid):
        self._refresh_service_async(svc_uid)
        if success:
            self.modal_overlay.hide()
            self.btn_confirm_ok.show()
            self.btn_confirm_cancel.show()
            return
        # раньше окно молча закрывалось — теперь видно, что не получилось и почему
        error = getattr(self, "_last_error", "")
        self.modal_text.setText(self.t("modal.error") + (f"\n\n{error[:400]}" if error else ""))
        self.btn_confirm_cancel.hide()
        self.btn_confirm_ok.setText(self.t("btn.ok"))
        self.btn_confirm_ok.show()

    def _close_error(self):
        self.modal_overlay.hide()
        self.btn_confirm_ok.setText(self.t("btn.confirm"))
        self.btn_confirm_cancel.show()

    def _refresh_service_async(self, svc_uid):
        def _run():
            scope, _, svc_name = svc_uid.partition(":")
            props = _refresh_single(svc_name, scope)
            for svc in self.all_services:
                if svc.uid == svc_uid:
                    if "ActiveState" in props:
                        svc.active_state = props["ActiveState"]
                    if "SubState" in props:
                        svc.sub_state = props["SubState"]
                    if "UnitFileState" in props:
                        svc.unit_file_state = props["UnitFileState"]
                    if props.get("Description"):
                        svc.description = props["Description"]
                    break
            self.row_updated.emit(svc_uid)

        threading.Thread(target=_run, daemon=True).start()

    def _on_row_updated(self, svc_uid):
        if svc_uid in self._rows:
            self._rows[svc_uid].refresh(self._row_labels())
            self.apply_filters()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    win = ServicesApp()
    win.show()
    sys.exit(app.exec())
