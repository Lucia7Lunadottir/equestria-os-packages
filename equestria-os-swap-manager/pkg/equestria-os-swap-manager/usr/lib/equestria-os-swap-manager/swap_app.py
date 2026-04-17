import sys
import os
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QMessageBox,
    QCheckBox, QProgressBar, QSpinBox, QSlider, QComboBox, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFontDatabase

import privilege

ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKMARK_SVG = os.path.join(ASSETS_DIR, "check_mark.svg")


def generate_assets():
    if os.path.exists(CHECKMARK_SVG):
        return
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path fill="#ffffff" d="M13.485 1.414l1.414 1.414L6.343 11.373 1.1 6.13l1.414-1.414 3.829 3.829z"/>
</svg>"""
    try:
        with open(CHECKMARK_SVG, 'w') as f:
            f.write(svg_content)
    except Exception:
        pass


def _get_ram_gb() -> int:
    """Return total system RAM in whole GB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return max(1, kb // 1024 // 1024)
    except Exception:
        pass
    return 8


LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
STRINGS = {
    # ── Existing ─────────────────────────────────────────────────────────────
    "title":        {"en": "Equestria OS Swap Manager",       "ru": "Equestria OS: Менеджер Подкачки",    "de": "Equestria OS Swap-Manager",        "fr": "Equestria OS Gestionnaire Swap",    "es": "Equestria OS Gestor Swap",          "pt": "Equestria OS Gerenciador Swap",     "pl": "Equestria OS Menedżer Swap",         "uk": "Equestria OS Менеджер Swap",         "zh": "Equestria 交换空间管理器",       "ja": "Equestria OS スワップマネージャー"},
    "current_swap": {"en": "Active Swap Files",               "ru": "Активные файлы подкачки",            "de": "Aktive Swap-Dateien",              "fr": "Fichiers Swap actifs",              "es": "Archivos Swap activos",             "pt": "Arquivos Swap ativos",              "pl": "Aktywne pliki wymiany",              "uk": "Активні файли підкачки",             "zh": "活动交换文件",                   "ja": "アクティブなスワップファイル"},
    "path":         {"en": "Swap File Path",                  "ru": "Путь к файлу подкачки",              "de": "Swap-Dateipfad",                   "fr": "Chemin du fichier Swap",            "es": "Ruta del archivo Swap",             "pt": "Caminho do arquivo Swap",           "pl": "Ścieżka pliku wymiany",              "uk": "Шлях до файлу підкачки",             "zh": "交换文件路径",                   "ja": "スワップファイルパス"},
    "size":         {"en": "Size (GB)",                       "ru": "Размер (ГБ)",                        "de": "Größe (GB)",                       "fr": "Taille (Go)",                       "es": "Tamaño (GB)",                       "pt": "Tamanho (GB)",                      "pl": "Rozmiar (GB)",                       "uk": "Розмір (ГБ)",                        "zh": "大小 (GB)",                      "ja": "サイズ (GB)"},
    "fstab_chk":    {"en": "Mount on boot (/etc/fstab)",      "ru": "Включать при загрузке (/etc/fstab)", "de": "Beim Booten einbinden (/etc/fstab)", "fr": "Monter au démarrage (/etc/fstab)", "es": "Montar al inicio (/etc/fstab)",     "pt": "Montar na inicialização (/etc/fstab)", "pl": "Montuj przy rozruchu (/etc/fstab)", "uk": "Вмикати при завантаженні (/etc/fstab)", "zh": "开机挂载 (/etc/fstab)",         "ja": "起動時にマウント (/etc/fstab)"},
    "swappiness":   {"en": "Kernel Swappiness (0–100)",       "ru": "Жадность подкачки (Swappiness)",     "de": "Kernel Swappiness",                "fr": "Swappiness du Noyau",               "es": "Swappiness del Kernel",             "pt": "Swappiness do Kernel",              "pl": "Swappiness Jądra",                   "uk": "Swappiness Ядра",                    "zh": "内核 Swappiness",                "ja": "カーネル Swappiness"},
    "btn_apply":    {"en": "Create / Resize Swap",            "ru": "Создать / Изменить размер",          "de": "Swap erstellen / ändern",          "fr": "Créer / Redimensionner Swap",       "es": "Crear / Redimensionar Swap",        "pt": "Criar / Redimensionar Swap",        "pl": "Utwórz / Zmień rozmiar Swap",        "uk": "Створити / Змінити розмір Swap",     "zh": "创建 / 调整交换空间",            "ja": "スワップを作成 / サイズ変更"},
    "btn_swapp":    {"en": "Apply Swappiness",                "ru": "Применить Swappiness",               "de": "Swappiness anwenden",              "fr": "Appliquer Swappiness",              "es": "Aplicar Swappiness",                "pt": "Aplicar Swappiness",                "pl": "Zastosuj Swappiness",                "uk": "Застосувати Swappiness",             "zh": "应用 Swappiness",                "ja": "Swappiness を適用"},
    "btn_disable":  {"en": "Disable Swap",                    "ru": "Отключить Swap",                     "de": "Swap deaktivieren",                "fr": "Désactiver Swap",                   "es": "Desactivar Swap",                   "pt": "Desativar Swap",                    "pl": "Wyłącz Swap",                        "uk": "Вимкнути Swap",                      "zh": "禁用交换空间",                   "ja": "スワップを無効化"},
    "btn_delete":   {"en": "Delete File",                     "ru": "Удалить файл",                       "de": "Datei löschen",                    "fr": "Supprimer le fichier",              "es": "Eliminar archivo",                  "pt": "Excluir arquivo",                   "pl": "Usuń plik",                          "uk": "Видалити файл",                      "zh": "删除文件",                       "ja": "ファイルを削除"},
    "status_app":   {"en": "Applying changes (may take time)...", "ru": "Применение (может занять время)...", "de": "Änderungen werden angewendet...", "fr": "Application en cours...",          "es": "Aplicando cambios...",              "pt": "Aplicando alterações...",           "pl": "Stosowanie zmian...",                "uk": "Застосування (може зайняти час)...", "zh": "正在应用更改...",                "ja": "変更を適用中..."},
    "success":      {"en": "Operation successful!",           "ru": "Операция выполнена успешно!",        "de": "Vorgang erfolgreich!",             "fr": "Opération réussie !",               "es": "¡Operación exitosa!",               "pt": "Operação bem-sucedida!",            "pl": "Operacja zakończona pomyślnie!",     "uk": "Операцію виконано успішно!",         "zh": "操作成功！",                     "ja": "操作が完了しました！"},
    "err_elevate":  {"en": "Failed to get root access.",      "ru": "Не удалось получить права root.",    "de": "Root-Zugriff fehlgeschlagen.",     "fr": "Échec de l'accès root.",            "es": "Error al obtener acceso root.",     "pt": "Falha ao obter acesso root.",       "pl": "Błąd uzyskania dostępu root.",       "uk": "Помилка отримання прав root.",       "zh": "获取 root 权限失败。",           "ja": "root アクセスに失敗しました。"},
    "no_swap":      {"en": "No active swap found.",           "ru": "Нет активных файлов подкачки.",      "de": "Kein aktiver Swap gefunden.",      "fr": "Aucun swap actif trouvé.",          "es": "No se encontró swap activo.",       "pt": "Nenhum swap ativo encontrado.",     "pl": "Brak aktywnego swapu.",              "uk": "Немає активних файлів підкачки.",    "zh": "未找到活动的交换空间。",         "ja": "アクティブなスワップはありません。"},

    # ── OOM / Memory Pressure ─────────────────────────────────────────────────
    "oom_section":   {"en": "Memory Pressure & OOM Killer",          "ru": "Давление памяти и OOM Killer",                    "de": "Speicherdruck & OOM-Killer",               "fr": "Pression mémoire & OOM Killer",             "es": "Presión de memoria & OOM Killer",           "pt": "Pressão de memória & OOM Killer",           "pl": "Ciśnienie pamięci & OOM Killer",             "uk": "Тиск пам'яті та OOM Killer",                 "zh": "内存压力与 OOM Killer",          "ja": "メモリプレッシャー & OOM Killer"},
    "oom_hint":      {"en": "Mode 1 prevents OOM kills — system slows down instead of killing processes (like Windows).", "ru": "Режим 1 предотвращает убийство процессов — система замедляется вместо того, чтобы ломать процессы (как Windows).", "de": "Modus 1 verhindert OOM-Kills — System verlangsamt sich statt Prozesse zu beenden.", "fr": "Le mode 1 empêche les kills OOM — le système ralentit au lieu de tuer les processus.", "es": "El modo 1 evita los kills OOM — el sistema se ralentiza en lugar de matar procesos.", "pt": "O modo 1 evita kills OOM — o sistema desacelera em vez de matar processos.", "pl": "Tryb 1 zapobiega OOM kills — system zwalnia zamiast zabijać procesy.", "uk": "Режим 1 запобігає вбивству процесів — система уповільнюється замість того, щоб ламати процеси.", "zh": "模式 1 防止 OOM 杀进程 — 系统变慢而不是杀死进程。", "ja": "モード1はOOMキルを防ぎます — プロセスを終了させる代わりにシステムが遅くなります。"},
    "oom_overcommit":{"en": "Memory overcommit policy:",             "ru": "Политика выделения памяти:",                     "de": "Speicher-Overcommit-Richtlinie:",          "fr": "Politique de sur-allocation mémoire :",     "es": "Política de sobreasignación de memoria:",   "pt": "Política de sobre-alocação de memória:",    "pl": "Polityka nadkontraktowania pamięci:",        "uk": "Політика надмірного виділення пам'яті:",     "zh": "内存超额分配策略：",             "ja": "メモリオーバーコミットポリシー："},
    "oom_mode_0":    {"en": "0 — Heuristic (default)",               "ru": "0 — Эвристика (по умолчанию)",                   "de": "0 — Heuristisch (Standard)",               "fr": "0 — Heuristique (défaut)",                  "es": "0 — Heurístico (predeterminado)",            "pt": "0 — Heurístico (padrão)",                   "pl": "0 — Heurystyczny (domyślny)",                "uk": "0 — Евристика (за замовчуванням)",            "zh": "0 — 启发式（默认）",             "ja": "0 — ヒューリスティック（デフォルト）"},
    "oom_mode_1":    {"en": "1 — Always allow (Windows-like)",       "ru": "1 — Всегда разрешать (как Windows)",              "de": "1 — Immer erlauben (Windows-ähnlich)",     "fr": "1 — Toujours autoriser (comme Windows)",    "es": "1 — Siempre permitir (como Windows)",        "pt": "1 — Sempre permitir (como Windows)",        "pl": "1 — Zawsze zezwalaj (jak Windows)",          "uk": "1 — Завжди дозволяти (як Windows)",          "zh": "1 — 始终允许（类似 Windows）",   "ja": "1 — 常に許可（Windowsのように）"},
    "oom_mode_2":    {"en": "2 — Strict limit (RAM + swap × ratio)", "ru": "2 — Строгий лимит (ОЗУ + swap × коэффициент)",   "de": "2 — Striktes Limit (RAM + Swap × Faktor)", "fr": "2 — Limite stricte (RAM + swap × ratio)",   "es": "2 — Límite estricto (RAM + swap × ratio)",  "pt": "2 — Limite estrito (RAM + swap × razão)",   "pl": "2 — Ścisły limit (RAM + swap × współczynnik)","uk": "2 — Суворий ліміт (ОЗУ + swap × коефіцієнт)","zh": "2 — 严格限制（内存+交换×比率）","ja": "2 — 厳格な制限（RAM+スワップ×比率）"},
    "oom_oomd_cb":   {"en": "Disable systemd-oomd (prevents proactive process kills)", "ru": "Отключить systemd-oomd (упреждающий убийца процессов)", "de": "systemd-oomd deaktivieren (verhindert proaktive Kills)", "fr": "Désactiver systemd-oomd (évite les kills proactifs)", "es": "Deshabilitar systemd-oomd (evita kills proactivos)", "pt": "Desativar systemd-oomd (evita kills proativos)", "pl": "Wyłącz systemd-oomd (zapobiega proaktywnym killom)", "uk": "Вимкнути systemd-oomd (запобігає превентивному вбивству)", "zh": "禁用 systemd-oomd（防止主动杀死进程）", "ja": "systemd-oomdを無効化（積極的なプロセスキルを防止）"},
    "oom_panic_cb":  {"en": "Prevent kernel panic on OOM (kernel.panic_on_oom=0)", "ru": "Не паниковать ядру при OOM (kernel.panic_on_oom=0)", "de": "Kernel-Panic bei OOM verhindern (kernel.panic_on_oom=0)", "fr": "Empêcher la panique noyau sur OOM (kernel.panic_on_oom=0)", "es": "Prevenir pánico del kernel en OOM (kernel.panic_on_oom=0)", "pt": "Prevenir pânico do kernel em OOM (kernel.panic_on_oom=0)", "pl": "Zapobiegaj panice jądra przy OOM (kernel.panic_on_oom=0)", "uk": "Запобігати паніці ядра при OOM (kernel.panic_on_oom=0)", "zh": "防止 OOM 时内核 panic（kernel.panic_on_oom=0）", "ja": "OOM時のカーネルパニックを防止（kernel.panic_on_oom=0）"},
    "oom_apply":     {"en": "Apply Memory Settings",                 "ru": "Применить настройки памяти",                     "de": "Speichereinstellungen anwenden",           "fr": "Appliquer les paramètres mémoire",          "es": "Aplicar configuración de memoria",           "pt": "Aplicar configurações de memória",          "pl": "Zastosuj ustawienia pamięci",                "uk": "Застосувати налаштування пам'яті",            "zh": "应用内存设置",                   "ja": "メモリ設定を適用"},

    # ── zram ─────────────────────────────────────────────────────────────────
    "zram_section":  {"en": "Fast Swap (zram)",                      "ru": "Быстрая подкачка (zram)",                        "de": "Schneller Swap (zram)",                    "fr": "Swap rapide (zram)",                        "es": "Swap rápido (zram)",                         "pt": "Swap rápido (zram)",                        "pl": "Szybki Swap (zram)",                         "uk": "Швидка підкачка (zram)",                     "zh": "快速交换（zram）",               "ja": "高速スワップ (zram)"},
    "zram_hint":     {"en": "Compressed swap in RAM — no disk IO, system stays responsive even under heavy load. Prevents watchdog reboot.", "ru": "Сжатая подкачка прямо в ОЗУ — без нагрузки на диск, система остаётся отзывчивой. Предотвращает перезагрузку по watchdog.", "de": "Komprimierter Swap im RAM — kein Datenträger-IO, System bleibt reaktionsfähig. Verhindert Watchdog-Neustart.", "fr": "Swap compressé en RAM — pas d'IO disque, système réactif. Évite le redémarrage watchdog.", "es": "Swap comprimido en RAM — sin IO de disco, sistema responsivo. Previene reinicio por watchdog.", "pt": "Swap comprimido na RAM — sem IO de disco, sistema responsivo. Previne reinicialização watchdog.", "pl": "Skompresowany swap w RAM — bez IO dysku. Zapobiega restartowi watchdoga.", "uk": "Стиснута підкачка в ОЗУ — без навантаження на диск. Запобігає перезавантаженню watchdog.", "zh": "RAM 中的压缩交换空间 — 无磁盘 IO，防止 watchdog 重启。", "ja": "RAMの圧縮スワップ — ディスクI/Oなし、watchdog再起動を防止。"},
    "zram_status":   {"en": "zram status:",                          "ru": "Состояние zram:",                                "de": "zram-Status:",                             "fr": "État zram :",                               "es": "Estado zram:",                               "pt": "Status zram:",                              "pl": "Status zram:",                               "uk": "Стан zram:",                                 "zh": "zram 状态：",                    "ja": "zram 状態："},
    "zram_active":   {"en": "Active: {0}",                           "ru": "Активен: {0}",                                   "de": "Aktiv: {0}",                               "fr": "Actif : {0}",                               "es": "Activo: {0}",                                "pt": "Ativo: {0}",                                "pl": "Aktywny: {0}",                               "uk": "Активний: {0}",                              "zh": "活跃：{0}",                      "ja": "アクティブ: {0}"},
    "zram_inactive": {"en": "Not active",                            "ru": "Не активен",                                     "de": "Nicht aktiv",                              "fr": "Inactif",                                   "es": "No activo",                                  "pt": "Não ativo",                                 "pl": "Nieaktywny",                                 "uk": "Не активний",                                "zh": "未激活",                         "ja": "非アクティブ"},
    "zram_size_lbl": {"en": "zram size (GB):",                       "ru": "Размер zram (ГБ):",                              "de": "zram-Größe (GB):",                         "fr": "Taille zram (Go) :",                        "es": "Tamaño zram (GB):",                          "pt": "Tamanho zram (GB):",                        "pl": "Rozmiar zram (GB):",                         "uk": "Розмір zram (ГБ):",                          "zh": "zram 大小 (GB)：",               "ja": "zram サイズ (GB)："},
    "zram_algo_lbl": {"en": "Algorithm:",                            "ru": "Алгоритм:",                                      "de": "Algorithmus:",                             "fr": "Algorithme :",                              "es": "Algoritmo:",                                 "pt": "Algoritmo:",                                "pl": "Algorytm:",                                  "uk": "Алгоритм:",                                  "zh": "算法：",                         "ja": "アルゴリズム："},
    "zram_enable":   {"en": "Enable zram",                           "ru": "Включить zram",                                  "de": "zram aktivieren",                          "fr": "Activer zram",                              "es": "Activar zram",                               "pt": "Ativar zram",                               "pl": "Włącz zram",                                 "uk": "Увімкнути zram",                             "zh": "启用 zram",                      "ja": "zramを有効化"},
    "zram_disable":  {"en": "Disable zram",                          "ru": "Выключить zram",                                 "de": "zram deaktivieren",                        "fr": "Désactiver zram",                           "es": "Desactivar zram",                            "pt": "Desativar zram",                            "pl": "Wyłącz zram",                                "uk": "Вимкнути zram",                              "zh": "禁用 zram",                      "ja": "zramを無効化"},

    # ── Windows preset ────────────────────────────────────────────────────────
    "win_section":   {"en": "Windows-like Preset",                   "ru": "Режим «как Windows»",                            "de": "Windows-ähnliches Profil",                 "fr": "Profil Windows",                            "es": "Perfil Windows",                             "pt": "Perfil Windows",                            "pl": "Profil Windows",                             "uk": "Режим «як Windows»",                         "zh": "Windows 类似预设",               "ja": "Windowsライクなプリセット"},
    "win_hint":      {"en": "One click: zram (50% RAM, lzo-rle) + overcommit=1 + swappiness=80 + disable systemd-oomd + panic_on_oom=0.\nSystem slows down under load instead of killing processes.", "ru": "Одним кликом: zram (50% ОЗУ, lzo-rle) + overcommit=1 + swappiness=80 + отключить systemd-oomd + panic_on_oom=0.\nСистема замедляется под нагрузкой вместо убийства процессов.", "de": "Ein Klick: zram (50% RAM) + overcommit=1 + swappiness=80 + systemd-oomd aus + panic_on_oom=0.", "fr": "Un clic : zram (50% RAM) + overcommit=1 + swappiness=80 + désactiver systemd-oomd + panic_on_oom=0.", "es": "Un clic: zram (50% RAM) + overcommit=1 + swappiness=80 + desactivar systemd-oomd + panic_on_oom=0.", "pt": "Um clique: zram (50% RAM) + overcommit=1 + swappiness=80 + desativar systemd-oomd + panic_on_oom=0.", "pl": "Jeden klik: zram (50% RAM) + overcommit=1 + swappiness=80 + wyłącz systemd-oomd + panic_on_oom=0.", "uk": "Один клік: zram (50% ОЗУ) + overcommit=1 + swappiness=80 + вимкнути systemd-oomd + panic_on_oom=0.", "zh": "一键：zram（50% RAM）+ overcommit=1 + swappiness=80 + 禁用 systemd-oomd + panic_on_oom=0。", "ja": "ワンクリック: zram(RAM50%) + overcommit=1 + swappiness=80 + systemd-oomd無効 + panic_on_oom=0。"},
    "win_btn":       {"en": "Apply Windows-like preset",             "ru": "Применить режим «как Windows»",                  "de": "Windows-Profil anwenden",                  "fr": "Appliquer le profil Windows",               "es": "Aplicar perfil Windows",                     "pt": "Aplicar perfil Windows",                    "pl": "Zastosuj profil Windows",                    "uk": "Застосувати режим «як Windows»",              "zh": "应用 Windows 类似预设",          "ja": "Windowsライクなプリセットを適用"},
}


class SwapWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, command_args):
        super().__init__()
        self.command_args = command_args

    def run(self):
        elevator = privilege.find_elevator()
        if not elevator:
            self.finished.emit(False, "No elevation tool found.")
            return

        if getattr(sys, 'frozen', False):
            backend_script = os.path.join(os.path.dirname(sys.executable), "equestria-os-swap-backend")
            inner = [backend_script] + self.command_args
        else:
            backend_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swap_backend.py")
            inner = [sys.executable, backend_script] + self.command_args

        cmd = [elevator, "--"] + inner if os.path.basename(elevator) == "kdesu" else [elevator] + inner

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate()

        if proc.returncode == 0:
            self.finished.emit(True, stdout.strip())
        else:
            self.finished.emit(False, stderr.strip())


class SwapManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = os.getenv("LANG", "en")[:2]
        if self.current_lang not in LANGS:
            self.current_lang = "en"

        self._setup_ui()
        self._load_data()

    def t(self, key):
        d = STRINGS.get(key, {})
        return d.get(self.current_lang) or d.get("en", key)

    def _change_lang(self, lang):
        self.current_lang = lang
        for code, btn in self._lang_btns.items():
            btn.setProperty("active", "true" if code == lang else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._refresh_ui()

    def _make_divider(self):
        d = QFrame()
        d.setObjectName("Divider")
        d.setFrameShape(QFrame.Shape.HLine)
        d.setFixedHeight(1)
        return d

    def _setup_ui(self):
        self.setWindowTitle(self.t("title"))
        self.resize(780, 820)

        base_path = os.path.dirname(os.path.abspath(__file__))

        title_font_family = "sans-serif"
        font_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        if os.path.exists(font_path):
            fid = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                title_font_family = families[0]

        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            qss = open(qss_path).read()
            qss = qss.replace("{{CHECKMARK_SVG_PATH}}", CHECKMARK_SVG)
            qss = qss.replace("{{TITLE_FONT}}", f'"{title_font_family}"')
            qss += """
            QSlider::groove:horizontal { border-radius: 4px; height: 6px; background: #313244; }
            QSlider::handle:horizontal { background: #f5c2e7; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::handle:horizontal:hover { background: #f2cdcd; }
            QComboBox { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a; border-radius: 6px; padding: 4px 8px; min-height: 28px; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView { background-color: #1e1e2e; color: #cdd6f4; selection-background-color: #313244; border: 1px solid #45475a; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #1e1e2e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal { background: #1e1e2e; height: 8px; border-radius: 4px; }
            QScrollBar::handle:horizontal { background: #45475a; border-radius: 4px; min-width: 20px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            QLabel#HintLabel { color: #6c7086; font-size: 11px; font-style: italic; }
            QMenu { background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #313244; }
            QMenu::separator { height: 1px; background: #45475a; margin: 4px 8px; }
            QLabel#ZramStatusLabel { color: #a6e3a1; font-size: 12px; font-weight: bold; }
            QPushButton#WindowsBtn { background-color: rgb(60, 50, 100); border: 2px solid rgb(137, 180, 250); border-radius: 8px; color: rgb(137, 180, 250); font-size: 13px; font-weight: bold; padding: 6px 18px; }
            QPushButton#WindowsBtn:hover { background-color: rgb(80, 70, 130); }
            QPushButton#WindowsBtn:pressed { background-color: rgb(40, 35, 80); }
            """
            self.setStyleSheet(qss)

        # Outer widget
        central = QWidget()
        central.setObjectName("CentralBg")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area so content is always accessible
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("CentralBg")
        scroll.setWidget(content)
        L = QVBoxLayout(content)
        L.setContentsMargins(30, 20, 30, 20)
        L.setSpacing(12)

        # ── Title & Lang ──────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        self.app_title = QLabel(self.t("title"))
        self.app_title.setObjectName("AppTitle")
        title_row.addWidget(self.app_title)
        title_row.addStretch()

        self._lang_btns = {}
        lang_row = QHBoxLayout()
        lang_row.setSpacing(4)
        for code in LANGS:
            btn = QPushButton(code.upper())
            btn.setProperty("cssClass", "lang-button")
            btn.setProperty("active", "true" if code == self.current_lang else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self._change_lang(c))
            lang_row.addWidget(btn)
            self._lang_btns[code] = btn
        title_row.addLayout(lang_row)
        L.addLayout(title_row)
        L.addWidget(self._make_divider())

        # ── Active Swap Info ──────────────────────────────────────────────────
        info_row = QHBoxLayout()
        self.lbl_current = QLabel(self.t("current_swap"))
        self.lbl_current.setObjectName("SectionLabel")
        info_row.addWidget(self.lbl_current)
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setObjectName("BrowseBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._load_data)
        info_row.addWidget(self.refresh_btn)
        info_row.addStretch()
        L.addLayout(info_row)
        self.info_lbl = QLabel(self.t("no_swap"))
        self.info_lbl.setObjectName("StatusLabel")
        L.addWidget(self.info_lbl)
        L.addWidget(self._make_divider())

        # ── Swap File Settings ────────────────────────────────────────────────
        self.lbl_path = QLabel(self.t("path"))
        self.lbl_path.setObjectName("SectionLabel")
        L.addWidget(self.lbl_path)
        self.path_input = QLineEdit()
        self.path_input.setObjectName("DestEdit")
        self.path_input.setText("/swapfile")
        L.addWidget(self.path_input)

        size_row = QHBoxLayout()
        self.lbl_size = QLabel(self.t("size"))
        self.lbl_size.setObjectName("SectionLabel")
        size_row.addWidget(self.lbl_size)
        self.size_spin = QSpinBox()
        self.size_spin.setObjectName("SourceEdit")
        self.size_spin.setRange(1, 256)
        self.size_spin.setValue(32)
        self.size_spin.setSuffix(" GB")
        self.size_spin.setFixedHeight(34)
        size_row.addWidget(self.size_spin)
        size_row.addStretch()
        L.addLayout(size_row)

        self.fstab_cb = QCheckBox(self.t("fstab_chk"))
        self.fstab_cb.setChecked(True)
        self.fstab_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fstab_cb.setObjectName("SwapCheckBox")
        L.addWidget(self.fstab_cb)

        self.apply_btn = QPushButton(self.t("btn_apply"))
        self.apply_btn.setObjectName("RelocateBtn")
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.clicked.connect(self._apply_swap)
        L.addWidget(self.apply_btn)

        action_row = QHBoxLayout()
        self.disable_btn = QPushButton(self.t("btn_disable"))
        self.disable_btn.setObjectName("BrowseBtn")
        self.disable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.disable_btn.clicked.connect(self._disable_swap)
        self.delete_btn = QPushButton(self.t("btn_delete"))
        self.delete_btn.setObjectName("DangerBtn")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(self._delete_swap)
        action_row.addWidget(self.disable_btn)
        action_row.addWidget(self.delete_btn)
        L.addLayout(action_row)
        L.addWidget(self._make_divider())

        # ── Swappiness ────────────────────────────────────────────────────────
        self.lbl_swappiness = QLabel(self.t("swappiness"))
        self.lbl_swappiness.setObjectName("SectionLabel")
        L.addWidget(self.lbl_swappiness)
        swapp_row = QHBoxLayout()
        self.swapp_slider = QSlider(Qt.Orientation.Horizontal)
        self.swapp_slider.setRange(0, 100)
        self.swapp_slider.setValue(60)
        self.swapp_slider.valueChanged.connect(lambda v: self.swapp_val_lbl.setText(str(v)))
        self.swapp_val_lbl = QLabel("60")
        self.swapp_val_lbl.setObjectName("StatusLabel")
        self.swapp_val_lbl.setFixedWidth(30)
        swapp_row.addWidget(self.swapp_slider)
        swapp_row.addWidget(self.swapp_val_lbl)
        L.addLayout(swapp_row)
        self.apply_swapp_btn = QPushButton(self.t("btn_swapp"))
        self.apply_swapp_btn.setObjectName("BrowseBtn")
        self.apply_swapp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_swapp_btn.clicked.connect(self._apply_swappiness)
        L.addWidget(self.apply_swapp_btn)
        L.addWidget(self._make_divider())

        # ── Fast Swap (zram) ──────────────────────────────────────────────────
        self.lbl_zram_section = QLabel(self.t("zram_section"))
        self.lbl_zram_section.setObjectName("SectionLabel")
        L.addWidget(self.lbl_zram_section)

        self.lbl_zram_hint = QLabel(self.t("zram_hint"))
        self.lbl_zram_hint.setObjectName("HintLabel")
        self.lbl_zram_hint.setWordWrap(True)
        L.addWidget(self.lbl_zram_hint)

        zram_status_row = QHBoxLayout()
        self.lbl_zram_status_key = QLabel(self.t("zram_status"))
        self.lbl_zram_status_key.setObjectName("SectionLabel")
        self.lbl_zram_status_val = QLabel(self.t("zram_inactive"))
        self.lbl_zram_status_val.setObjectName("ZramStatusLabel")
        zram_status_row.addWidget(self.lbl_zram_status_key)
        zram_status_row.addWidget(self.lbl_zram_status_val)
        zram_status_row.addStretch()
        L.addLayout(zram_status_row)

        zram_cfg_row = QHBoxLayout()
        self.lbl_zram_size = QLabel(self.t("zram_size_lbl"))
        self.lbl_zram_size.setObjectName("SectionLabel")
        zram_cfg_row.addWidget(self.lbl_zram_size)

        self.zram_size_spin = QSpinBox()
        self.zram_size_spin.setObjectName("SourceEdit")
        self.zram_size_spin.setRange(1, 128)
        default_zram = max(4, _get_ram_gb() // 2)
        self.zram_size_spin.setValue(default_zram)
        self.zram_size_spin.setSuffix(" GB")
        self.zram_size_spin.setFixedHeight(34)
        zram_cfg_row.addWidget(self.zram_size_spin)

        self.lbl_zram_algo = QLabel(self.t("zram_algo_lbl"))
        self.lbl_zram_algo.setObjectName("SectionLabel")
        zram_cfg_row.addWidget(self.lbl_zram_algo)

        self.zram_algo_combo = QComboBox()
        self.zram_algo_combo.addItem("lzo-rle")
        self.zram_algo_combo.addItem("zstd")
        self.zram_algo_combo.addItem("lz4")
        self.zram_algo_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        zram_cfg_row.addWidget(self.zram_algo_combo)
        zram_cfg_row.addStretch()
        L.addLayout(zram_cfg_row)

        zram_btn_row = QHBoxLayout()
        self.zram_enable_btn = QPushButton(self.t("zram_enable"))
        self.zram_enable_btn.setObjectName("BrowseBtn")
        self.zram_enable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zram_enable_btn.clicked.connect(self._enable_zram)
        self.zram_disable_btn = QPushButton(self.t("zram_disable"))
        self.zram_disable_btn.setObjectName("DangerBtn")
        self.zram_disable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zram_disable_btn.clicked.connect(self._disable_zram)
        self.zram_disable_btn.setEnabled(False)
        zram_btn_row.addWidget(self.zram_enable_btn)
        zram_btn_row.addWidget(self.zram_disable_btn)
        L.addLayout(zram_btn_row)
        L.addWidget(self._make_divider())

        # ── Memory Pressure & OOM Killer ──────────────────────────────────────
        self.lbl_oom_section = QLabel(self.t("oom_section"))
        self.lbl_oom_section.setObjectName("SectionLabel")
        L.addWidget(self.lbl_oom_section)

        self.lbl_oom_hint = QLabel(self.t("oom_hint"))
        self.lbl_oom_hint.setObjectName("HintLabel")
        self.lbl_oom_hint.setWordWrap(True)
        L.addWidget(self.lbl_oom_hint)

        overcommit_row = QHBoxLayout()
        self.lbl_overcommit = QLabel(self.t("oom_overcommit"))
        self.lbl_overcommit.setObjectName("SectionLabel")
        overcommit_row.addWidget(self.lbl_overcommit)
        self.overcommit_combo = QComboBox()
        self.overcommit_combo.addItem(self.t("oom_mode_0"))
        self.overcommit_combo.addItem(self.t("oom_mode_1"))
        self.overcommit_combo.addItem(self.t("oom_mode_2"))
        self.overcommit_combo.setMinimumWidth(280)
        self.overcommit_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        overcommit_row.addWidget(self.overcommit_combo)
        overcommit_row.addStretch()
        L.addLayout(overcommit_row)

        # Fix transparent dropdown: style view() directly so global
        # "QWidget { background: transparent }" in style.qss doesn't win.
        _dv = ("background-color: #1e1e2e; color: #cdd6f4; "
               "selection-background-color: #313244; selection-color: #cdd6f4; "
               "border: 1px solid #45475a;")
        self.zram_algo_combo.view().setStyleSheet(_dv)
        self.overcommit_combo.view().setStyleSheet(_dv)

        self.oomd_cb = QCheckBox(self.t("oom_oomd_cb"))
        self.oomd_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.oomd_cb.setObjectName("SwapCheckBox")
        L.addWidget(self.oomd_cb)

        self.panic_oom_cb = QCheckBox(self.t("oom_panic_cb"))
        self.panic_oom_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.panic_oom_cb.setObjectName("SwapCheckBox")
        L.addWidget(self.panic_oom_cb)

        self.apply_oom_btn = QPushButton(self.t("oom_apply"))
        self.apply_oom_btn.setObjectName("BrowseBtn")
        self.apply_oom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_oom_btn.clicked.connect(self._apply_oom_settings)
        L.addWidget(self.apply_oom_btn)
        L.addWidget(self._make_divider())

        # ── Windows-like Preset ───────────────────────────────────────────────
        self.lbl_win_section = QLabel(self.t("win_section"))
        self.lbl_win_section.setObjectName("SectionLabel")
        L.addWidget(self.lbl_win_section)

        self.lbl_win_hint = QLabel(self.t("win_hint"))
        self.lbl_win_hint.setObjectName("HintLabel")
        self.lbl_win_hint.setWordWrap(True)
        L.addWidget(self.lbl_win_hint)

        self.win_btn = QPushButton(self.t("win_btn"))
        self.win_btn.setObjectName("WindowsBtn")
        self.win_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.win_btn.clicked.connect(self._apply_windows_preset)
        L.addWidget(self.win_btn)

        L.addStretch()

        # ── Progress ──────────────────────────────────────────────────────────
        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("ProgressFrame")
        self.progress_frame.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_frame)
        prog_layout.setContentsMargins(0, 10, 0, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        prog_layout.addWidget(self.progress_bar)
        self.prog_status_lbl = QLabel(self.t("status_app"))
        self.prog_status_lbl.setObjectName("StatusLabel")
        self.prog_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prog_layout.addWidget(self.prog_status_lbl)
        L.addWidget(self.progress_frame)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self):
        # Swap files
        try:
            result = subprocess.run(["swapon", "--show=NAME,SIZE,TYPE"], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) <= 1:
                self.info_lbl.setText(self.t("no_swap"))
            else:
                formatted = []
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        formatted.append(f"• {parts[0]}  —  {parts[1]}")
                self.info_lbl.setText("\n".join(formatted))
        except Exception:
            self.info_lbl.setText(self.t("no_swap"))

        # Swappiness
        try:
            with open("/proc/sys/vm/swappiness") as f:
                val = int(f.read().strip())
                self.swapp_slider.setValue(val)
                self.swapp_val_lbl.setText(str(val))
        except Exception:
            pass

        # zram status
        try:
            r = subprocess.run(["swapon", "--show=NAME,SIZE,TYPE"], capture_output=True, text=True)
            zram_line = next((l for l in r.stdout.splitlines() if "/dev/zram" in l), None)
            if zram_line:
                parts = zram_line.split()
                size_info = parts[1] if len(parts) > 1 else "?"
                self.lbl_zram_status_val.setText(self.t("zram_active").format(size_info))
                self.zram_enable_btn.setEnabled(False)
                self.zram_disable_btn.setEnabled(True)
            else:
                self.lbl_zram_status_val.setText(self.t("zram_inactive"))
                self.zram_enable_btn.setEnabled(True)
                self.zram_disable_btn.setEnabled(False)
        except Exception:
            self.lbl_zram_status_val.setText(self.t("zram_inactive"))

        # Overcommit policy
        try:
            with open("/proc/sys/vm/overcommit_memory") as f:
                self.overcommit_combo.setCurrentIndex(max(0, min(2, int(f.read().strip()))))
        except Exception:
            pass

        # systemd-oomd state
        try:
            r = subprocess.run(["systemctl", "is-enabled", "systemd-oomd"], capture_output=True, text=True)
            self.oomd_cb.setChecked(r.stdout.strip() not in ("enabled", "static", "preset"))
        except Exception:
            self.oomd_cb.setChecked(False)

        # panic_on_oom (checked = prevent panic = value is 0)
        # Parameter may not exist on all kernel builds
        _panic_path = "/proc/sys/kernel/panic_on_oom"
        if os.path.exists(_panic_path):
            try:
                with open(_panic_path) as f:
                    self.panic_oom_cb.setChecked(int(f.read().strip()) == 0)
                self.panic_oom_cb.setEnabled(True)
            except Exception:
                self.panic_oom_cb.setChecked(True)
                self.panic_oom_cb.setEnabled(True)
        else:
            self.panic_oom_cb.setChecked(False)
            self.panic_oom_cb.setEnabled(False)
            self.panic_oom_cb.setText(self.t("oom_panic_cb") + " (n/a)")

    # ── Language refresh ──────────────────────────────────────────────────────

    def _refresh_ui(self):
        self.setWindowTitle(self.t("title"))
        self.app_title.setText(self.t("title"))
        self.lbl_current.setText(self.t("current_swap"))
        self.lbl_path.setText(self.t("path"))
        self.lbl_size.setText(self.t("size"))
        self.lbl_swappiness.setText(self.t("swappiness"))
        self.fstab_cb.setText(self.t("fstab_chk"))
        self.apply_btn.setText(self.t("btn_apply"))
        self.apply_swapp_btn.setText(self.t("btn_swapp"))
        self.disable_btn.setText(self.t("btn_disable"))
        self.delete_btn.setText(self.t("btn_delete"))
        self.prog_status_lbl.setText(self.t("status_app"))
        # zram
        self.lbl_zram_section.setText(self.t("zram_section"))
        self.lbl_zram_hint.setText(self.t("zram_hint"))
        self.lbl_zram_status_key.setText(self.t("zram_status"))
        self.lbl_zram_size.setText(self.t("zram_size_lbl"))
        self.lbl_zram_algo.setText(self.t("zram_algo_lbl"))
        self.zram_enable_btn.setText(self.t("zram_enable"))
        self.zram_disable_btn.setText(self.t("zram_disable"))
        # OOM
        self.lbl_oom_section.setText(self.t("oom_section"))
        self.lbl_oom_hint.setText(self.t("oom_hint"))
        self.lbl_overcommit.setText(self.t("oom_overcommit"))
        cur = self.overcommit_combo.currentIndex()
        self.overcommit_combo.setItemText(0, self.t("oom_mode_0"))
        self.overcommit_combo.setItemText(1, self.t("oom_mode_1"))
        self.overcommit_combo.setItemText(2, self.t("oom_mode_2"))
        self.overcommit_combo.setCurrentIndex(cur)
        self.oomd_cb.setText(self.t("oom_oomd_cb"))
        self.panic_oom_cb.setText(self.t("oom_panic_cb"))
        self.apply_oom_btn.setText(self.t("oom_apply"))
        # Windows preset
        self.lbl_win_section.setText(self.t("win_section"))
        self.lbl_win_hint.setText(self.t("win_hint"))
        self.win_btn.setText(self.t("win_btn"))
        self._load_data()

    # ── Backend plumbing ──────────────────────────────────────────────────────

    def _all_interactive(self):
        return (
            self.apply_btn, self.disable_btn, self.delete_btn,
            self.path_input, self.size_spin, self.fstab_cb,
            self.refresh_btn, self.apply_swapp_btn, self.swapp_slider,
            self.zram_enable_btn, self.zram_disable_btn, self.zram_size_spin, self.zram_algo_combo,
            self.overcommit_combo, self.oomd_cb, self.panic_oom_cb, self.apply_oom_btn,
            self.win_btn,
        )

    def _run_backend(self, args):
        for w in self._all_interactive():
            w.setEnabled(False)
        self.progress_frame.setVisible(True)
        self.worker = SwapWorker(args)
        self.worker.finished.connect(self._on_worker_done)
        self.worker.start()

    def _on_worker_done(self, success, message):
        for w in self._all_interactive():
            w.setEnabled(True)
        self.progress_frame.setVisible(False)
        if success:
            QMessageBox.information(self, "Success", self.t("success"))
        else:
            # Only show "failed to get root" prefix for actual privilege errors
            if not message or "elevation" in message.lower() or message == "No elevation tool found.":
                text = f"{self.t('err_elevate')}\n{message}"
            else:
                text = message
            QMessageBox.critical(self, "Error", text)
        self._load_data()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _apply_swap(self):
        path = self.path_input.text().strip()
        if not path:
            return
        self._run_backend(["--create", path, str(self.size_spin.value()),
                           "yes" if self.fstab_cb.isChecked() else "no"])

    def _disable_swap(self):
        path = self.path_input.text().strip()
        if not path:
            return
        self._run_backend(["--disable", path])

    def _delete_swap(self):
        path = self.path_input.text().strip()
        if not path:
            return
        if QMessageBox.question(self, "Confirm Delete", f"Delete {path} completely?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._run_backend(["--delete", path])

    def _apply_swappiness(self):
        self._run_backend(["--swappiness", str(self.swapp_slider.value())])

    def _enable_zram(self):
        self._run_backend([
            "--zram-enable", str(self.zram_size_spin.value()),
            self.zram_algo_combo.currentText(),
        ])

    def _disable_zram(self):
        self._run_backend(["--zram-disable"])

    def _apply_oom_settings(self):
        self._run_backend([
            "--overcommit", str(self.overcommit_combo.currentIndex()),
            "--oomd",       "disable" if self.oomd_cb.isChecked() else "enable",
            "--panic-on-oom", "0" if self.panic_oom_cb.isChecked() else "1",
        ])

    def _apply_windows_preset(self):
        zram_gb = max(4, _get_ram_gb() // 2)
        self._run_backend([
            "--zram-enable", str(zram_gb), "lzo-rle",
            "--overcommit",    "1",
            "--oomd",          "disable",
            "--swappiness",    "80",
            "--panic-on-oom",  "0",
        ])


def main():
    generate_assets()
    app = QApplication(sys.argv)
    app.setDesktopFileName("equestria-os-swap-manager")
    win = SwapManagerApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
