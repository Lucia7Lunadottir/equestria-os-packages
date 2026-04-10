import sys, os, subprocess, threading, re
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
from PyQt6.QtGui import QIcon, QFontDatabase, QFont
from PyQt6.QtCore import Qt, pyqtSignal
from ui_services import Ui_ServicesManager, ServiceRow


class ServiceData:
    def __init__(self, name, unit_file_state=""):
        self.name = name
        self.description = ""
        self.active_state = "inactive"
        self.sub_state = "dead"
        self.unit_file_state = unit_file_state

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


def _fetch_all_services():
    services = {}

    # All service unit files (includes disabled, static, masked, generated)
    r1 = subprocess.run(
        ["systemctl", "list-unit-files", "--type=service", "--no-pager", "--no-legend"],
        capture_output=True, text=True
    )
    for line in r1.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(".service"):
            services[parts[0]] = ServiceData(name=parts[0], unit_file_state=parts[1])

    # All loaded units with runtime state and description
    r2 = subprocess.run(
        ["systemctl", "list-units", "--all", "--type=service", "--no-pager", "--no-legend", "--full"],
        capture_output=True, text=True
    )
    for line in r2.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        # Some systemd versions prefix lines with a status glyph (● ✗ ▷ ○)
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
            svc = ServiceData(name=name, unit_file_state="transient")
            svc.active_state = active
            svc.sub_state = sub
            svc.description = desc
            services[name] = svc

    return sorted(services.values(), key=lambda s: s.name)


def _refresh_single(svc_name):
    r = subprocess.run(
        ["systemctl", "show", svc_name, "--no-pager",
         "--property=Description,ActiveState,SubState,UnitFileState"],
        capture_output=True, text=True
    )
    props = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k] = v
    return props


LANGS = {
    "ui.title": {
        "en": "Equestria OS Services",
        "ru": "Сервисы Equestria OS",
        "de": "Equestria OS Dienste",
        "fr": "Services Equestria OS",
        "es": "Servicios Equestria OS",
        "pt": "Serviços Equestria OS",
        "pl": "Usługi Equestria OS",
        "uk": "Сервіси Equestria OS",
        "zh": "Equestria OS 服务",
        "ja": "Equestria OS サービス",
    },
    "cat.all":      {"en": "All",      "ru": "Все",           "de": "Alle",         "fr": "Tous",      "es": "Todos",       "pt": "Todos",       "pl": "Wszystkie",   "uk": "Всі",        "zh": "全部",  "ja": "すべて"},
    "cat.running":  {"en": "Running",  "ru": "Запущенные",    "de": "Laufend",      "fr": "En cours",  "es": "En ejecución","pt": "Em execução", "pl": "Działające",  "uk": "Запущені",   "zh": "运行中","ja": "実行中"},
    "cat.stopped":  {"en": "Stopped",  "ru": "Остановленные", "de": "Gestoppt",     "fr": "Arrêtés",   "es": "Detenidos",   "pt": "Parados",     "pl": "Zatrzymane",  "uk": "Зупинені",   "zh": "已停止","ja": "停止中"},
    "cat.enabled":  {"en": "Enabled",  "ru": "Включённые",    "de": "Aktiviert",    "fr": "Activés",   "es": "Habilitados", "pt": "Habilitados", "pl": "Włączone",    "uk": "Увімкнені",  "zh": "已启用","ja": "有効"},
    "cat.disabled": {"en": "Disabled", "ru": "Выключенные",   "de": "Deaktiviert",  "fr": "Désactivés","es": "Deshabilitados","pt":"Desabilitados","pl": "Wyłączone",  "uk": "Вимкнені",   "zh": "已禁用","ja": "無効"},
    "cat.failed":   {"en": "Failed",   "ru": "С ошибкой",     "de": "Fehlgeschlagen","fr":"En erreur",  "es": "Fallidos",    "pt": "Com erro",    "pl": "Błędne",      "uk": "З помилкою", "zh": "失败",  "ja": "エラー"},

    "state.running":    {"en": "Running",   "ru": "Работает",     "de": "Läuft",      "fr": "Actif",      "es": "Activo",      "pt": "Rodando",     "pl": "Działa",      "uk": "Працює",      "zh": "运行中", "ja": "実行中"},
    "state.stopped":    {"en": "Stopped",   "ru": "Остановлен",   "de": "Gestoppt",   "fr": "Arrêté",     "es": "Detenido",    "pt": "Parado",      "pl": "Zatrzymany",  "uk": "Зупинений",   "zh": "已停止", "ja": "停止"},
    "state.failed":     {"en": "Failed",    "ru": "Ошибка",       "de": "Fehler",     "fr": "Erreur",     "es": "Error",       "pt": "Erro",        "pl": "Błąd",        "uk": "Помилка",     "zh": "失败",   "ja": "エラー"},
    "state.activating": {"en": "Starting",  "ru": "Запускается",  "de": "Startet",    "fr": "Démarrage",  "es": "Iniciando",   "pt": "Iniciando",   "pl": "Uruchamia",   "uk": "Запуск",      "zh": "启动中", "ja": "起動中"},
    "state.enabled":    {"en": "Autostart",  "ru": "Автозапуск",   "de": "Autostart",  "fr": "Démarrage auto","es": "Arranque auto","pt": "Inicialização auto","pl": "Autostart", "uk": "Автозапуск",  "zh": "自动启动","ja": "自動起動"},
    "state.disabled":   {"en": "Manual",     "ru": "Вручную",      "de": "Manuell",    "fr": "Manuel",     "es": "Manual",      "pt": "Manual",      "pl": "Ręcznie",     "uk": "Вручну",      "zh": "手动",   "ja": "手動"},
    "state.static":     {"en": "System",     "ru": "Системный",    "de": "System",     "fr": "Système",    "es": "Sistema",     "pt": "Sistema",     "pl": "Systemowy",   "uk": "Системний",   "zh": "系统",   "ja": "システム"},
    "state.masked":     {"en": "Blocked",    "ru": "Заблокирован", "de": "Blockiert",  "fr": "Bloqué",     "es": "Bloqueado",   "pt": "Bloqueado",   "pl": "Zablokowany", "uk": "Заблокований","zh": "已屏蔽", "ja": "ブロック"},
    "state.generated":  {"en": "Generated",  "ru": "Авто",         "de": "Generiert",  "fr": "Généré",     "es": "Generado",    "pt": "Gerado",      "pl": "Generowany",  "uk": "Авто",        "zh": "生成",   "ja": "自動"},

    "btn.start":   {"en": "Start",      "ru": "Запустить",   "de": "Starten",       "fr": "Démarrer",   "es": "Iniciar",     "pt": "Iniciar",      "pl": "Uruchom",   "uk": "Запустити",  "zh": "启动",  "ja": "起動"},
    "btn.stop":    {"en": "Stop",       "ru": "Остановить",  "de": "Stoppen",       "fr": "Arrêter",    "es": "Detener",     "pt": "Parar",        "pl": "Zatrzymaj", "uk": "Зупинити",   "zh": "停止",  "ja": "停止"},
    "btn.enable":  {"en": "Set Autostart","ru": "Автозапуск ВКЛ","de": "Autostart AN", "fr": "Autostart ON","es": "Activar inicio","pt": "Ativar início","pl": "Autostart WŁ","uk": "Автозапуск УВК","zh": "启用自动","ja": "自動起動ON"},
    "btn.disable": {"en": "No Autostart","ru": "Автозапуск ВЫКЛ","de": "Autostart AUS","fr": "Autostart OFF","es": "Sin inicio","pt": "Sem início",  "pl": "Autostart WYŁ","uk": "Автозапуск ВИМ","zh": "禁用自动","ja": "自動起動OFF"},
    "btn.na":      {"en": "N/A",        "ru": "Н/Д",         "de": "N/V",           "fr": "N/D",        "es": "N/D",         "pt": "N/D",          "pl": "N/D",       "uk": "Н/Д",        "zh": "不适用","ja": "N/A"},
    "btn.confirm": {"en": "Confirm", "ru": "Подтвердить","de": "Bestätigen", "fr": "Confirmer", "es": "Confirmar",  "pt": "Confirmar",  "pl": "Potwierdź","uk": "Підтвердити","zh": "确认", "ja": "確認"},
    "btn.cancel":  {"en": "Cancel",  "ru": "Отмена",     "de": "Abbrechen",  "fr": "Annuler",   "es": "Cancelar",   "pt": "Cancelar",   "pl": "Anuluj",   "uk": "Скасувати",  "zh": "取消", "ja": "キャンセル"},

    "modal.title":   {"en": "Confirmation",      "ru": "Подтверждение",    "de": "Bestätigung",    "fr": "Confirmation",  "es": "Confirmación",   "pt": "Confirmação",   "pl": "Potwierdzenie","uk": "Підтвердження","zh": "确认",   "ja": "確認"},
    "modal.start":   {"en": "Start {0}?",        "ru": "Запустить {0}?",   "de": "{0} starten?",   "fr": "Démarrer {0} ?","es": "¿Iniciar {0}?",  "pt": "Iniciar {0}?",  "pl": "Uruchomić {0}?","uk": "Запустити {0}?","zh": "启动 {0}？", "ja": "{0} を起動しますか？"},
    "modal.stop":    {"en": "Stop {0}?",         "ru": "Остановить {0}?",  "de": "{0} stoppen?",   "fr": "Arrêter {0} ?", "es": "¿Detener {0}?",  "pt": "Parar {0}?",    "pl": "Zatrzymać {0}?","uk": "Зупинити {0}?", "zh": "停止 {0}？", "ja": "{0} を停止しますか？"},
    "modal.enable":  {"en": "Enable autostart for {0}?\nService will start automatically on every boot.", "ru": "Включить автозапуск для {0}?\nСервис будет запускаться при каждой загрузке системы.", "de": "Autostart für {0} aktivieren?\nDer Dienst startet bei jedem Boot automatisch.", "fr": "Activer le démarrage auto de {0} ?\nLe service démarrera automatiquement à chaque démarrage.", "es": "¿Activar inicio automático de {0}?\nEl servicio iniciará automáticamente en cada arranque.", "pt": "Ativar inicialização automática de {0}?\nO serviço iniciará automaticamente em cada boot.", "pl": "Włączyć autostart {0}?\nUsługa będzie startować automatycznie przy każdym uruchomieniu.", "uk": "Увімкнути автозапуск для {0}?\nСервіс запускатиметься автоматично при кожному завантаженні.", "zh": "为 {0} 启用自动启动？\n服务将在每次启动时自动运行。", "ja": "{0} の自動起動を有効にしますか？\nシステム起動時に自動的に開始されます。"},
    "modal.disable": {"en": "Disable autostart for {0}?\nService will no longer start automatically on boot.", "ru": "Выключить автозапуск для {0}?\nСервис перестанет запускаться автоматически при загрузке.", "de": "Autostart für {0} deaktivieren?\nDer Dienst startet beim Boot nicht mehr automatisch.", "fr": "Désactiver le démarrage auto de {0} ?\nLe service ne démarrera plus automatiquement.", "es": "¿Desactivar inicio automático de {0}?\nEl servicio ya no iniciará automáticamente.", "pt": "Desativar inicialização automática de {0}?\nO serviço não iniciará mais automaticamente.", "pl": "Wyłączyć autostart {0}?\nUsługa nie będzie już startować automatycznie.", "uk": "Вимкнути автозапуск для {0}?\nСервіс більше не запускатиметься автоматично.", "zh": "为 {0} 禁用自动启动？\n服务将不再在启动时自动运行。", "ja": "{0} の自動起動を無効にしますか？\nシステム起動時に自動的に開始されなくなります。"},
    "modal.wait":    {"en": "Please wait...",     "ru": "Пожалуйста, подождите...", "de": "Bitte warten...", "fr": "Veuillez patienter...", "es": "Por favor espere...", "pt": "Aguarde...", "pl": "Proszę czekać...", "uk": "Зачекайте...", "zh": "请稍候...", "ja": "お待ちください..."},

    "tip.running":       {"en": "Service is currently running",                     "ru": "Сервис сейчас работает",                               "de": "Dienst läuft gerade",                        "fr": "Le service est en cours d'exécution",     "es": "El servicio está ejecutándose",            "pt": "O serviço está em execução",           "pl": "Usługa jest uruchomiona",                "uk": "Сервіс зараз працює",                    "zh": "服务正在运行",     "ja": "サービスは実行中"},
    "tip.stopped":       {"en": "Service is stopped",                               "ru": "Сервис остановлен",                                     "de": "Dienst ist gestoppt",                        "fr": "Le service est arrêté",                   "es": "El servicio está detenido",                "pt": "O serviço está parado",                "pl": "Usługa jest zatrzymana",                 "uk": "Сервіс зупинений",                       "zh": "服务已停止",       "ja": "サービスは停止"},
    "tip.failed":        {"en": "Service failed to start or crashed",               "ru": "Сервис завершился с ошибкой или не запустился",         "de": "Dienst ist fehlgeschlagen",                  "fr": "Le service a échoué",                     "es": "El servicio falló",                        "pt": "O serviço falhou",                     "pl": "Usługa zakończyła się błędem",           "uk": "Сервіс завершився з помилкою",           "zh": "服务失败",         "ja": "サービスがエラー"},
    "tip.autostart_on":  {"en": "Autostart ON — starts automatically on system boot","ru": "Автозапуск ВКЛ — запускается автоматически при загрузке", "de": "Autostart AN — startet beim Systemstart",   "fr": "Démarrage auto ACTIVÉ — démarre au boot", "es": "Inicio automático ACTIVO — arranca en el inicio","pt": "Inicialização auto ATIVA — inicia no boot","pl": "Autostart WŁ — startuje przy uruchomieniu","uk": "Автозапуск УВК — запускається при завантаженні","zh": "自动启动已启用 — 系统启动时自动运行","ja": "自動起動ON — システム起動時に自動開始"},
    "tip.autostart_off": {"en": "Autostart OFF — must be started manually",         "ru": "Автозапуск ВЫКЛ — нужно запускать вручную",            "de": "Autostart AUS — manuell starten",            "fr": "Démarrage auto DÉSACTIVÉ — démarrage manuel","es": "Inicio automático INACTIVO — inicio manual","pt": "Inicialização auto INATIVA — início manual","pl": "Autostart WYŁ — ręczne uruchomienie",    "uk": "Автозапуск ВИМ — потрібен ручний запуск","zh": "自动启动已禁用 — 需手动启动", "ja": "自動起動OFF — 手動起動が必要"},
    "tip.static":        {"en": "Static — controlled by the system, cannot be toggled","ru": "Системный — управляется системой, нельзя изменить",  "de": "Statisch — systemgesteuert",                 "fr": "Statique — contrôlé par le système",      "es": "Estático — controlado por el sistema",     "pt": "Estático — controlado pelo sistema",   "pl": "Statyczny — zarządzany przez system",    "uk": "Системний — керується системою",         "zh": "静态 — 由系统控制", "ja": "静的 — システムが管理"},
    "tip.masked":        {"en": "Masked — completely blocked, cannot be started",   "ru": "Заблокирован — полностью заблокирован, нельзя запустить","de": "Maskiert — vollständig blockiert",           "fr": "Masqué — bloqué, ne peut pas démarrer",   "es": "Enmascarado — bloqueado, no puede iniciarse","pt": "Mascarado — bloqueado, não pode iniciar","pl": "Maskowany — zablokowany, nie można uruchomić","uk": "Заблокований — повністю заблокований", "zh": "已屏蔽 — 完全阻止", "ja": "マスク — 完全にブロック"},
    "tip.enable_btn":    {"en": "Click to set autostart on boot (no terminal needed)","ru": "Нажмите, чтобы включить автозапуск при загрузке (терминал не нужен)","de": "Autostart beim Boot aktivieren",          "fr": "Activer le démarrage automatique au boot", "es": "Activar inicio automático al arrancar",    "pt": "Ativar inicialização automática",      "pl": "Włączyć autostart przy uruchomieniu",    "uk": "Увімкнути автозапуск при завантаженні",  "zh": "设置开机自动启动", "ja": "起動時自動開始を設定"},
    "tip.disable_btn":   {"en": "Click to remove autostart on boot (no terminal needed)","ru": "Нажмите, чтобы выключить автозапуск при загрузке (терминал не нужен)","de": "Autostart beim Boot deaktivieren",        "fr": "Désactiver le démarrage automatique au boot","es": "Desactivar inicio automático al arrancar","pt": "Desativar inicialização automática",   "pl": "Wyłączyć autostart przy uruchomieniu",   "uk": "Вимкнути автозапуск при завантаженні",   "zh": "禁用开机自动启动", "ja": "起動時自動開始を解除"},
    "tip.start_btn":     {"en": "Start the service now (no terminal needed)",       "ru": "Запустить сервис прямо сейчас (терминал не нужен)",    "de": "Dienst jetzt starten",                       "fr": "Démarrer le service maintenant",          "es": "Iniciar el servicio ahora",                "pt": "Iniciar o serviço agora",              "pl": "Uruchom usługę teraz",                   "uk": "Запустити сервіс зараз",                 "zh": "立即启动服务",     "ja": "今すぐサービスを起動"},
    "tip.stop_btn":      {"en": "Stop the service now (no terminal needed)",        "ru": "Остановить сервис прямо сейчас (терминал не нужен)",   "de": "Dienst jetzt stoppen",                       "fr": "Arrêter le service maintenant",           "es": "Detener el servicio ahora",                "pt": "Parar o serviço agora",                "pl": "Zatrzymaj usługę teraz",                 "uk": "Зупинити сервіс зараз",                  "zh": "立即停止服务",     "ja": "今すぐサービスを停止"},

    "search.ph":  {"en": "Search services...", "ru": "Поиск сервисов...", "de": "Dienste suchen...", "fr": "Rechercher...", "es": "Buscar servicios...", "pt": "Buscar serviços...", "pl": "Szukaj usług...", "uk": "Пошук сервісів...", "zh": "搜索服务...", "ja": "サービスを検索..."},
    "loading":    {"en": "Loading services...", "ru": "Загрузка сервисов...", "de": "Lade Dienste...", "fr": "Chargement...", "es": "Cargando...", "pt": "Carregando...", "pl": "Ładowanie usług...", "uk": "Завантаження...", "zh": "正在加载服务...", "ja": "読み込み中..."},
}


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
            fid = QFontDatabase.addApplicationFont(f_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                font = QFont(families[0])
                self.title_label.setFont(QFont(families[0], 28, QFont.Weight.Bold))
                self.modal_title.setFont(QFont(families[0], 20, QFont.Weight.Bold))

        q_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(q_path):
            self.setStyleSheet(open(q_path).read())

        icon_path = os.path.join(self.base_path, "equestria-os-services-manager.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        QApplication.setDesktopFileName("equestria-os-services-manager")

        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in LANGS["cat.all"]:
            self.current_lang = "en"

        self.all_services = []
        self._rows = {}
        self.pending_action = None  # (ServiceData, action_str)

        self.setup_logic()
        self.apply_localization()
        self.refresh_services()

    def t(self, key):
        return LANGS.get(key, {}).get(self.current_lang, LANGS.get(key, {}).get("en", key))

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
        }

    def setup_logic(self):
        self.search_field.textChanged.connect(self.apply_filters)
        self.category_dropdown.currentTextChanged.connect(self.apply_filters)
        self.btn_confirm_cancel.clicked.connect(self.modal_overlay.hide)
        self.btn_confirm_ok.clicked.connect(self.execute_action)

        for code in ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]:
            btn = QPushButton(code.upper())
            btn.setObjectName("LangBtn")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self.change_lang(c))
            self.lang_layout.addWidget(btn)

    def resizeEvent(self, event):
        self.modal_overlay.resize(event.size())
        super().resizeEvent(event)

    def change_lang(self, lang):
        self.current_lang = lang
        for i in range(self.lang_layout.count()):
            btn = self.lang_layout.itemAt(i).widget()
            if isinstance(btn, QPushButton):
                btn.setProperty("active", "true" if btn.text().lower() == lang else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self.apply_localization()

    def apply_localization(self):
        title = self.t("ui.title")
        self.title_label.setText(title)
        self.setWindowTitle(title)
        self.search_field.setPlaceholderText(self.t("search.ph"))
        self.modal_title.setText(self.t("modal.title"))
        self.btn_confirm_cancel.setText(self.t("btn.cancel"))
        self.btn_confirm_ok.setText(self.t("btn.confirm"))

        self.category_dropdown.blockSignals(True)
        self.category_dropdown.clear()
        self.category_dropdown.addItems([
            self.t("cat.all"), self.t("cat.running"), self.t("cat.stopped"),
            self.t("cat.enabled"), self.t("cat.disabled"), self.t("cat.failed"),
        ])
        self.category_dropdown.blockSignals(False)

        labels = self._row_labels()
        for row in self._rows.values():
            row.update_labels(labels)

        self.apply_filters()

    def refresh_services(self):
        def _run():
            self.fetch_finished.emit(_fetch_all_services())
        threading.Thread(target=_run, daemon=True).start()

    def on_fetch_finished(self, services):
        self.all_services = services
        self._build_list()

    def _build_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = {}

        labels = self._row_labels()
        for svc in self.all_services:
            row = ServiceRow(svc, labels, self._confirm_start_stop, self._confirm_enable_disable)
            self.list_layout.addWidget(row)
            self._rows[svc.name] = row

        self.apply_filters()

    def apply_filters(self):
        query = self.search_field.text().lower()
        cat = self.category_dropdown.currentText()

        for svc_name, row in self._rows.items():
            svc = row.svc_data
            text_ok = not query or query in svc.name.lower() or query in svc.description.lower()

            if cat == self.t("cat.all"):
                cat_ok = True
            elif cat == self.t("cat.running"):
                cat_ok = svc.active_state == "active"
            elif cat == self.t("cat.stopped"):
                cat_ok = svc.active_state not in ("active", "failed")
            elif cat == self.t("cat.enabled"):
                cat_ok = svc.is_enabled
            elif cat == self.t("cat.disabled"):
                cat_ok = svc.unit_file_state == "disabled"
            elif cat == self.t("cat.failed"):
                cat_ok = svc.active_state == "failed"
            else:
                cat_ok = True

            row.setVisible(text_ok and cat_ok)

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

    def _show_modal(self):
        self.btn_confirm_ok.show()
        self.btn_confirm_cancel.show()
        self.modal_overlay.show()
        self.modal_overlay.raise_()

    def execute_action(self):
        if not self.pending_action:
            return
        svc, action = self.pending_action
        self.modal_text.setText(self.t("modal.wait"))
        self.btn_confirm_ok.hide()
        self.btn_confirm_cancel.hide()

        cmd = ["pkexec", "systemctl", action, svc.name]

        def _run():
            proc = subprocess.run(cmd, capture_output=True)
            self.action_finished.emit(proc.returncode == 0, svc.name)

        threading.Thread(target=_run, daemon=True).start()

    def on_action_finished(self, success, svc_name):
        self.modal_overlay.hide()
        self.btn_confirm_ok.show()
        self.btn_confirm_cancel.show()
        if success:
            self._refresh_service_async(svc_name)

    def _refresh_service_async(self, svc_name):
        def _run():
            props = _refresh_single(svc_name)
            for svc in self.all_services:
                if svc.name == svc_name:
                    if "ActiveState" in props:
                        svc.active_state = props["ActiveState"]
                    if "SubState" in props:
                        svc.sub_state = props["SubState"]
                    if "UnitFileState" in props:
                        svc.unit_file_state = props["UnitFileState"]
                    if props.get("Description"):
                        svc.description = props["Description"]
                    break
            self.row_updated.emit(svc_name)

        threading.Thread(target=_run, daemon=True).start()

    def _on_row_updated(self, svc_name):
        if svc_name in self._rows:
            self._rows[svc_name].refresh(self._row_labels())
            self.apply_filters()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ServicesApp()
    win.show()
    sys.exit(app.exec())
