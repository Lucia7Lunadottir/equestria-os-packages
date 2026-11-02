import sys
import os
import re
import pwd
import json
import shlex
import shutil
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QFrame, QMessageBox,
    QCheckBox, QProgressBar, QScrollArea, QDialog, QDoubleSpinBox,
    QAbstractButton
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, pyqtProperty, QPropertyAnimation,
    QEasingCurve, QSize, QRectF
)
from PyQt6.QtGui import QFontDatabase, QFont, QIcon, QPainter, QColor

try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt
from equestria_kit.i18n import detect_language
from equestria_kit.widgets import font_families

import privilege
import disk_backend  # только константы и build_mkfs_cmd для предпросмотра


class SwitchToggle(QAbstractButton):
    """Переключатель-пилюля с бегунком: фон плавно заливается акцентным
    цветом, бегунок едет вправо. Рисуется вручную — QSS такое не умеет."""
    stateChanged = pyqtSignal(int)

    TRACK_W, TRACK_H, KNOB_M = 34, 18, 3
    # Роли общей темы (выкл → вкл); цвета берутся в момент отрисовки,
    # поэтому смена темы в переключателе персонажей видна сразу.
    TRACK = ("surface1", "accent")
    KNOB = ("text", "on_accent")
    TEXT = ("subtext", "accent")

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self._label = label
        self._pos = 0.0
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        f = QFont("monospace")
        f.setPixelSize(12)
        self.setFont(f)
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggle)

    def _on_toggle(self, checked):
        target = 1.0 if checked else 0.0
        if self.isVisible():
            self._anim.stop()
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._pos = target
            self.update()
        self.stateChanged.emit(2 if checked else 0)

    def setChecked(self, val):
        super().setChecked(bool(val))

    def setLabelText(self, label):
        self._label = label
        self.updateGeometry()
        self.update()

    def _get_pos(self):
        return self._pos

    def _set_pos(self, v):
        self._pos = v
        self.update()

    knobPos = pyqtProperty(float, _get_pos, _set_pos)

    @staticmethod
    def _blend(roles, t, text=False):
        pick = kit_qt.text_color if text else kit_qt.theme_color
        a, b = (pick(r) for r in roles)
        return QColor(round(a.red() + (b.red() - a.red()) * t),
                      round(a.green() + (b.green() - a.green()) * t),
                      round(a.blue() + (b.blue() - a.blue()) * t))

    def sizeHint(self):
        fm = self.fontMetrics()
        w = self.TRACK_W + 8 + fm.horizontalAdvance(self._label) + 4
        return QSize(w, max(self.TRACK_H + 6, fm.height() + 6))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._pos
        ty = (self.height() - self.TRACK_H) / 2

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._blend(self.TRACK, t))
        p.drawRoundedRect(QRectF(0, ty, self.TRACK_W, self.TRACK_H),
                          self.TRACK_H / 2, self.TRACK_H / 2)

        kd = self.TRACK_H - 2 * self.KNOB_M
        kx = self.KNOB_M + t * (self.TRACK_W - kd - 2 * self.KNOB_M)
        p.setBrush(self._blend(self.KNOB, t))
        p.drawEllipse(QRectF(kx, ty + self.KNOB_M, kd, kd))

        p.setPen(self._blend(self.TEXT, t, text=True))
        p.drawText(QRectF(self.TRACK_W + 8, 0,
                          self.width() - self.TRACK_W - 8, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._label)


class FstabOptionsWidget(QFrame):
    """User-friendly fstab options editor."""

    OPTS_TIPS = {
        "noatime":    {"en": "Don't update file access time — improves disk performance",
                       "ru": "Не обновлять время последнего доступа — ускоряет работу диска", "de": "Zugriffszeit von Dateien nicht aktualisieren — verbessert die Leistung", "fr": "Ne pas mettre à jour l'heure d'accès aux fichiers — améliore les performances", "es": "No actualizar la hora de acceso a archivos — mejora el rendimiento del disco", "pt": "Não atualizar o horário de acesso aos arquivos — melhora o desempenho", "pl": "Nie aktualizuj czasu dostępu do plików — poprawia wydajność dysku", "uk": "Не оновлювати час доступу до файлів — підвищує швидкодію диска", "zh": "不更新文件访问时间——提高磁盘性能", "zh_TW": "不更新檔案訪問時間——提高磁碟效能", "ja": "ファイルのアクセス時刻を更新しない — ディスク性能が向上", "ko": "파일 접근 시간을 갱신하지 않음 — 디스크 성능 향상"},
        "nofail":     {"en": "Don't fail boot if the drive is missing or unavailable",
                       "ru": "Не прерывать загрузку системы, если диск недоступен", "de": "Start nicht abbrechen, wenn das Laufwerk fehlt oder nicht verfügbar ist", "fr": "Ne pas faire échouer le démarrage si le disque est absent ou indisponible", "es": "No fallar el arranque si la unidad falta o no está disponible", "pt": "Não falhar a inicialização se a unidade estiver ausente ou indisponível", "pl": "Nie przerywaj uruchamiania, jeśli dysku brak lub jest niedostępny", "uk": "Не зривати завантаження, якщо диска немає або він недоступний", "zh": "驱动器缺失或不可用时不让启动失败", "zh_TW": "驅動器缺失或不可用時不讓啟動失敗", "ja": "ドライブがない、または使用できなくても起動を失敗させない", "ko": "드라이브가 없거나 사용할 수 없어도 부팅 실패로 처리하지 않음"},
        "ro":         {"en": "Mount read-only — no writes allowed",
                       "ru": "Монтировать только для чтения — запись запрещена", "de": "Schreibgeschützt einhängen — kein Schreiben möglich", "fr": "Monter en lecture seule — aucune écriture", "es": "Montar en solo lectura — sin escritura", "pt": "Montar somente leitura — sem gravação", "pl": "Montuj tylko do odczytu — bez zapisu", "uk": "Монтувати лише для читання — без запису", "zh": "只读挂载——禁止写入", "zh_TW": "只讀掛載——禁止寫入", "ja": "読み取り専用でマウント — 書き込み不可", "ko": "읽기 전용으로 마운트 — 쓰기 불가"},
        "exec":       {"en": "Explicitly allow executing binaries.\n"
                             "Use this to override 'noexec' from an old fstab entry.\n"
                             "Not needed if noexec is not set — exec is the default.",
                       "ru": "Явно разрешить запуск исполняемых файлов.\n"
                             "Используй чтобы перебить 'noexec' из старой записи fstab.\n"
                             "Не нужен если noexec не установлен — exec включён по умолчанию.", "de": "Ausführen von Programmen ausdrücklich erlauben.\nÜberschreibt 'noexec' aus einem alten fstab-Eintrag.\nNicht nötig, wenn noexec nicht gesetzt ist — exec ist Standard.", "fr": "Autoriser explicitement l'exécution des programmes.\nPermet d'annuler un 'noexec' d'une ancienne entrée fstab.\nInutile si noexec n'est pas défini — exec est la valeur par défaut.", "es": "Permitir explícitamente ejecutar programas.\nSirve para anular 'noexec' de una entrada antigua de fstab.\nNo hace falta si noexec no está puesto — exec es el valor predeterminado.", "pt": "Permitir explicitamente a execução de programas.\nUse para anular 'noexec' de uma entrada fstab antiga.\nDesnecessário se noexec não estiver definido — exec é o padrão.", "pl": "Jawnie zezwól na uruchamianie programów.\nNadpisuje 'noexec' ze starego wpisu fstab.\nNiepotrzebne, jeśli noexec nie jest ustawione — exec jest domyślne.", "uk": "Явно дозволити запуск програм.\nСкасовує 'noexec' зі старого запису fstab.\nНепотрібно, якщо noexec не задано — exec діє за замовчуванням.", "zh": "明确允许执行程序。\n用于覆盖旧 fstab 条目中的 'noexec'。\n未设置 noexec 时不需要——exec 是默认值。", "zh_TW": "明確允許執行程式。\n用於覆蓋舊 fstab 條目中的 'noexec'。\n未設定 noexec 時不需要——exec 是預設值。", "ja": "プログラムの実行を明示的に許可します。\n古い fstab エントリの 'noexec' を上書きする場合に使います。\nnoexec が設定されていなければ不要です — exec が既定です。", "ko": "바이너리 실행을 명시적으로 허용합니다.\n이전 fstab 항목의 'noexec'를 덮어쓸 때 사용하세요.\nnoexec가 설정되지 않았다면 필요 없습니다 — exec가 기본값입니다."},
        "noexec":     {"en": "Prevent execution of any binaries on this partition.\n"
                             "⚠ Don't enable for Steam game drives!",
                       "ru": "Запретить запуск исполняемых файлов с этого раздела.\n"
                             "⚠ Не включать для дисков с играми Steam!", "de": "Ausführen jeglicher Programme auf dieser Partition verhindern.\n⚠ Nicht für Steam-Spielelaufwerke aktivieren!", "fr": "Empêcher l'exécution de tout programme sur cette partition.\n⚠ Ne pas activer pour les disques de jeux Steam !", "es": "Impedir la ejecución de cualquier programa en esta partición.\n⚠ ¡No lo active en unidades de juegos de Steam!", "pt": "Impedir a execução de qualquer programa nesta partição.\n⚠ Não ative em unidades de jogos da Steam!", "pl": "Zablokuj uruchamianie jakichkolwiek programów na tej partycji.\n⚠ Nie włączaj dla dysków z grami Steam!", "uk": "Заборонити запуск будь-яких програм на цьому розділі.\n⚠ Не вмикайте для дисків з іграми Steam!", "zh": "禁止在此分区上执行任何程序。\n⚠ 不要对 Steam 游戏驱动器启用！", "zh_TW": "禁止在此分割槽上執行任何程式。\n⚠ 不要對 Steam 遊戲驅動器啟用！", "ja": "このパーティションでのプログラム実行をすべて禁止します。\n⚠ Steam のゲーム用ドライブでは有効にしないでください！", "ko": "이 파티션에서 모든 바이너리 실행을 막습니다.\n⚠ Steam 게임 드라이브에는 켜지 마세요!"},
        "noauto":     {"en": "Don't auto-mount when 'mount -a' runs — mount manually only",
                       "ru": "Не монтировать при 'mount -a' — только вручную", "de": "Bei 'mount -a' nicht automatisch einhängen — nur manuell", "fr": "Ne pas monter automatiquement avec 'mount -a' — montage manuel uniquement", "es": "No montar automáticamente con 'mount -a' — solo montaje manual", "pt": "Não montar automaticamente com 'mount -a' — apenas montagem manual", "pl": "Nie montuj automatycznie przy 'mount -a' — tylko ręcznie", "uk": "Не монтувати автоматично під час 'mount -a' — лише вручну", "zh": "运行 'mount -a' 时不自动挂载——仅手动挂载", "zh_TW": "執行 'mount -a' 時不自動掛載——僅手動掛載", "ja": "'mount -a' 実行時に自動マウントしない — 手動マウントのみ", "ko": "'mount -a' 실행 시 자동 마운트하지 않음 — 직접 마운트만"},
        "uid":        {"en": "User ID that owns all files on this drive.\n"
                             "Find yours in terminal: id -u",
                       "ru": "UID пользователя-владельца всех файлов на диске.\n"
                             "Узнать в терминале: id -u", "de": "Benutzer-ID, der alle Dateien auf diesem Laufwerk gehören.\nIm Terminal ermitteln: id -u", "fr": "ID de l'utilisateur propriétaire de tous les fichiers de ce disque.\nPour le connaître dans un terminal : id -u", "es": "ID del usuario propietario de todos los archivos de esta unidad.\nConsúltelo en la terminal: id -u", "pt": "ID do usuário dono de todos os arquivos desta unidade.\nDescubra no terminal: id -u", "pl": "ID użytkownika będącego właścicielem wszystkich plików na tym dysku.\nSprawdź w terminalu: id -u", "uk": "ID користувача, якому належать усі файли на цьому диску.\nДізнайтеся в терміналі: id -u", "zh": "拥有此驱动器上所有文件的用户 ID。\n在终端中查询：id -u", "zh_TW": "擁有此驅動器上所有檔案的使用者 ID。\n在終端中查詢：id -u", "ja": "このドライブ上の全ファイルを所有するユーザー ID。\nターミナルで確認：id -u", "ko": "이 드라이브의 모든 파일을 소유하는 사용자 ID.\n터미널에서 확인: id -u"},
        "gid":        {"en": "Group ID that owns all files on this drive.\n"
                             "Find yours in terminal: id -g",
                       "ru": "GID группы-владельца всех файлов на диске.\n"
                             "Узнать в терминале: id -g", "de": "Gruppen-ID, der alle Dateien auf diesem Laufwerk gehören.\nIm Terminal ermitteln: id -g", "fr": "ID du groupe propriétaire de tous les fichiers de ce disque.\nPour le connaître dans un terminal : id -g", "es": "ID del grupo propietario de todos los archivos de esta unidad.\nConsúltelo en la terminal: id -g", "pt": "ID do grupo dono de todos os arquivos desta unidade.\nDescubra no terminal: id -g", "pl": "ID grupy będącej właścicielem wszystkich plików na tym dysku.\nSprawdź w terminalu: id -g", "uk": "ID групи, якій належать усі файли на цьому диску.\nДізнайтеся в терміналі: id -g", "zh": "拥有此驱动器上所有文件的组 ID。\n在终端中查询：id -g", "zh_TW": "擁有此驅動器上所有檔案的組 ID。\n在終端中查詢：id -g", "ja": "このドライブ上の全ファイルを所有するグループ ID。\nターミナルで確認：id -g", "ko": "이 드라이브의 모든 파일을 소유하는 그룹 ID.\n터미널에서 확인: id -g"},
        "dmask":      {"en": "Permission mask for directories.\n"
                             "022  →  rwxr-xr-x  (recommended)",
                       "ru": "Маска прав доступа для папок.\n"
                             "022  →  rwxr-xr-x  (рекомендуется)", "de": "Rechtemaske für Verzeichnisse.\n022  →  rwxr-xr-x  (empfohlen)", "fr": "Masque de permissions pour les dossiers.\n022  →  rwxr-xr-x  (recommandé)", "es": "Máscara de permisos para carpetas.\n022  →  rwxr-xr-x  (recomendado)", "pt": "Máscara de permissões para pastas.\n022  →  rwxr-xr-x  (recomendado)", "pl": "Maska uprawnień dla katalogów.\n022  →  rwxr-xr-x  (zalecane)", "uk": "Маска прав для тек.\n022  →  rwxr-xr-x  (рекомендовано)", "zh": "目录的权限掩码。\n022  →  rwxr-xr-x  （推荐）", "zh_TW": "目錄的許可權掩碼。\n022  →  rwxr-xr-x  （推薦）", "ja": "ディレクトリの権限マスク。\n022  →  rwxr-xr-x  （推奨）", "ko": "디렉터리 권한 마스크.\n022  →  rwxr-xr-x  (권장)"},
        "fmask":      {"en": "Permission mask for files.\n"
                             "022  →  rwxr-xr-x  ← use this for Steam/games\n"
                             "133  →  rw-r--r--  ← use this for documents only",
                       "ru": "Маска прав доступа для файлов.\n"
                             "022  →  rwxr-xr-x  ← для Steam/игр\n"
                             "133  →  rw-r--r--  ← только для документов", "de": "Rechtemaske für Dateien.\n022  →  rwxr-xr-x  ← für Steam/Spiele\n133  →  rw-r--r--  ← nur für Dokumente", "fr": "Masque de permissions pour les fichiers.\n022  →  rwxr-xr-x  ← pour Steam/jeux\n133  →  rw-r--r--  ← pour les documents uniquement", "es": "Máscara de permisos para archivos.\n022  →  rwxr-xr-x  ← para Steam/juegos\n133  →  rw-r--r--  ← solo para documentos", "pt": "Máscara de permissões para arquivos.\n022  →  rwxr-xr-x  ← para Steam/jogos\n133  →  rw-r--r--  ← apenas para documentos", "pl": "Maska uprawnień dla plików.\n022  →  rwxr-xr-x  ← dla Steam/gier\n133  →  rw-r--r--  ← tylko dla dokumentów", "uk": "Маска прав для файлів.\n022  →  rwxr-xr-x  ← для Steam/ігор\n133  →  rw-r--r--  ← лише для документів", "zh": "文件的权限掩码。\n022  →  rwxr-xr-x  ← 用于 Steam/游戏\n133  →  rw-r--r--  ← 仅用于文档", "zh_TW": "檔案的許可權掩碼。\n022  →  rwxr-xr-x  ← 用於 Steam/遊戲\n133  →  rw-r--r--  ← 僅用於文件", "ja": "ファイルの権限マスク。\n022  →  rwxr-xr-x  ← Steam/ゲーム用\n133  →  rw-r--r--  ← 文書専用", "ko": "파일 권한 마스크.\n022  →  rwxr-xr-x  ← Steam/게임용\n133  →  rw-r--r--  ← 문서 전용"},
        "winnames":   {"en": "Restrict filenames to Windows-compatible characters.\n"
                             "⚠ DO NOT use for Steam game libraries — breaks game files!",
                       "ru": "Ограничить имена файлов символами, совместимыми с Windows.\n"
                             "⚠ НЕ использовать для библиотек Steam — ломает файлы игр!", "de": "Dateinamen auf Windows-kompatible Zeichen beschränken.\n⚠ NICHT für Steam-Spielebibliotheken verwenden — beschädigt Spieldateien!", "fr": "Limiter les noms de fichiers aux caractères compatibles Windows.\n⚠ NE PAS utiliser pour les bibliothèques de jeux Steam — cela casse les fichiers des jeux !", "es": "Limitar los nombres de archivo a caracteres compatibles con Windows.\n⚠ NO usar en bibliotecas de juegos de Steam — ¡estropea los archivos de los juegos!", "pt": "Restringir nomes de arquivos a caracteres compatíveis com o Windows.\n⚠ NÃO use em bibliotecas de jogos da Steam — quebra os arquivos dos jogos!", "pl": "Ogranicz nazwy plików do znaków zgodnych z Windows.\n⚠ NIE używaj dla bibliotek gier Steam — psuje pliki gier!", "uk": "Обмежити імена файлів символами, сумісними з Windows.\n⚠ НЕ використовуйте для бібліотек ігор Steam — ламає файли ігор!", "zh": "将文件名限制为 Windows 兼容字符。\n⚠ 不要用于 Steam 游戏库——会损坏游戏文件！", "zh_TW": "將檔名限制為 Windows 相容字元。\n⚠ 不要用於 Steam 遊戲庫——會損壞遊戲檔案！", "ja": "ファイル名を Windows 互換の文字に制限します。\n⚠ Steam のゲームライブラリには使わないでください — ゲームファイルが壊れます！", "ko": "파일 이름을 Windows 호환 문자로 제한합니다.\n⚠ Steam 게임 라이브러리에는 사용하지 마세요 — 게임 파일이 망가집니다!"},
        "compress":   {"en": "Transparent compression algorithm.\n"
                             "zstd = best speed/ratio on modern CPUs",
                       "ru": "Алгоритм прозрачного сжатия.\n"
                             "zstd = лучшее соотношение скорости и сжатия", "de": "Algorithmus der transparenten Komprimierung.\nzstd = bestes Verhältnis von Tempo zu Kompression auf modernen CPUs", "fr": "Algorithme de compression transparente.\nzstd = meilleur rapport vitesse/taux sur les processeurs modernes", "es": "Algoritmo de compresión transparente.\nzstd = mejor relación velocidad/compresión en CPU modernas", "pt": "Algoritmo de compressão transparente.\nzstd = melhor relação velocidade/taxa em CPUs modernas", "pl": "Algorytm przezroczystej kompresji.\nzstd = najlepszy stosunek szybkości do kompresji na nowoczesnych procesorach", "uk": "Алгоритм прозорого стиснення.\nzstd = найкраще співвідношення швидкості та стиснення на сучасних процесорах", "zh": "透明压缩算法。\nzstd = 在现代 CPU 上速度/压缩比最佳", "zh_TW": "透明壓縮演算法。\nzstd = 在現代 CPU 上速度/壓縮比最佳", "ja": "透過圧縮のアルゴリズム。\nzstd = 最新の CPU で速度と圧縮率のバランスが最良", "ko": "투명 압축 알고리즘.\nzstd = 최신 CPU에서 속도/압축률이 가장 좋음"},
        "autodefrag": {"en": "Automatic background defragmentation",
                       "ru": "Автоматическая дефрагментация в фоновом режиме", "de": "Automatische Defragmentierung im Hintergrund", "fr": "Défragmentation automatique en arrière-plan", "es": "Desfragmentación automática en segundo plano", "pt": "Desfragmentação automática em segundo plano", "pl": "Automatyczna defragmentacja w tle", "uk": "Автоматична дефрагментація у фоні", "zh": "后台自动碎片整理", "zh_TW": "後臺自動碎片整理", "ja": "バックグラウンドでの自動デフラグ", "ko": "자동 백그라운드 조각 모음"},
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OptionsFrame")
        self._fstype = "ext4"
        self._updating = False
        self._build()

    # ---- helpers ---------------------------------------------------------

    def _lbl(self, text):
        w = QLabel(text)
        w.setObjectName("OptionsSubLabel")
        return w

    def _mini(self, default, width=58):
        e = QLineEdit(default)
        e.setObjectName("SmallEdit")
        e.setFixedWidth(width)
        e.setFixedHeight(26)
        e.textChanged.connect(self._sync)
        return e

    def _tog(self, key):
        t = SwitchToggle(key)
        t.stateChanged.connect(self._sync)
        return t

    # ---- build -----------------------------------------------------------

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # ── Common flags ──────────────────────────────────────────────────
        self._cbs = {key: self._tog(key) for key in ("noatime", "nofail", "ro", "exec", "noexec", "noauto")}
        row_common = QHBoxLayout()
        row_common.setSpacing(8)
        for cb in self._cbs.values():
            row_common.addWidget(cb)
        row_common.addStretch()
        outer.addLayout(row_common)

        # ── NTFS / FAT options ────────────────────────────────────────────
        self._ntfs_frame = QFrame()
        nf = QVBoxLayout(self._ntfs_frame)
        nf.setContentsMargins(0, 2, 0, 0)
        nf.setSpacing(4)
        nf.addWidget(self._lbl("── NTFS / FAT options ───────────────────────────────────────────"))

        row_ids = QHBoxLayout()
        row_ids.setSpacing(6)
        row_ids.addWidget(self._lbl("uid:"))
        self._uid = self._mini("1000")
        row_ids.addWidget(self._uid)
        row_ids.addWidget(self._lbl("gid:"))
        self._gid = self._mini("1000")
        row_ids.addWidget(self._gid)
        row_ids.addWidget(self._lbl("dmask:"))
        self._dmask = self._mini("022", 52)
        row_ids.addWidget(self._dmask)
        row_ids.addWidget(self._lbl("fmask:"))
        self._fmask = self._mini("022", 52)
        row_ids.addWidget(self._fmask)
        self._winnames = SwitchToggle("windows_names")
        self._winnames.stateChanged.connect(self._sync)
        row_ids.addWidget(self._winnames)
        row_ids.addStretch()
        nf.addLayout(row_ids)
        outer.addWidget(self._ntfs_frame)

        # ── btrfs options ─────────────────────────────────────────────────
        self._btrfs_frame = QFrame()
        bf = QVBoxLayout(self._btrfs_frame)
        bf.setContentsMargins(0, 2, 0, 0)
        bf.setSpacing(4)
        bf.addWidget(self._lbl("── btrfs options ────────────────────────────────────────────────"))

        row_btrfs = QHBoxLayout()
        row_btrfs.setSpacing(6)
        row_btrfs.addWidget(self._lbl("compress:"))
        self._compress = QComboBox()
        self._compress.setObjectName("SourceEdit")
        self._compress.setFixedHeight(26)
        self._compress.setFixedWidth(76)
        self._compress.addItems(["zstd", "lzo", "zlib", "none"])
        self._compress.currentIndexChanged.connect(self._sync)
        row_btrfs.addWidget(self._compress)
        self._autodefrag = SwitchToggle("autodefrag")
        self._autodefrag.stateChanged.connect(self._sync)
        row_btrfs.addWidget(self._autodefrag)
        row_btrfs.addStretch()
        bf.addLayout(row_btrfs)
        outer.addWidget(self._btrfs_frame)

        # ── Result (always visible, manually editable) ────────────────────
        outer.addWidget(self._lbl("── result ───────────────────────────────────────────────────────"))
        self._result = QLineEdit()
        self._result.setObjectName("SourceEdit")
        self._result.setPlaceholderText("defaults")
        outer.addWidget(self._result)

        self._update_visibility()

    # ---- internal --------------------------------------------------------

    def _update_visibility(self):
        is_fat  = self._fstype in ("vfat", "fat32", "exfat")
        is_ntfs = self._fstype in ("ntfs", "ntfs-3g")
        self._ntfs_frame.setVisible(is_ntfs or is_fat)
        self._winnames.setVisible(is_ntfs)
        self._btrfs_frame.setVisible(self._fstype == "btrfs")

    def _sync(self):
        if self._updating:
            return
        parts = ["defaults"]
        for key, cb in self._cbs.items():
            if cb.isChecked():
                parts.append(key)

        if self._ntfs_frame.isVisible():
            if self._uid.text().strip():
                parts.append(f"uid={self._uid.text().strip()}")
            if self._gid.text().strip():
                parts.append(f"gid={self._gid.text().strip()}")
            if self._dmask.text().strip():
                parts.append(f"dmask={self._dmask.text().strip()}")
            if self._fmask.text().strip():
                parts.append(f"fmask={self._fmask.text().strip()}")
            if self._winnames.isVisible() and self._winnames.isChecked():
                parts.append("windows_names")

        if self._btrfs_frame.isVisible():
            c = self._compress.currentText()
            if c != "none":
                parts.append(f"compress={c}")
            if self._autodefrag.isChecked():
                parts.append("autodefrag")

        self._result.setText(",".join(parts))

    # ---- public API ------------------------------------------------------

    def set_fstype(self, fstype):
        self._fstype = fstype
        self._update_visibility()

    def set_lang(self, lang):
        def tip(key):
            d = self.OPTS_TIPS.get(key, {})
            return d.get(lang) or d.get("en", "")
        for key, cb in self._cbs.items():
            cb.setToolTip(tip(key))
        self._uid.setToolTip(tip("uid"))
        self._gid.setToolTip(tip("gid"))
        self._dmask.setToolTip(tip("dmask"))
        self._fmask.setToolTip(tip("fmask"))
        self._winnames.setToolTip(tip("winnames"))
        self._compress.setToolTip(tip("compress"))
        self._autodefrag.setToolTip(tip("autodefrag"))

    def set_options(self, opts_str):
        self._updating = True
        opts = {o.strip() for o in opts_str.split(",")}
        for key, cb in self._cbs.items():
            cb.setChecked(key in opts)
        for o in opts:
            if o.startswith("uid="):      self._uid.setText(o[4:])
            elif o.startswith("gid="):    self._gid.setText(o[4:])
            elif o.startswith("dmask="):  self._dmask.setText(o[6:])
            elif o.startswith("fmask="):  self._fmask.setText(o[6:])
            elif o.startswith("compress="):
                idx = self._compress.findText(o[9:])
                if idx >= 0:
                    self._compress.setCurrentIndex(idx)
        self._winnames.setChecked("windows_names" in opts)
        self._autodefrag.setChecked("autodefrag" in opts)
        self._result.setText(opts_str)
        self._updating = False

    def get_options(self):
        return self._result.text().strip() or "defaults"


def fs_display(fstype, fsver=""):
    """Человекочитаемое имя ФС. lsblk для любого FAT возвращает 'vfat' —
    конкретную версию (FAT32/FAT16/FAT12) даёт только колонка FSVER.
    Показываем её, чтобы пользователь видел точный формат, а не сокращение."""
    if fstype == "vfat":
        return fsver or "FAT"
    if fstype in ("fat32", "fat16", "fat12"):
        return fstype.upper()
    return {"ntfs": "NTFS", "ntfs-3g": "NTFS",
            "exfat": "exFAT", "btrfs": "Btrfs"}.get(fstype, fstype)


LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "zh_TW", "ja", "ko"]
STRINGS = {
    "title":        {"en": "Equestria OS Disk Manager",           "ru": "Equestria OS: Менеджер Дисков",      "de": "Equestria OS Festplatten-Manager",        "fr": "Equestria OS Gestionnaire de disques",    "es": "Equestria OS Gestor de discos",          "pt": "Equestria OS Gerenciador de discos",     "pl": "Equestria OS Menedżer dysków",           "uk": "Equestria OS Менеджер дисків",           "zh": "Equestria OS 磁盘管理器",                "ja": "Equestria OS ディスクマネージャー", "zh_TW": "Equestria OS 磁碟管理器", "ko": "Equestria OS 디스크 관리자"},
    "select_disk":  {"en": "Select Partition",                    "ru": "Выберите раздел",                    "de": "Partition auswählen",                    "fr": "Sélectionner une partition",             "es": "Seleccionar partición",                  "pt": "Selecionar partição",                    "pl": "Wybierz partycję",                       "uk": "Виберіть розділ",                        "zh": "选择分区",                               "ja": "パーティションを選択", "zh_TW": "選擇分割槽", "ko": "파티션 선택"},
    "mount_point":  {"en": "Mount Point",                         "ru": "Точка монтирования",                 "de": "Einhängepunkt",                          "fr": "Point de montage",                       "es": "Punto de montaje",                       "pt": "Ponto de montagem",                      "pl": "Punkt montowania",                       "uk": "Точка монтування",                       "zh": "挂载点",                                 "ja": "マウントポイント", "zh_TW": "掛載點", "ko": "마운트 지점"},
    "fstab_opts":   {"en": "fstab Options",                       "ru": "Опции fstab",                        "de": "fstab-Optionen",                         "fr": "Options fstab",                          "es": "Opciones fstab",                         "pt": "Opções fstab",                           "pl": "Opcje fstab",                            "uk": "Параметри fstab",                        "zh": "fstab 选项",                             "ja": "fstab オプション", "zh_TW": "fstab 選項", "ko": "fstab 옵션"},
    "select_user":  {"en": "Target User",                         "ru": "Владелец диска",                     "de": "Zielbenutzer",                           "fr": "Utilisateur cible",                      "es": "Usuario destino",                        "pt": "Usuário destino",                        "pl": "Użytkownik docelowy",                    "uk": "Цільовий користувач",                    "zh": "目标用户",                               "ja": "対象ユーザー", "zh_TW": "目標使用者", "ko": "대상 사용자"},
    "uuid":         {"en": "UUID",                                "ru": "UUID",                               "de": "UUID",                                   "fr": "UUID",                                   "es": "UUID",                                   "pt": "UUID",                                   "pl": "UUID",                                   "uk": "UUID",                                   "zh": "UUID",                                   "ja": "UUID", "zh_TW": "UUID", "ko": "UUID"},
    "fstype":       {"en": "File System",                         "ru": "Файловая система",                   "de": "Dateisystem",                            "fr": "Système de fichiers",                    "es": "Sistema de archivos",                    "pt": "Sistema de arquivos",                    "pl": "System plików",                          "uk": "Файлова система",                        "zh": "文件系统",                               "ja": "ファイルシステム", "zh_TW": "檔案系統", "ko": "파일 시스템"},
    "size":         {"en": "Size",                                "ru": "Размер",                             "de": "Größe",                                  "fr": "Taille",                                 "es": "Tamaño",                                 "pt": "Tamanho",                                "pl": "Rozmiar",                                "uk": "Розмір",                                 "zh": "大小",                                   "ja": "サイズ", "zh_TW": "大小", "ko": "크기"},
    "automount":    {"en": "Enable Automount",                    "ru": "Включить автомонтирование",          "de": "Automount aktivieren",                   "fr": "Activer le montage auto",                "es": "Activar automontaje",                    "pt": "Ativar montagem automática",             "pl": "Włącz automontowanie",                   "uk": "Увімкнути автомонтування",               "zh": "启用自动挂载",                           "ja": "自動マウントを有効化", "zh_TW": "啟用自動掛載", "ko": "자동 마운트 켜기"},
    "disable_auto": {"en": "Disable Automount",                   "ru": "Отключить автомонтирование",         "de": "Automount deaktivieren",                 "fr": "Désactiver le montage auto",             "es": "Desactivar automontaje",                 "pt": "Desativar montagem automática",          "pl": "Wyłącz automontowanie",                  "uk": "Вимкнути автомонтування",                "zh": "禁用自动挂载",                           "ja": "自動マウントを無効化", "zh_TW": "停用自動掛載", "ko": "자동 마운트 끄기"},
    "fix_perms":    {"en": "Take Ownership",                      "ru": "Установить владельца и права",       "de": "Eigentümerschaft übernehmen",            "fr": "Prendre possession",                     "es": "Tomar propiedad",                        "pt": "Assumir propriedade",                    "pl": "Przejmij własność",                      "uk": "Взяти у власність",                      "zh": "设置所有权",                             "ja": "所有権を取得", "zh_TW": "設定所有權", "ko": "소유권 가져오기"},
    "recursive":    {"en": "Recursive (includes files inside)",   "ru": "Рекурсивно (включая все файлы)",     "de": "Rekursiv (alle Dateien eingeschlossen)", "fr": "Récursif (tous les fichiers inclus)",    "es": "Recursivo (todos los archivos)",         "pt": "Recursivo (todos os arquivos)",          "pl": "Rekurencyjnie (wszystkie pliki)",        "uk": "Рекурсивно (всі файли)",                 "zh": "递归（包括所有文件）",                   "ja": "再帰的（全ファイル含む）", "zh_TW": "遞迴（包括所有檔案）", "ko": "재귀적 (안의 파일 포함)"},
    "ph_mount":     {"en": "e.g., /mnt/Work",                     "ru": "напр., /mnt/Work",                   "de": "z.B. /mnt/Work",                         "fr": "ex. /mnt/Work",                          "es": "p.ej. /mnt/Work",                        "pt": "ex. /mnt/Work",                          "pl": "np. /mnt/Work",                          "uk": "напр. /mnt/Work",                        "zh": "例如 /mnt/Work",                         "ja": "例: /mnt/Work", "zh_TW": "例如 /mnt/Work", "ko": "예: /mnt/Work"},
    "ph_opts":      {"en": "e.g., defaults,noatime",              "ru": "напр., defaults,noatime",            "de": "z.B. defaults,noatime",                  "fr": "ex. defaults,noatime",                   "es": "p.ej. defaults,noatime",                 "pt": "ex. defaults,noatime",                   "pl": "np. defaults,noatime",                   "uk": "напр. defaults,noatime",                 "zh": "例如 defaults,noatime",                 "ja": "例: defaults,noatime", "zh_TW": "例如 defaults,noatime", "ko": "예: defaults,noatime"},
    "ph_label":     {"en": "e.g., Work",                          "ru": "напр., Work",                        "de": "z.B. Work",                              "fr": "ex. Work",                               "es": "p.ej. Work",                             "pt": "ex. Work",                               "pl": "np. Work",                               "uk": "напр. Work",                             "zh": "例如 Work",                              "ja": "例: Work", "zh_TW": "例如 Work", "ko": "예: Work"},
    "refresh":      {"en": "Refresh disk list",                   "ru": "Обновить список дисков",             "de": "Festplattenliste aktualisieren",         "fr": "Actualiser la liste des disques",        "es": "Actualizar lista de discos",             "pt": "Atualizar lista de discos",              "pl": "Odśwież listę dysków",                   "uk": "Оновити список дисків",                  "zh": "刷新磁盘列表",                           "ja": "ディスク一覧を更新", "zh_TW": "重新整理磁碟列表", "ko": "디스크 목록 새로 고침"},
    "success":      {"en": "Operation successful!",               "ru": "Операция выполнена успешно!",        "de": "Vorgang erfolgreich!",                   "fr": "Opération réussie !",                    "es": "¡Operación exitosa!",                    "pt": "Operação bem-sucedida!",                 "pl": "Operacja zakończona pomyślnie!",         "uk": "Операцію виконано успішно!",             "zh": "操作成功！",                             "ja": "操作が完了しました！", "zh_TW": "操作成功！", "ko": "작업 성공!"},
    "err_elevate":  {"en": "Failed to get root access.",          "ru": "Не удалось получить права root.",    "de": "Root-Zugriff fehlgeschlagen.",           "fr": "Échec de l'accès root.",                 "es": "Error al obtener acceso root.",          "pt": "Falha ao obter acesso root.",            "pl": "Błąd uzyskania dostępu root.",           "uk": "Помилка отримання прав root.",           "zh": "获取 root 权限失败。",                   "ja": "root アクセスに失敗しました。", "zh_TW": "獲取 root 許可權失敗。", "ko": "root 권한을 얻지 못했습니다."},
    "applying":     {"en": "Applying changes...",                 "ru": "Применение изменений...",            "de": "Änderungen werden angewendet...",        "fr": "Application des modifications...",       "es": "Aplicando cambios...",                   "pt": "Aplicando alterações...",                "pl": "Stosowanie zmian...",                    "uk": "Застосування змін...",                   "zh": "正在应用更改...",                        "ja": "変更を適用中...", "zh_TW": "正在應用更改...", "ko": "변경 사항 적용 중..."},
    "mount_now":    {"en": "Mount Now",                           "ru": "Монтировать",                        "de": "Jetzt einbinden",                        "fr": "Monter maintenant",                      "es": "Montar ahora",                           "pt": "Montar agora",                           "pl": "Zamontuj teraz",                         "uk": "Монтувати зараз",                        "zh": "立即挂载",                               "ja": "今すぐマウント", "zh_TW": "立即掛載", "ko": "지금 마운트"},
    "umount":       {"en": "Unmount",                             "ru": "Размонтировать",                     "de": "Aushängen",                              "fr": "Démonter",                               "es": "Desmontar",                              "pt": "Desmontar",                              "pl": "Odmontuj",                               "uk": "Розмонтувати",                           "zh": "卸载",                                   "ja": "アンマウント", "zh_TW": "解除安裝", "ko": "마운트 해제"},
    "not_mounted":  {"en": "Not mounted",                         "ru": "Не смонтирован",                     "de": "Nicht eingebunden",                      "fr": "Non monté",                              "es": "No montado",                             "pt": "Não montado",                            "pl": "Nie zamontowany",                        "uk": "Не змонтований",                         "zh": "未挂载",                                 "ja": "未マウント", "zh_TW": "未掛載", "ko": "마운트되지 않음"},
    "mounted_at":   {"en": "Mounted at",                          "ru": "Смонтирован в",                      "de": "Eingebunden unter",                      "fr": "Monté sur",                              "es": "Montado en",                             "pt": "Montado em",                             "pl": "Zamontowany w",                          "uk": "Змонтований у",                          "zh": "挂载于",                                 "ja": "マウント先", "zh_TW": "掛載於", "ko": "마운트 위치"},
    "disk_used":    {"en": "Used",                                "ru": "Занято",                             "de": "Belegt",                                 "fr": "Utilisé",                                "es": "Usado",                                  "pt": "Usado",                                  "pl": "Zajęte",                                 "uk": "Зайнято",                                "zh": "已用",                                   "ja": "使用中", "zh_TW": "已用", "ko": "사용됨"},
    "disk_free":    {"en": "Free",                                "ru": "Свободно",                           "de": "Frei",                                   "fr": "Libre",                                  "es": "Libre",                                  "pt": "Livre",                                  "pl": "Wolne",                                  "uk": "Вільно",                                 "zh": "可用",                                   "ja": "空き", "zh_TW": "可用", "ko": "여유"},
    "lbl_section":  {"en": "Partition Label",                     "ru": "Метка раздела",                      "de": "Partitionsbezeichnung",                  "fr": "Étiquette de partition",                 "es": "Etiqueta de partición",                  "pt": "Rótulo da partição",                     "pl": "Etykieta partycji",                      "uk": "Мітка розділу",                          "zh": "分区标签",                               "ja": "パーティションラベル", "zh_TW": "分割槽標籤", "ko": "파티션 레이블"},
    "set_label":    {"en": "Set Label",                           "ru": "Установить метку",                   "de": "Bezeichnung setzen",                     "fr": "Définir l'étiquette",                    "es": "Establecer etiqueta",                    "pt": "Definir rótulo",                         "pl": "Ustaw etykietę",                         "uk": "Встановити мітку",                       "zh": "设置标签",                               "ja": "ラベルを設定", "zh_TW": "設定標籤", "ko": "레이블 설정"},
    "fmt_section":  {"en": "Format Partition",                    "ru": "Форматирование раздела",             "de": "Partition formatieren",                  "fr": "Formater la partition",                  "es": "Formatear partición",                    "pt": "Formatar partição",                      "pl": "Formatuj partycję",                      "uk": "Форматування розділу",                   "zh": "格式化分区",                             "ja": "パーティションをフォーマット", "zh_TW": "格式化分割槽", "ko": "파티션 포맷"},
    "fmt_warn":     {"en": "WARNING: All data will be ERASED!",   "ru": "ВНИМАНИЕ: Все данные будут УНИЧТОЖЕНЫ!", "de": "WARNUNG: Alle Daten werden GELÖSCHT!",   "fr": "ATTENTION : Toutes les données seront EFFACÉES !", "es": "¡ADVERTENCIA: Todos los datos serán BORRADOS!", "pt": "AVISO: Todos os dados serão APAGADOS!", "pl": "OSTRZEŻENIE: Wszystkie dane zostaną USUNIĘTE!", "uk": "УВАГА: Усі дані будуть ЗНИЩЕНІ!",        "zh": "警告：所有数据将被清除！",               "ja": "警告：すべてのデータが消去されます！", "zh_TW": "警告：所有資料將被清除！", "ko": "경고: 모든 데이터가 지워집니다!"},
    "new_fs":       {"en": "Filesystem",                          "ru": "Файловая система",                   "de": "Dateisystem",                            "fr": "Système de fichiers",                    "es": "Sistema de archivos",                    "pt": "Sistema de arquivos",                    "pl": "System plików",                          "uk": "Файлова система",                        "zh": "文件系统",                               "ja": "ファイルシステム", "zh_TW": "檔案系統", "ko": "파일 시스템"},
    "fmt_lbl_ph":   {"en": "Label after format (optional)",       "ru": "Метка после форматирования (опц.)", "de": "Bezeichnung nach Format (optional)",     "fr": "Étiquette après format (optionnel)",     "es": "Etiqueta tras formato (opcional)",       "pt": "Rótulo após formatação (opcional)",      "pl": "Etykieta po formatowaniu (opcja)",       "uk": "Мітка після форматування (опц.)",        "zh": "格式化后的标签（可选）",                 "ja": "フォーマット後のラベル（任意）", "zh_TW": "格式化後的標籤（可選）", "ko": "포맷 후 레이블 (선택 사항)"},
    "format_btn":   {"en": "Format Partition",                    "ru": "Форматировать раздел",               "de": "Partition formatieren",                  "fr": "Formater la partition",                  "es": "Formatear partición",                    "pt": "Formatar partição",                      "pl": "Formatuj partycję",                      "uk": "Форматувати розділ",                     "zh": "格式化分区",                             "ja": "パーティションをフォーマット", "zh_TW": "格式化分割槽", "ko": "파티션 포맷"},
    "fmt_mounted":  {"en": "Unmount partition before formatting", "ru": "Сначала размонтируйте раздел",       "de": "Zuerst aushängen vor dem Formatieren",  "fr": "Démontez d'abord avant de formater",     "es": "Desmonte antes de formatear",            "pt": "Desmonte antes de formatar",             "pl": "Najpierw odmontuj przed formatowaniem",  "uk": "Спочатку розмонтуйте розділ",            "zh": "格式化前请先卸载",                       "ja": "フォーマット前にアンマウントを", "zh_TW": "格式化前請先解除安裝", "ko": "포맷 전에 파티션 마운트 해제"},
    "confirm_fmt":  {
        "en": "FORMAT /dev/{dev}?\n\nAll data will be PERMANENTLY ERASED.\nThis cannot be undone!",
        "ru": "ФОРМАТИРОВАТЬ /dev/{dev}?\n\nВсе данные будут БЕЗВОЗВРАТНО УНИЧТОЖЕНЫ.\nОтменить невозможно!",
        "de": "Partition /dev/{dev} FORMATIEREN?\n\nAlle Daten werden UNWIDERRUFLICH GELÖSCHT.\nDieser Vorgang kann nicht rückgängig gemacht werden!",
        "fr": "FORMATER /dev/{dev} ?\n\nToutes les données seront DÉFINITIVEMENT EFFACÉES.\nCette action est irréversible !",
        "es": "¿FORMATEAR /dev/{dev}?\n\nTodos los datos serán BORRADOS PERMANENTEMENTE.\n¡Esta acción no se puede deshacer!",
        "pt": "FORMATAR /dev/{dev}?\n\nTodos os dados serão APAGADOS PERMANENTEMENTE.\nEsta ação não pode ser desfeita!",
        "pl": "FORMATOWAĆ /dev/{dev}?\n\nWszystkie dane zostaną TRWALE USUNIĘTE.\nTej operacji nie można cofnąć!",
        "uk": "ФОРМАТУВАТИ /dev/{dev}?\n\nУсі дані будуть БЕЗПОВОРОТНО ЗНИЩЕНІ.\nСкасувати неможливо!",
        "zh": "格式化 /dev/{dev}？\n\n所有数据将被永久清除。\n此操作无法撤消！",
        "ja": "/dev/{dev} をフォーマットしますか？\n\nすべてのデータが完全に消去されます。\nこの操作は元に戻せません！", "zh_TW": "格式化 /dev/{dev}？\n\n所有資料將被永久清除。\n此操作無法撤消！", "ko": "/dev/{dev}을(를) 포맷할까요?\n\n모든 데이터가 영구적으로 지워집니다.\n되돌릴 수 없습니다!",
    },
    # Tooltips (EN + RU; other langs fall back to EN via t())
    "tt_disk":      {"en": "Select the physical drive or partition to configure",    "ru": "Выберите физический диск или раздел для настройки", "de": "Physisches Laufwerk oder Partition zum Einrichten auswählen", "fr": "Choisir le disque physique ou la partition à configurer", "es": "Seleccione la unidad física o partición que desea configurar", "pt": "Selecione a unidade física ou partição a configurar", "pl": "Wybierz fizyczny dysk lub partycję do skonfigurowania", "uk": "Виберіть фізичний диск або розділ для налаштування", "zh": "选择要配置的物理驱动器或分区", "zh_TW": "選擇要配置的物理驅動器或分割槽", "ja": "設定する物理ドライブまたはパーティションを選択", "ko": "설정할 물리 드라이브나 파티션을 선택하세요"},
    "tt_mount":     {"en": "Absolute path where the drive will be mounted",          "ru": "Абсолютный путь, куда будет примонтирован диск", "de": "Absoluter Pfad, unter dem das Laufwerk eingehängt wird", "fr": "Chemin absolu où le disque sera monté", "es": "Ruta absoluta donde se montará la unidad", "pt": "Caminho absoluto onde a unidade será montada", "pl": "Bezwzględna ścieżka, pod którą zostanie zamontowany dysk", "uk": "Абсолютний шлях, куди буде змонтовано диск", "zh": "驱动器的挂载绝对路径", "zh_TW": "驅動器的掛載絕對路徑", "ja": "ドライブをマウントする絶対パス", "ko": "드라이브를 마운트할 절대 경로"},
    "tt_opts":      {"en": "Mount options for /etc/fstab. You can edit these manually.", "ru": "Параметры монтирования для /etc/fstab. Можно редактировать вручную.", "de": "Einhängeoptionen für /etc/fstab. Sie können sie manuell bearbeiten.", "fr": "Options de montage pour /etc/fstab. Vous pouvez les modifier à la main.", "es": "Opciones de montaje para /etc/fstab. Puede editarlas a mano.", "pt": "Opções de montagem para /etc/fstab. Você pode editá-las manualmente.", "pl": "Opcje montowania dla /etc/fstab. Możesz je edytować ręcznie.", "uk": "Параметри монтування для /etc/fstab. Їх можна редагувати вручну.", "zh": "/etc/fstab 的挂载选项。可以手动编辑。", "zh_TW": "/etc/fstab 的掛載選項。可以手動編輯。", "ja": "/etc/fstab 用のマウントオプション。手動で編集できます。", "ko": "/etc/fstab용 마운트 옵션. 직접 편집할 수 있습니다."},
    "tt_auto":      {"en": "Write this drive to /etc/fstab so it mounts on boot",   "ru": "Прописать диск в /etc/fstab для монтирования при загрузке", "de": "Dieses Laufwerk in /etc/fstab eintragen, damit es beim Start eingehängt wird", "fr": "Inscrire ce disque dans /etc/fstab pour qu'il soit monté au démarrage", "es": "Escribir esta unidad en /etc/fstab para que se monte al arrancar", "pt": "Gravar esta unidade no /etc/fstab para que seja montada na inicialização", "pl": "Zapisz ten dysk w /etc/fstab, aby montował się przy uruchamianiu", "uk": "Записати цей диск у /etc/fstab, щоб він монтувався під час завантаження", "zh": "将此驱动器写入 /etc/fstab，使其在启动时挂载", "zh_TW": "將此驅動器寫入 /etc/fstab，使其在啟動時掛載", "ja": "起動時にマウントされるよう、このドライブを /etc/fstab に書き込む", "ko": "부팅 시 마운트되도록 이 드라이브를 /etc/fstab에 기록"},
    "tt_user":      {"en": "Select the system user who will own this drive",         "ru": "Выберите пользователя системы, который станет владельцем диска", "de": "Systembenutzer auswählen, dem dieses Laufwerk gehören soll", "fr": "Choisir l'utilisateur système propriétaire de ce disque", "es": "Seleccione el usuario del sistema que será propietario de esta unidad", "pt": "Selecione o usuário do sistema que será dono desta unidade", "pl": "Wybierz użytkownika systemu, który będzie właścicielem dysku", "uk": "Виберіть користувача системи, якому належатиме цей диск", "zh": "选择拥有此驱动器的系统用户", "zh_TW": "選擇擁有此驅動器的系統使用者", "ja": "このドライブを所有するシステムユーザーを選択", "ko": "이 드라이브를 소유할 시스템 사용자를 선택하세요"},
    "tt_perms":     {"en": "Change directory owner and grant read/write access",     "ru": "Сменить владельца директории и выдать полные права", "de": "Eigentümer des Verzeichnisses ändern und Lese-/Schreibzugriff gewähren", "fr": "Changer le propriétaire du dossier et accorder l'accès en lecture/écriture", "es": "Cambiar el propietario de la carpeta y conceder acceso de lectura/escritura", "pt": "Alterar o dono da pasta e conceder acesso de leitura/escrita", "pl": "Zmień właściciela katalogu i nadaj prawa odczytu/zapisu", "uk": "Змінити власника теки та надати доступ на читання/запис", "zh": "更改目录所有者并授予读写权限", "zh_TW": "更改目錄所有者並授予讀寫許可權", "ja": "ディレクトリの所有者を変更し、読み書きアクセスを付与", "ko": "디렉터리 소유자를 변경하고 읽기/쓰기 권한 부여"},
    "tt_rec":       {"en": "Apply permissions to all nested folders and files (may take time)", "ru": "Применить права ко всем вложенным папкам и файлам (может занять время)", "de": "Berechtigungen auf alle Unterordner und Dateien anwenden (kann dauern)", "fr": "Appliquer les permissions à tous les sous-dossiers et fichiers (peut prendre du temps)", "es": "Aplicar permisos a todas las subcarpetas y archivos (puede tardar)", "pt": "Aplicar permissões a todas as subpastas e arquivos (pode demorar)", "pl": "Zastosuj uprawnienia do wszystkich podfolderów i plików (może potrwać)", "uk": "Застосувати права до всіх вкладених тек і файлів (може тривати довго)", "zh": "将权限应用到所有子文件夹和文件（可能需要一些时间）", "zh_TW": "將許可權應用到所有子資料夾和檔案（可能需要一些時間）", "ja": "すべてのサブフォルダーとファイルに権限を適用（時間がかかる場合があります）", "ko": "모든 하위 폴더와 파일에 권한 적용 (시간이 걸릴 수 있음)"},
    "tt_mount_now": {"en": "Mount the partition to the path specified above",        "ru": "Монтировать раздел по указанному пути", "de": "Partition unter dem oben angegebenen Pfad einhängen", "fr": "Monter la partition au chemin indiqué ci-dessus", "es": "Montar la partición en la ruta indicada arriba", "pt": "Montar a partição no caminho indicado acima", "pl": "Zamontuj partycję w ścieżce podanej powyżej", "uk": "Змонтувати розділ за шляхом, указаним вище", "zh": "将分区挂载到上面指定的路径", "zh_TW": "將分割槽掛載到上面指定的路徑", "ja": "上で指定したパスにパーティションをマウント", "ko": "위에 지정한 경로에 파티션 마운트"},
    "tt_umount":    {"en": "Unmount the currently mounted partition",                "ru": "Размонтировать смонтированный раздел", "de": "Aktuell eingehängte Partition aushängen", "fr": "Démonter la partition actuellement montée", "es": "Desmontar la partición montada actualmente", "pt": "Desmontar a partição montada atualmente", "pl": "Odmontuj aktualnie zamontowaną partycję", "uk": "Відмонтувати змонтований розділ", "zh": "卸载当前已挂载的分区", "zh_TW": "解除安裝當前已掛載的分割槽", "ja": "現在マウントされているパーティションをアンマウント", "ko": "현재 마운트된 파티션 마운트 해제"},
    "tt_set_label": {"en": "Change the partition label",                             "ru": "Изменить метку раздела", "de": "Partitionsbezeichnung ändern", "fr": "Changer l'étiquette de la partition", "es": "Cambiar la etiqueta de la partición", "pt": "Alterar o rótulo da partição", "pl": "Zmień etykietę partycji", "uk": "Змінити мітку розділу", "zh": "更改分区标签", "zh_TW": "更改分割槽標籤", "ja": "パーティションのラベルを変更", "ko": "파티션 레이블 변경"},
    "tt_format":    {"en": "Format with a new filesystem — ERASES ALL DATA",        "ru": "Форматировать с новой ФС — УНИЧТОЖАЕТ ВСЕ ДАННЫЕ", "de": "Mit neuem Dateisystem formatieren — LÖSCHT ALLE DATEN", "fr": "Formater avec un nouveau système de fichiers — EFFACE TOUTES LES DONNÉES", "es": "Formatear con un nuevo sistema de archivos — BORRA TODOS LOS DATOS", "pt": "Formatar com um novo sistema de arquivos — APAGA TODOS OS DADOS", "pl": "Sformatuj nowym systemem plików — USUWA WSZYSTKIE DANE", "uk": "Відформатувати новою файловою системою — СТИРАЄ ВСІ ДАНІ", "zh": "用新文件系统格式化——删除所有数据", "zh_TW": "用新檔案系統格式化——刪除所有資料", "ja": "新しいファイルシステムでフォーマット — すべてのデータを消去", "ko": "새 파일 시스템으로 포맷 — 모든 데이터 삭제"},
    "no_label":     {"en": "No Label",                                             "ru": "Без метки",                          "de": "Kein Name",                              "fr": "Sans nom",                               "es": "Sin nombre",                             "pt": "Sem nome",                               "pl": "Bez nazwy",                              "uk": "Без мітки",                              "zh": "无标签",                                 "ja": "ラベルなし", "zh_TW": "無標籤", "ko": "레이블 없음"},
    "fstab_issues":      {"en": "⚠  fstab Issues",
                          "ru": "⚠  Проблемы fstab", "de": "⚠  fstab-Probleme", "fr": "⚠  Problèmes fstab", "es": "⚠  Problemas de fstab", "pt": "⚠  Problemas no fstab", "pl": "⚠  Problemy z fstab", "uk": "⚠  Проблеми з fstab", "zh": "⚠  fstab 问题", "zh_TW": "⚠  fstab 問題", "ja": "⚠  fstab の問題", "ko": "⚠  fstab 문제"},
    "fstab_orphan_hint": {"en": "These /etc/fstab entries have no matching connected disk.\n"
                                "Without 'nofail' they may block system boot.",
                          "ru": "Эти записи /etc/fstab не имеют соответствующего подключённого диска.\n"
                                "Без 'nofail' они могут блокировать загрузку системы.", "de": "Zu diesen /etc/fstab-Einträgen gibt es keine verbundene Festplatte.\nOhne 'nofail' können sie den Systemstart blockieren.", "fr": "Ces entrées de /etc/fstab n'ont aucun disque connecté correspondant.\nSans 'nofail', elles peuvent bloquer le démarrage du système.", "es": "Estas entradas de /etc/fstab no tienen ningún disco conectado correspondiente.\nSin 'nofail' pueden bloquear el arranque del sistema.", "pt": "Estas entradas do /etc/fstab não têm disco conectado correspondente.\nSem 'nofail' elas podem bloquear a inicialização do sistema.", "pl": "Te wpisy /etc/fstab nie mają pasującego podłączonego dysku.\nBez 'nofail' mogą zablokować uruchamianie systemu.", "uk": "Для цих записів /etc/fstab немає відповідного під'єднаного диска.\nБез 'nofail' вони можуть заблокувати завантаження системи.", "zh": "这些 /etc/fstab 条目没有匹配的已连接磁盘。\n没有 'nofail' 时可能阻止系统启动。", "zh_TW": "這些 /etc/fstab 條目沒有匹配的已連線磁碟。\n沒有 'nofail' 時可能阻止系統啟動。", "ja": "これらの /etc/fstab エントリに一致する接続済みディスクがありません。\n'nofail' がないとシステムの起動を妨げる可能性があります。", "ko": "이 /etc/fstab 항목들과 일치하는 연결된 디스크가 없습니다.\n'nofail'이 없으면 시스템 부팅을 막을 수 있습니다."},
    "fstab_orphan_warn": {"en": "Disk not connected — may block boot",
                          "ru": "Диск не подключён — может блокировать загрузку", "de": "Laufwerk nicht verbunden — kann den Start blockieren", "fr": "Disque non connecté — peut bloquer le démarrage", "es": "Disco no conectado — puede bloquear el arranque", "pt": "Disco não conectado — pode bloquear a inicialização", "pl": "Dysk niepodłączony — może zablokować uruchamianie", "uk": "Диск не під'єднано — може заблокувати завантаження", "zh": "磁盘未连接——可能阻止启动", "zh_TW": "磁碟未連線——可能阻止啟動", "ja": "ディスクが接続されていません — 起動を妨げる可能性があります", "ko": "디스크가 연결되지 않음 — 부팅을 막을 수 있음"},
    "fstab_orphan_rm":   {"en": "Remove from fstab",
                          "ru": "Удалить из fstab", "de": "Aus fstab entfernen", "fr": "Retirer de fstab", "es": "Quitar de fstab", "pt": "Remover do fstab", "pl": "Usuń z fstab", "uk": "Видалити з fstab", "zh": "从 fstab 中删除", "zh_TW": "從 fstab 中刪除", "ja": "fstab から削除", "ko": "fstab에서 제거"},
    "fstab_add_nofail":  {"en": "Add nofail",
                          "ru": "Добавить nofail", "de": "nofail hinzufügen", "fr": "Ajouter nofail", "es": "Añadir nofail", "pt": "Adicionar nofail", "pl": "Dodaj nofail", "uk": "Додати nofail", "zh": "添加 nofail", "zh_TW": "新增 nofail", "ja": "nofail を追加", "ko": "nofail 추가"},
    "fmt_rm_fstab_note": {"en": "(The existing fstab entry for this partition will be removed automatically)",
                          "ru": "(Существующая запись fstab для этого раздела будет удалена автоматически)", "de": "(Der vorhandene fstab-Eintrag dieser Partition wird automatisch entfernt)", "fr": "(L'entrée fstab existante de cette partition sera supprimée automatiquement)", "es": "(La entrada de fstab existente de esta partición se eliminará automáticamente)", "pt": "(A entrada fstab existente desta partição será removida automaticamente)", "pl": "(Istniejący wpis fstab tej partycji zostanie usunięty automatycznie)", "uk": "(Наявний запис fstab для цього розділу буде видалено автоматично)", "zh": "（此分区现有的 fstab 条目将被自动删除）", "zh_TW": "（此分割槽現有的 fstab 條目將被自動刪除）", "ja": "（このパーティションの既存の fstab エントリは自動的に削除されます）", "ko": "(이 파티션의 기존 fstab 항목은 자동으로 제거됩니다)"},
    "dlg_warning":      {"en": "Warning",                                     "ru": "Предупреждение",                     "de": "Warnung",                                "fr": "Avertissement",                          "es": "Advertencia",                            "pt": "Aviso",                                  "pl": "Ostrzeżenie",                            "uk": "Попередження",                           "zh": "警告",                                   "ja": "警告", "zh_TW": "警告", "ko": "경고"},
    "dlg_error":        {"en": "Error",                                        "ru": "Ошибка",                             "de": "Fehler",                                 "fr": "Erreur",                                 "es": "Error",                                  "pt": "Erro",                                   "pl": "Błąd",                                   "uk": "Помилка",                                "zh": "错误",                                   "ja": "エラー", "zh_TW": "錯誤", "ko": "오류"},
    "dlg_success":      {"en": "Success",                                      "ru": "Успешно",                            "de": "Erfolg",                                 "fr": "Succès",                                 "es": "Éxito",                                  "pt": "Sucesso",                                "pl": "Sukces",                                 "uk": "Успіх",                                  "zh": "成功",                                   "ja": "成功", "zh_TW": "成功", "ko": "성공"},
    "dlg_confirm_fmt":  {"en": "Confirm Format",                               "ru": "Подтвердите форматирование",         "de": "Format bestätigen",                      "fr": "Confirmer le formatage",                 "es": "Confirmar formato",                      "pt": "Confirmar formatação",                   "pl": "Potwierdź formatowanie",                 "uk": "Підтвердіть форматування",               "zh": "确认格式化",                             "ja": "フォーマットの確認", "zh_TW": "確認格式化", "ko": "포맷 확인"},
    "warn_empty_mount": {"en": "Mount point and options cannot be empty!",     "ru": "Точка монтирования и опции не могут быть пустыми!", "de": "Einhängepunkt und Optionen dürfen nicht leer sein!", "fr": "Le point de montage et les options ne peuvent pas être vides !", "es": "¡El punto de montaje y las opciones no pueden estar vacíos!", "pt": "O ponto de montagem e as opções não podem estar vazios!", "pl": "Punkt montowania i opcje nie mogą być puste!", "uk": "Точка монтування та параметри не можуть бути порожніми!", "zh": "挂载点和选项不能为空！", "ja": "マウントポイントとオプションを入力してください！", "zh_TW": "掛載點和選項不能為空！", "ko": "마운트 지점과 옵션은 비워 둘 수 없습니다!"},
    "warn_no_mount":    {"en": "Specify mount point first!",                   "ru": "Сначала укажите точку монтирования!", "de": "Bitte zuerst Einhängepunkt angeben!",    "fr": "Veuillez d'abord spécifier un point de montage !", "es": "¡Primero especifique el punto de montaje!", "pt": "Especifique o ponto de montagem primeiro!", "pl": "Najpierw podaj punkt montowania!",       "uk": "Спочатку вкажіть точку монтування!",     "zh": "请先指定挂载点！",                       "ja": "最初にマウントポイントを指定してください！", "zh_TW": "請先指定掛載點！", "ko": "먼저 마운트 지점을 지정하세요!"},
    "warn_no_label":    {"en": "Enter a label!",                               "ru": "Введите метку!",                     "de": "Bezeichnung eingeben!",                  "fr": "Entrez une étiquette !",                 "es": "¡Introduzca una etiqueta!",              "pt": "Digite um rótulo!",                      "pl": "Podaj etykietę!",                        "uk": "Введіть мітку!",                         "zh": "请输入标签！",                           "ja": "ラベルを入力してください！", "zh_TW": "請輸入標籤！", "ko": "레이블을 입력하세요!"},
    "save_fstab":   {"en": "Save fstab",                                  "ru": "Сохранить fstab",                    "de": "fstab speichern",                        "fr": "Enregistrer fstab",                      "es": "Guardar fstab",                          "pt": "Salvar fstab",                           "pl": "Zapisz fstab",                           "uk": "Зберегти fstab",                         "zh": "保存 fstab",                             "ja": "fstab を保存", "zh_TW": "儲存 fstab", "ko": "fstab 저장"},
    "tt_save_fstab":{"en": "Update mount point and options in /etc/fstab", "ru": "Обновить точку монтирования и опции в /etc/fstab", "de": "Einhängepunkt und Optionen in /etc/fstab aktualisieren", "fr": "Mettre à jour le point de montage et les options dans /etc/fstab", "es": "Actualizar el punto de montaje y las opciones en /etc/fstab", "pt": "Atualizar o ponto de montagem e as opções no /etc/fstab", "pl": "Zaktualizuj punkt montowania i opcje w /etc/fstab", "uk": "Оновити точку монтування та параметри в /etc/fstab", "zh": "更新 /etc/fstab 中的挂载点和选项", "zh_TW": "更新 /etc/fstab 中的掛載點和選項", "ja": "/etc/fstab のマウントポイントとオプションを更新", "ko": "/etc/fstab의 마운트 지점과 옵션 업데이트"},
    "open_fstab":   {"en": "Open fstab",                                  "ru": "Открыть fstab",                      "de": "fstab öffnen",                           "fr": "Ouvrir fstab",                           "es": "Abrir fstab",                            "pt": "Abrir fstab",                            "pl": "Otwórz fstab",                           "uk": "Відкрити fstab",                         "zh": "打开 fstab",                             "ja": "fstab を開く", "zh_TW": "開啟 fstab", "ko": "fstab 열기"},
    "tt_open_fstab":{"en": "Open /etc/fstab in a text editor to inspect or hand-edit it directly", "ru": "Открыть /etc/fstab в текстовом редакторе для просмотра или ручного редактирования", "de": "/etc/fstab in einem Texteditor zur Ansicht oder manuellen Bearbeitung öffnen", "fr": "Ouvrir /etc/fstab dans un éditeur de texte pour l'inspecter ou le modifier manuellement", "es": "Abrir /etc/fstab en un editor de texto para inspeccionarlo o editarlo manualmente", "pt": "Abrir /etc/fstab em um editor de texto para inspecionar ou editar manualmente", "pl": "Otwórz /etc/fstab w edytorze tekstu, aby go sprawdzić lub edytować ręcznie", "uk": "Відкрити /etc/fstab у текстовому редакторі для перегляду або ручного редагування", "zh": "在文本编辑器中打开 /etc/fstab 以查看或手动编辑", "ja": "テキストエディタで /etc/fstab を開いて確認・手動編集する", "zh_TW": "在文本編輯器中開啟 /etc/fstab 以檢視或手動編輯", "ko": "텍스트 편집기에서 /etc/fstab을 열어 확인하거나 직접 편집"},
    "no_editor_found": {"en": "No text editor or terminal emulator found to open fstab", "ru": "Не найден текстовый редактор или терминал для открытия fstab", "de": "Kein Texteditor oder Terminal-Emulator zum Öffnen von fstab gefunden", "fr": "Aucun éditeur de texte ou émulateur de terminal trouvé pour ouvrir fstab", "es": "No se encontró ningún editor de texto ni emulador de terminal para abrir fstab", "pt": "Nenhum editor de texto ou emulador de terminal encontrado para abrir o fstab", "pl": "Nie znaleziono edytora tekstu ani emulatora terminala do otwarcia fstab", "uk": "Не знайдено текстовий редактор або емулятор термінала для відкриття fstab", "zh": "未找到可用于打开 fstab 的文本编辑器或终端模拟器", "ja": "fstab を開くためのテキストエディタやターミナルエミュレータが見つかりません", "zh_TW": "未找到可用於開啟 fstab 的文本編輯器或終端模擬器", "ko": "fstab을 열 텍스트 편집기나 터미널 에뮬레이터를 찾을 수 없음"},
    "cancel":       {"en": "Cancel",                                       "ru": "Отмена",                             "de": "Abbrechen",                              "fr": "Annuler",                                "es": "Cancelar",                               "pt": "Cancelar",                               "pl": "Anuluj",                                 "uk": "Скасувати",                              "zh": "取消",                                   "ja": "キャンセル", "zh_TW": "取消", "ko": "취소"},
    "confirm_type_hint": {
        "en": "Type the partition name ({dev}) to confirm:",
        "ru": "Введите имя раздела ({dev}) для подтверждения:",
        "de": "Gib zur Bestätigung den Partitionsnamen ({dev}) ein:",
        "fr": "Saisissez le nom de la partition ({dev}) pour confirmer :",
        "es": "Escribe el nombre de la partición ({dev}) para confirmar:",
        "pt": "Digite o nome da partição ({dev}) para confirmar:",
        "pl": "Wpisz nazwę partycji ({dev}), aby potwierdzić:",
        "uk": "Введіть назву розділу ({dev}) для підтвердження:",
        "zh": "输入分区名称（{dev}）以确认：",
        "ja": "確認のためパーティション名（{dev}）を入力してください：", "zh_TW": "輸入分割槽名稱（{dev}）以確認：", "ko": "확인하려면 파티션 이름({dev})을 입력하세요:",
    },
    "keep_uuid": {
        "en": "Keep UUID (fstab entry stays valid)",
        "ru": "Сохранить UUID (запись в fstab останется рабочей)",
        "de": "UUID behalten (fstab-Eintrag bleibt gültig)",
        "fr": "Conserver l'UUID (l'entrée fstab reste valide)",
        "es": "Mantener UUID (la entrada fstab sigue válida)",
        "pt": "Manter UUID (a entrada fstab continua válida)",
        "pl": "Zachowaj UUID (wpis fstab pozostanie ważny)",
        "uk": "Зберегти UUID (запис у fstab лишиться робочим)",
        "zh": "保留 UUID（fstab 条目保持有效）",
        "ja": "UUID を保持（fstab エントリは有効なまま）", "zh_TW": "保留 UUID（fstab 條目保持有效）", "ko": "UUID 유지 (fstab 항목이 계속 유효)",
    },
    "warn_label_len": {
        "en": "Label is too long for {fs} — maximum {max} characters",
        "ru": "Метка слишком длинная для {fs} — максимум {max} символов",
        "de": "Bezeichnung zu lang für {fs} — maximal {max} Zeichen",
        "fr": "Étiquette trop longue pour {fs} — {max} caractères maximum",
        "es": "Etiqueta demasiado larga para {fs} — máximo {max} caracteres",
        "pt": "Rótulo muito longo para {fs} — máximo de {max} caracteres",
        "pl": "Etykieta za długa dla {fs} — maksymalnie {max} znaków",
        "uk": "Мітка задовга для {fs} — максимум {max} символів",
        "zh": "标签对 {fs} 来说太长——最多 {max} 个字符",
        "ja": "{fs} のラベルが長すぎます — 最大 {max} 文字", "zh_TW": "標籤對 {fs} 來說太長——最多 {max} 個字元", "ko": "{fs}에는 레이블이 너무 깁니다 — 최대 {max}자",
    },
    "warn_fat16_size": {
        "en": "FAT16 supports volumes up to 4 GiB only — use FAT32 or exFAT",
        "ru": "FAT16 поддерживает тома только до 4 ГиБ — используй FAT32 или exFAT",
        "de": "FAT16 unterstützt nur Volumes bis 4 GiB — nutze FAT32 oder exFAT",
        "fr": "FAT16 ne gère que les volumes jusqu'à 4 Gio — utilisez FAT32 ou exFAT",
        "es": "FAT16 solo admite volúmenes de hasta 4 GiB — usa FAT32 o exFAT",
        "pt": "FAT16 só suporta volumes de até 4 GiB — use FAT32 ou exFAT",
        "pl": "FAT16 obsługuje woluminy tylko do 4 GiB — użyj FAT32 lub exFAT",
        "uk": "FAT16 підтримує томи лише до 4 ГіБ — використовуй FAT32 або exFAT",
        "zh": "FAT16 仅支持最大 4 GiB 的卷——请使用 FAT32 或 exFAT",
        "ja": "FAT16 は最大 4 GiB のボリュームのみ対応 — FAT32 か exFAT を使ってください", "zh_TW": "FAT16 僅支援最大 4 GiB 的卷——請使用 FAT32 或 exFAT", "ko": "FAT16은 4GiB까지의 볼륨만 지원합니다 — FAT32나 exFAT를 사용하세요",
    },
    "warn_label_chars": {
        "en": "FAT/exFAT label: only letters, digits, space, '_', '.', '-'",
        "ru": "Метка FAT/exFAT: только буквы, цифры, пробел, '_', '.', '-'",
        "de": "FAT/exFAT-Bezeichnung: nur Buchstaben, Ziffern, Leerzeichen, '_', '.', '-'",
        "fr": "Étiquette FAT/exFAT : uniquement lettres, chiffres, espace, '_', '.', '-'",
        "es": "Etiqueta FAT/exFAT: solo letras, dígitos, espacio, '_', '.', '-'",
        "pt": "Rótulo FAT/exFAT: apenas letras, dígitos, espaço, '_', '.', '-'",
        "pl": "Etykieta FAT/exFAT: tylko litery, cyfry, spacja, '_', '.', '-'",
        "uk": "Мітка FAT/exFAT: лише літери, цифри, пробіл, '_', '.', '-'",
        "zh": "FAT/exFAT 标签：仅限字母、数字、空格、'_'、'.'、'-'",
        "ja": "FAT/exFAT ラベル：英数字・空白・'_'・'.'・'-' のみ", "zh_TW": "FAT/exFAT 標籤：僅限字母、數字、空格、'_'、'.'、'-'", "ko": "FAT/exFAT 레이블: 문자, 숫자, 공백, '_', '.', '-'만 사용",
    },
    # Подсказки и описания ФС — en+ru, остальные языки падают на en через t()
    "fmt_keep_fstab_note": {"en": "(UUID will be kept — the existing fstab entry stays valid)",
                            "ru": "(UUID будет сохранён — существующая запись fstab останется рабочей)", "de": "(Die UUID bleibt erhalten — der vorhandene fstab-Eintrag bleibt gültig)", "fr": "(L'UUID sera conservé — l'entrée fstab existante reste valide)", "es": "(Se conservará el UUID — la entrada de fstab existente sigue siendo válida)", "pt": "(O UUID será mantido — a entrada fstab existente continua válida)", "pl": "(UUID zostanie zachowany — istniejący wpis fstab pozostaje ważny)", "uk": "(UUID буде збережено — наявний запис fstab залишається дійсним)", "zh": "（UUID 将保留——现有的 fstab 条目仍然有效）", "zh_TW": "（UUID 將保留——現有的 fstab 條目仍然有效）", "ja": "（UUID は保持されます — 既存の fstab エントリはそのまま有効です）", "ko": "(UUID가 유지됩니다 — 기존 fstab 항목은 그대로 유효합니다)"},
    "tt_keep_uuid": {"en": "Create the new filesystem with the same UUID so /etc/fstab and other references keep working. Available when the new filesystem is the same family as the current one.",
                     "ru": "Создать новую ФС с прежним UUID — /etc/fstab и другие ссылки продолжат работать. Доступно, когда новая ФС той же семьи, что и текущая.", "de": "Das neue Dateisystem mit derselben UUID erstellen, damit /etc/fstab und andere Verweise weiter funktionieren. Verfügbar, wenn das neue Dateisystem zur selben Familie wie das aktuelle gehört.", "fr": "Créer le nouveau système de fichiers avec le même UUID pour que /etc/fstab et les autres références continuent de fonctionner. Disponible quand le nouveau système de fichiers est de la même famille que l'actuel.", "es": "Crear el nuevo sistema de archivos con el mismo UUID para que /etc/fstab y otras referencias sigan funcionando. Disponible cuando el nuevo sistema de archivos es de la misma familia que el actual.", "pt": "Criar o novo sistema de arquivos com o mesmo UUID para que /etc/fstab e outras referências continuem funcionando. Disponível quando o novo sistema de arquivos é da mesma família do atual.", "pl": "Utwórz nowy system plików z tym samym UUID, aby /etc/fstab i inne odwołania nadal działały. Dostępne, gdy nowy system plików należy do tej samej rodziny co obecny.", "uk": "Створити нову файлову систему з тим самим UUID, щоб /etc/fstab та інші посилання працювали далі. Доступно, коли нова файлова система тієї ж родини, що й поточна.", "zh": "用相同的 UUID 创建新文件系统，使 /etc/fstab 和其他引用继续有效。新文件系统与当前文件系统属于同一类型时可用。", "zh_TW": "用相同的 UUID 建立新檔案系統，使 /etc/fstab 和其他引用繼續有效。新檔案系統與當前檔案系統屬於同一型別時可用。", "ja": "新しいファイルシステムを同じ UUID で作成し、/etc/fstab などの参照が引き続き機能するようにします。新しいファイルシステムが現在と同じ系統の場合に利用できます。", "ko": "새 파일 시스템을 같은 UUID로 만들어 /etc/fstab 등의 참조가 계속 작동하게 합니다. 새 파일 시스템이 현재와 같은 계열일 때 사용할 수 있습니다."},
    "fs_desc_ext4":  {"en": "Linux standard — fast and reliable; best choice for internal drives",
                      "ru": "Стандарт Linux — быстрая и надёжная; лучший выбор для внутренних дисков", "de": "Linux-Standard — schnell und zuverlässig; beste Wahl für interne Laufwerke", "fr": "Standard Linux — rapide et fiable ; le meilleur choix pour les disques internes", "es": "Estándar de Linux — rápido y fiable; la mejor opción para unidades internas", "pt": "Padrão do Linux — rápido e confiável; a melhor escolha para unidades internas", "pl": "Standard Linuksa — szybki i niezawodny; najlepszy wybór dla dysków wewnętrznych", "uk": "Стандарт Linux — швидка й надійна; найкращий вибір для внутрішніх дисків", "zh": "Linux 标准——快速可靠；内置驱动器的最佳选择", "zh_TW": "Linux 標準——快速可靠；內建驅動器的最佳選擇", "ja": "Linux の標準 — 高速で信頼性が高い。内蔵ドライブに最適", "ko": "Linux 표준 — 빠르고 안정적. 내장 드라이브에 가장 좋은 선택"},
    "fs_desc_btrfs": {"en": "Modern Linux FS with snapshots and transparent compression",
                      "ru": "Современная ФС Linux со снапшотами и прозрачным сжатием", "de": "Modernes Linux-Dateisystem mit Snapshots und transparenter Komprimierung", "fr": "Système de fichiers Linux moderne avec instantanés et compression transparente", "es": "Sistema de archivos Linux moderno con instantáneas y compresión transparente", "pt": "Sistema de arquivos Linux moderno com snapshots e compressão transparente", "pl": "Nowoczesny system plików Linuksa z migawkami i przezroczystą kompresją", "uk": "Сучасна файлова система Linux зі знімками та прозорим стисненням", "zh": "支持快照和透明压缩的现代 Linux 文件系统", "zh_TW": "支援快照和透明壓縮的現代 Linux 檔案系統", "ja": "スナップショットと透過圧縮を備えた最新の Linux ファイルシステム", "ko": "스냅샷과 투명 압축을 지원하는 현대적인 Linux 파일 시스템"},
    "fs_desc_ntfs":  {"en": "Windows filesystem; use for drives shared with Windows",
                      "ru": "ФС Windows; для дисков, общих с Windows", "de": "Windows-Dateisystem; für Laufwerke, die mit Windows geteilt werden", "fr": "Système de fichiers Windows ; pour les disques partagés avec Windows", "es": "Sistema de archivos de Windows; para unidades compartidas con Windows", "pt": "Sistema de arquivos do Windows; para unidades compartilhadas com o Windows", "pl": "System plików Windows; dla dysków współdzielonych z Windows", "uk": "Файлова система Windows; для дисків, спільних із Windows", "zh": "Windows 文件系统；用于与 Windows 共用的驱动器", "zh_TW": "Windows 檔案系統；用於與 Windows 共用的驅動器", "ja": "Windows のファイルシステム。Windows と共有するドライブ用", "ko": "Windows 파일 시스템. Windows와 함께 쓰는 드라이브용"},
    "fs_desc_exfat": {"en": "Flash drives and cross-OS exchange; no Linux permissions",
                      "ru": "Флешки и обмен между ОС; без прав доступа Linux", "de": "USB-Sticks und Austausch zwischen Systemen; keine Linux-Berechtigungen", "fr": "Clés USB et échanges entre systèmes ; pas de permissions Linux", "es": "Memorias USB e intercambio entre sistemas; sin permisos de Linux", "pt": "Pendrives e troca entre sistemas; sem permissões do Linux", "pl": "Pendrive'y i wymiana między systemami; bez uprawnień Linuksa", "uk": "Флешки та обмін між системами; без прав Linux", "zh": "U 盘和跨系统交换；没有 Linux 权限", "zh_TW": "U 盤和跨系統交換；沒有 Linux 許可權", "ja": "USB メモリや OS 間のやり取り用。Linux の権限なし", "ko": "플래시 드라이브 및 다른 OS와 교환용. Linux 권한 없음"},
    "fs_desc_fat32": {"en": "Maximum compatibility; single file up to 4 GB",
                      "ru": "Максимальная совместимость; файл не больше 4 ГБ", "de": "Maximale Kompatibilität; einzelne Datei bis 4 GB", "fr": "Compatibilité maximale ; un fichier jusqu'à 4 Go", "es": "Máxima compatibilidad; un archivo de hasta 4 GB", "pt": "Compatibilidade máxima; arquivo único de até 4 GB", "pl": "Maksymalna zgodność; pojedynczy plik do 4 GB", "uk": "Максимальна сумісність; один файл до 4 ГБ", "zh": "最大兼容性；单个文件最大 4 GB", "zh_TW": "最大相容性；單個檔案最大 4 GB", "ja": "最大の互換性。1 ファイル 4 GB まで", "ko": "최대 호환성. 단일 파일 최대 4GB"},
    "fs_desc_fat16": {"en": "Legacy devices (cameras, MP3 players, embedded); volume up to 4 GiB",
                      "ru": "Старые устройства (фотоаппараты, MP3-плееры, встраиваемые); том до 4 ГиБ", "de": "Ältere Geräte (Kameras, MP3-Player, eingebettete Systeme); Volumen bis 4 GiB", "fr": "Anciens appareils (appareils photo, lecteurs MP3, systèmes embarqués) ; volume jusqu'à 4 Gio", "es": "Dispositivos antiguos (cámaras, reproductores MP3, embebidos); volumen de hasta 4 GiB", "pt": "Dispositivos antigos (câmeras, players MP3, embarcados); volume de até 4 GiB", "pl": "Starsze urządzenia (aparaty, odtwarzacze MP3, systemy wbudowane); wolumin do 4 GiB", "uk": "Старі пристрої (камери, MP3-плеєри, вбудовані системи); том до 4 ГіБ", "zh": "旧设备（相机、MP3 播放器、嵌入式设备）；卷最大 4 GiB", "zh_TW": "舊裝置（相機、MP3 播放器、嵌入式裝置）；卷最大 4 GiB", "ja": "古い機器（カメラ、MP3 プレーヤー、組み込み機器）。ボリュームは 4 GiB まで", "ko": "구형 장치 (카메라, MP3 플레이어, 임베디드). 볼륨 최대 4GiB"},
    "fs_desc_ext3":  {"en": "Older ext generation — only for compatibility with old systems",
                      "ru": "Старое поколение ext — только для совместимости со старыми системами", "de": "Ältere ext-Generation — nur für Kompatibilität mit alten Systemen", "fr": "Ancienne génération ext — seulement pour la compatibilité avec de vieux systèmes", "es": "Generación ext antigua — solo para compatibilidad con sistemas viejos", "pt": "Geração ext antiga — apenas para compatibilidade com sistemas antigos", "pl": "Starsza generacja ext — tylko dla zgodności ze starymi systemami", "uk": "Старе покоління ext — лише для сумісності зі старими системами", "zh": "较旧的 ext 版本——仅用于兼容旧系统", "zh_TW": "較舊的 ext 版本——僅用於相容舊系統", "ja": "旧世代の ext — 古いシステムとの互換性のためのみ", "ko": "구세대 ext — 오래된 시스템과의 호환용으로만"},
    "fs_desc_ext2":  {"en": "Legacy ext without journal — loses data on power failure",
                      "ru": "Древняя ext без журнала — теряет данные при сбое питания", "de": "Altes ext ohne Journal — Datenverlust bei Stromausfall", "fr": "Ancien ext sans journal — perte de données en cas de coupure de courant", "es": "ext antiguo sin journal — pierde datos ante un corte de luz", "pt": "ext antigo sem journal — perde dados em queda de energia", "pl": "Stary ext bez dziennika — traci dane przy zaniku zasilania", "uk": "Старий ext без журналу — втрачає дані при вимкненні живлення", "zh": "无日志的旧 ext——断电时会丢失数据", "zh_TW": "無日誌的舊 ext——斷電時會丟失資料", "ja": "ジャーナルなしの古い ext — 停電時にデータを失います", "ko": "저널 없는 구형 ext — 정전 시 데이터 손실"},
    # ── Профи-режим: разметка дисков ──
    "pro_mode":     {"en": "Advanced",                 "ru": "Расширенные",                "de": "Erweitert",                   "fr": "Avancé",                       "es": "Avanzado",                     "pt": "Avançado",                     "pl": "Zaawansowane",                "uk": "Розширені",                   "zh": "高级",                  "ja": "詳細設定", "zh_TW": "高階", "ko": "고급"},
    "part_section": {"en": "Disk Partitioning",        "ru": "Разметка дисков",            "de": "Festplatten-Partitionierung", "fr": "Partitionnement des disques",  "es": "Particionado de discos",       "pt": "Particionamento de discos",    "pl": "Partycjonowanie dysków",      "uk": "Розмітка дисків",             "zh": "磁盘分区",              "ja": "パーティション管理", "zh_TW": "磁碟分割槽", "ko": "디스크 파티션"},
    "free_space":   {"en": "Free space",               "ru": "Свободное место",            "de": "Freier Speicherplatz",        "fr": "Espace libre",                 "es": "Espacio libre",                "pt": "Espaço livre",                 "pl": "Wolne miejsce",               "uk": "Вільне місце",                "zh": "可用空间",              "ja": "空き領域", "zh_TW": "可用空間", "ko": "여유 공간"},
    "create_part":  {"en": "Create partition",         "ru": "Создать раздел",             "de": "Partition erstellen",         "fr": "Créer une partition",          "es": "Crear partición",              "pt": "Criar partição",               "pl": "Utwórz partycję",             "uk": "Створити розділ",             "zh": "创建分区",              "ja": "パーティションを作成", "zh_TW": "建立分割槽", "ko": "파티션 만들기"},
    "delete_part":  {"en": "Delete",                   "ru": "Удалить",                    "de": "Löschen",                     "fr": "Supprimer",                    "es": "Eliminar",                     "pt": "Excluir",                      "pl": "Usuń",                        "uk": "Видалити",                    "zh": "删除",                  "ja": "削除", "zh_TW": "刪除", "ko": "삭제"},
    "resize_part":  {"en": "Resize",                   "ru": "Изменить размер",            "de": "Größe ändern",                "fr": "Redimensionner",               "es": "Redimensionar",                "pt": "Redimensionar",                "pl": "Zmień rozmiar",               "uk": "Змінити розмір",              "zh": "调整大小",              "ja": "サイズ変更", "zh_TW": "調整大小", "ko": "크기 조정"},
    "new_table":    {"en": "New partition table",      "ru": "Новая таблица разделов",     "de": "Neue Partitionstabelle",      "fr": "Nouvelle table de partitions", "es": "Nueva tabla de particiones",   "pt": "Nova tabela de partições",     "pl": "Nowa tablica partycji",       "uk": "Нова таблиця розділів",       "zh": "新建分区表",            "ja": "新しいパーティションテーブル", "zh_TW": "新建分割槽表", "ko": "새 파티션 테이블"},
    "new_size":     {"en": "New size",                 "ru": "Новый размер",               "de": "Neue Größe",                  "fr": "Nouvelle taille",              "es": "Nuevo tamaño",                 "pt": "Novo tamanho",                 "pl": "Nowy rozmiar",                "uk": "Новий розмір",                "zh": "新大小",                "ja": "新しいサイズ", "zh_TW": "新大小", "ko": "새 크기"},
    "fs_none":      {"en": "no filesystem",            "ru": "без файловой системы",       "de": "kein Dateisystem",            "fr": "sans système de fichiers",     "es": "sin sistema de archivos",      "pt": "sem sistema de arquivos",      "pl": "bez systemu plików",          "uk": "без файлової системи",        "zh": "无文件系统",            "ja": "ファイルシステムなし", "zh_TW": "無檔案系統", "ko": "파일 시스템 없음"},
    "external_badge": {"en": "External drive (USB)",   "ru": "Внешний диск (USB)",         "de": "Externes Laufwerk (USB)",     "fr": "Disque externe (USB)",         "es": "Disco externo (USB)",          "pt": "Disco externo (USB)",          "pl": "Dysk zewnętrzny (USB)",       "uk": "Зовнішній диск (USB)",        "zh": "外部驱动器（USB）",     "ja": "外付けドライブ（USB）", "zh_TW": "外部驅動器（USB）", "ko": "외장 드라이브 (USB)"},
    "confirm_del_part": {
        "en": "DELETE partition /dev/{dev}?\n\nAll data on this partition will be PERMANENTLY LOST!",
        "ru": "УДАЛИТЬ раздел /dev/{dev}?\n\nВсе данные на этом разделе будут БЕЗВОЗВРАТНО ПОТЕРЯНЫ!",
        "de": "Partition /dev/{dev} LÖSCHEN?\n\nAlle Daten auf dieser Partition gehen UNWIDERRUFLICH verloren!",
        "fr": "SUPPRIMER la partition /dev/{dev} ?\n\nToutes les données de cette partition seront DÉFINITIVEMENT PERDUES !",
        "es": "¿ELIMINAR la partición /dev/{dev}?\n\n¡Todos los datos de esta partición se PERDERÁN PERMANENTEMENTE!",
        "pt": "EXCLUIR a partição /dev/{dev}?\n\nTodos os dados desta partição serão PERDIDOS PERMANENTEMENTE!",
        "pl": "USUNĄĆ partycję /dev/{dev}?\n\nWszystkie dane na tej partycji zostaną TRWALE UTRACONE!",
        "uk": "ВИДАЛИТИ розділ /dev/{dev}?\n\nУсі дані на цьому розділі будуть БЕЗПОВОРОТНО ВТРАЧЕНІ!",
        "zh": "删除分区 /dev/{dev}？\n\n该分区上的所有数据将永久丢失！",
        "ja": "パーティション /dev/{dev} を削除しますか？\n\nこのパーティションのすべてのデータが完全に失われます！", "zh_TW": "刪除分割槽 /dev/{dev}？\n\n該分割槽上的所有資料將永久丟失！", "ko": "파티션 /dev/{dev}을(를) 삭제할까요?\n\n이 파티션의 모든 데이터가 영구적으로 사라집니다!",
    },
    "confirm_new_table": {
        "en": "Create a new {type} partition table on /dev/{disk}?\n\nEVERY partition and ALL data on the ENTIRE disk will be destroyed!",
        "ru": "Создать новую таблицу разделов {type} на /dev/{disk}?\n\nВСЕ разделы и ВСЕ данные на ВСЁМ диске будут уничтожены!",
        "de": "Neue {type}-Partitionstabelle auf /dev/{disk} erstellen?\n\nJEDE Partition und ALLE Daten auf der GESAMTEN Festplatte werden zerstört!",
        "fr": "Créer une nouvelle table de partitions {type} sur /dev/{disk} ?\n\nTOUTES les partitions et TOUTES les données du disque ENTIER seront détruites !",
        "es": "¿Crear una nueva tabla de particiones {type} en /dev/{disk}?\n\n¡TODAS las particiones y TODOS los datos del disco COMPLETO serán destruidos!",
        "pt": "Criar uma nova tabela de partições {type} em /dev/{disk}?\n\nTODAS as partições e TODOS os dados do disco INTEIRO serão destruídos!",
        "pl": "Utworzyć nową tablicę partycji {type} na /dev/{disk}?\n\nWSZYSTKIE partycje i WSZYSTKIE dane na CAŁYM dysku zostaną zniszczone!",
        "uk": "Створити нову таблицю розділів {type} на /dev/{disk}?\n\nУСІ розділи та ВСІ дані на ВСЬОМУ диску буде знищено!",
        "zh": "在 /dev/{disk} 上创建新的 {type} 分区表？\n\n整个磁盘上的所有分区和所有数据都将被销毁！",
        "ja": "/dev/{disk} に新しい {type} パーティションテーブルを作成しますか？\n\nディスク全体のすべてのパーティションとデータが破壊されます！", "zh_TW": "在 /dev/{disk} 上建立新的 {type} 分割槽表？\n\n整個磁碟上的所有分割槽和所有資料都將被銷燬！", "ko": "/dev/{disk}에 새 {type} 파티션 테이블을 만들까요?\n\n디스크 전체의 모든 파티션과 모든 데이터가 삭제됩니다!",
    },
    "confirm_resize": {
        "en": "Resize /dev/{dev} to {size}?",
        "ru": "Изменить размер /dev/{dev} до {size}?",
        "de": "Größe von /dev/{dev} auf {size} ändern?",
        "fr": "Redimensionner /dev/{dev} à {size} ?",
        "es": "¿Redimensionar /dev/{dev} a {size}?",
        "pt": "Redimensionar /dev/{dev} para {size}?",
        "pl": "Zmienić rozmiar /dev/{dev} na {size}?",
        "uk": "Змінити розмір /dev/{dev} до {size}?",
        "zh": "将 /dev/{dev} 调整为 {size}？",
        "ja": "/dev/{dev} を {size} にサイズ変更しますか？", "zh_TW": "將 /dev/{dev} 調整為 {size}？", "ko": "/dev/{dev}의 크기를 {size}(으)로 조정할까요?",
    },
    # ── Сетевые диски ──
    "net_section":  {"en": "Network Drives",           "ru": "Сетевые диски",              "de": "Netzlaufwerke",               "fr": "Lecteurs réseau",              "es": "Unidades de red",              "pt": "Unidades de rede",             "pl": "Dyski sieciowe",              "uk": "Мережеві диски",              "zh": "网络驱动器",            "ja": "ネットワークドライブ", "zh_TW": "網路驅動器", "ko": "네트워크 드라이브"},
    "add_net":      {"en": "Add network drive",        "ru": "Добавить сетевой диск",      "de": "Netzlaufwerk hinzufügen",     "fr": "Ajouter un lecteur réseau",    "es": "Añadir unidad de red",         "pt": "Adicionar unidade de rede",    "pl": "Dodaj dysk sieciowy",         "uk": "Додати мережевий диск",       "zh": "添加网络驱动器",        "ja": "ネットワークドライブを追加", "zh_TW": "新增網路驅動器", "ko": "네트워크 드라이브 추가"},
    "server":       {"en": "Server",                   "ru": "Сервер",                     "de": "Server",                      "fr": "Serveur",                      "es": "Servidor",                     "pt": "Servidor",                     "pl": "Serwer",                      "uk": "Сервер",                      "zh": "服务器",                "ja": "サーバー", "zh_TW": "伺服器", "ko": "서버"},
    "net_share":    {"en": "Share (folder on server)", "ru": "Шара (папка на сервере)",    "de": "Freigabe (Ordner am Server)", "fr": "Partage (dossier du serveur)", "es": "Recurso (carpeta del servidor)", "pt": "Compartilhamento (pasta)",   "pl": "Udział (folder na serwerze)", "uk": "Спільна тека на сервері",     "zh": "共享（服务器上的文件夹）", "ja": "共有（サーバー上のフォルダー）", "zh_TW": "共享（伺服器上的資料夾）", "ko": "공유 폴더 (서버의 폴더)"},
    "username":     {"en": "Username",                 "ru": "Имя пользователя",           "de": "Benutzername",                "fr": "Nom d'utilisateur",            "es": "Usuario",                      "pt": "Usuário",                      "pl": "Nazwa użytkownika",           "uk": "Ім'я користувача",            "zh": "用户名",                "ja": "ユーザー名", "zh_TW": "使用者名稱", "ko": "사용자 이름"},
    "password":     {"en": "Password",                 "ru": "Пароль",                     "de": "Passwort",                    "fr": "Mot de passe",                 "es": "Contraseña",                   "pt": "Senha",                        "pl": "Hasło",                       "uk": "Пароль",                      "zh": "密码",                  "ja": "パスワード", "zh_TW": "密碼", "ko": "암호"},
    "guest_access": {"en": "Guest access (no password)", "ru": "Гостевой доступ (без пароля)", "de": "Gastzugang (ohne Passwort)", "fr": "Accès invité (sans mot de passe)", "es": "Acceso de invitado (sin contraseña)", "pt": "Acesso de convidado (sem senha)", "pl": "Dostęp gościa (bez hasła)", "uk": "Гостьовий доступ (без пароля)", "zh": "来宾访问（无密码）",    "ja": "ゲストアクセス（パスワードなし）", "zh_TW": "來賓訪問（無密碼）", "ko": "게스트 접근 (암호 없음)"},
    "connect":      {"en": "Connect",                  "ru": "Подключить",                 "de": "Verbinden",                   "fr": "Connecter",                    "es": "Conectar",                     "pt": "Conectar",                     "pl": "Połącz",                      "uk": "Підключити",                  "zh": "连接",                  "ja": "接続", "zh_TW": "連線", "ko": "연결"},
    "net_connected": {"en": "Connected",               "ru": "Подключён",                  "de": "Verbunden",                   "fr": "Connecté",                     "es": "Conectado",                    "pt": "Conectado",                    "pl": "Połączono",                   "uk": "Підключено",                  "zh": "已连接",                "ja": "接続済み", "zh_TW": "已連線", "ko": "연결됨"},
    "net_not_conn": {"en": "Not connected",            "ru": "Не подключён",               "de": "Nicht verbunden",             "fr": "Non connecté",                 "es": "No conectado",                 "pt": "Não conectado",                "pl": "Nie połączono",               "uk": "Не підключено",               "zh": "未连接",                "ja": "未接続", "zh_TW": "未連線", "ko": "연결되지 않음"},
    "confirm_rm_net": {
        "en": "Remove network drive {src}?\n\nData on the server is NOT affected — only the connection is removed.",
        "ru": "Убрать сетевой диск {src}?\n\nДанные на сервере НЕ пострадают — удаляется только подключение.",
        "de": "Netzlaufwerk {src} entfernen?\n\nDaten auf dem Server bleiben UNBERÜHRT — nur die Verbindung wird entfernt.",
        "fr": "Supprimer le lecteur réseau {src} ?\n\nLes données du serveur ne sont PAS affectées — seule la connexion est supprimée.",
        "es": "¿Quitar la unidad de red {src}?\n\nLos datos del servidor NO se ven afectados — solo se elimina la conexión.",
        "pt": "Remover a unidade de rede {src}?\n\nOs dados no servidor NÃO são afetados — apenas a conexão é removida.",
        "pl": "Usunąć dysk sieciowy {src}?\n\nDane na serwerze NIE ucierpią — usuwane jest tylko połączenie.",
        "uk": "Прибрати мережевий диск {src}?\n\nДані на сервері НЕ постраждають — видаляється лише підключення.",
        "zh": "移除网络驱动器 {src}？\n\n服务器上的数据不受影响——仅删除连接。",
        "ja": "ネットワークドライブ {src} を削除しますか？\n\nサーバー上のデータは影響を受けません — 接続のみ削除されます。", "zh_TW": "移除網路驅動器 {src}？\n\n伺服器上的資料不受影響——僅刪除連線。", "ko": "네트워크 드라이브 {src}을(를) 제거할까요?\n\n서버의 데이터에는 영향이 없습니다 — 연결만 제거됩니다.",
    },
    "ssh_key":      {"en": "SSH key file",             "ru": "Файл SSH-ключа",             "de": "SSH-Schlüsseldatei",          "fr": "Fichier de clé SSH",           "es": "Archivo de clave SSH",         "pt": "Arquivo de chave SSH",         "pl": "Plik klucza SSH",             "uk": "Файл SSH-ключа",              "zh": "SSH 密钥文件",          "ja": "SSH 鍵ファイル", "zh_TW": "SSH 金鑰檔案", "ko": "SSH 키 파일"},
    "net_hint":     {"en": "The drive is mounted into a real folder visible to ALL apps (not only Dolphin). It connects on first access; boot never hangs if the server is off.",
                     "ru": "Диск монтируется в настоящую папку, видимую ВСЕМ программам (не только Dolphin). Подключается при первом обращении; загрузка не виснет, если сервер выключен.", "de": "Das Laufwerk wird in einen echten Ordner eingehängt, den ALLE Programme sehen (nicht nur Dolphin). Es verbindet sich beim ersten Zugriff; der Start hängt nie, wenn der Server aus ist.", "fr": "Le disque est monté dans un vrai dossier visible par TOUTES les applications (pas seulement Dolphin). Il se connecte au premier accès ; le démarrage ne se bloque jamais si le serveur est éteint.", "es": "La unidad se monta en una carpeta real visible para TODAS las aplicaciones (no solo Dolphin). Se conecta en el primer acceso; el arranque nunca se cuelga si el servidor está apagado.", "pt": "A unidade é montada em uma pasta real visível para TODOS os aplicativos (não só o Dolphin). Ela conecta no primeiro acesso; a inicialização nunca trava se o servidor estiver desligado.", "pl": "Dysk jest montowany w prawdziwym folderze widocznym dla WSZYSTKICH aplikacji (nie tylko Dolphina). Łączy się przy pierwszym dostępie; uruchamianie nigdy się nie zawiesza, gdy serwer jest wyłączony.", "uk": "Диск монтується в справжню теку, яку бачать УСІ програми (не лише Dolphin). Він під'єднується під час першого звернення; завантаження ніколи не зависає, якщо сервер вимкнено.", "zh": "驱动器挂载到所有应用都能看到的真实文件夹中（不只是 Dolphin）。首次访问时连接；服务器关闭时启动也不会卡住。", "zh_TW": "驅動器掛載到所有應用都能看到的真實資料夾中（不只是 Dolphin）。首次訪問時連線；伺服器關閉時啟動也不會卡住。", "ja": "ドライブはすべてのアプリから見える実際のフォルダーにマウントされます（Dolphin だけではありません）。最初のアクセス時に接続され、サーバーが停止していても起動が止まることはありません。", "ko": "드라이브가 실제 폴더에 마운트되어 (Dolphin뿐 아니라) 모든 앱에서 보입니다. 처음 접근할 때 연결되며, 서버가 꺼져 있어도 부팅이 멈추지 않습니다."},
    "warn_net_fields": {"en": "Fill in server and share!", "ru": "Заполни сервер и шару!",
                        "de": "Server und Freigabe ausfüllen!", "fr": "Renseignez le serveur et le partage !",
                        "es": "¡Rellena el servidor y el recurso!", "pt": "Preencha o servidor e o compartilhamento!",
                        "pl": "Wypełnij serwer i udział!", "uk": "Заповни сервер і теку!",
                        "zh": "请填写服务器和共享！", "ja": "サーバーと共有を入力してください！", "zh_TW": "請填寫伺服器和共享！", "ko": "서버와 공유 폴더를 입력하세요!"},
    # en+ru — прочие языки берут en через t()
    "shrink_warn":  {"en": "\n\nShrinking moves the filesystem boundary — back up important data first!",
                     "ru": "\n\nУменьшение сдвигает границу файловой системы — сначала сделай резервную копию важных данных!", "de": "\n\nDas Verkleinern verschiebt die Dateisystemgrenze — sichern Sie zuerst wichtige Daten!", "fr": "\n\nLa réduction déplace la limite du système de fichiers — sauvegardez d'abord vos données importantes !", "es": "\n\nReducir mueve el límite del sistema de archivos — ¡haga primero una copia de seguridad de los datos importantes!", "pt": "\n\nReduzir move o limite do sistema de arquivos — faça backup dos dados importantes primeiro!", "pl": "\n\nZmniejszenie przesuwa granicę systemu plików — najpierw zrób kopię ważnych danych!", "uk": "\n\nЗменшення зсуває межу файлової системи — спершу зробіть резервну копію важливих даних!", "zh": "\n\n缩小会移动文件系统边界——请先备份重要数据！", "zh_TW": "\n\n縮小會移動檔案系統邊界——請先備份重要資料！", "ja": "\n\n縮小するとファイルシステムの境界が移動します — 重要なデータを先にバックアップしてください！", "ko": "\n\n축소하면 파일 시스템 경계가 이동합니다 — 중요한 데이터를 먼저 백업하세요!"},
    "no_pt":        {"en": "No partition table — create one to use this disk",
                     "ru": "Нет таблицы разделов — создай её, чтобы использовать диск", "de": "Keine Partitionstabelle — erstellen Sie eine, um diese Festplatte zu verwenden", "fr": "Pas de table de partitions — créez-en une pour utiliser ce disque", "es": "Sin tabla de particiones — cree una para usar este disco", "pt": "Sem tabela de partições — crie uma para usar este disco", "pl": "Brak tablicy partycji — utwórz ją, aby używać tego dysku", "uk": "Немає таблиці розділів — створіть її, щоб користуватися цим диском", "zh": "没有分区表——请创建一个以使用此磁盘", "zh_TW": "沒有分割槽表——請建立一個以使用此磁碟", "ja": "パーティションテーブルがありません — このディスクを使うには作成してください", "ko": "파티션 테이블 없음 — 이 디스크를 쓰려면 만드세요"},
    "ntfs_driver_line": {"en": "NTFS driver: {drv}", "ru": "Драйвер NTFS: {drv}", "de": "NTFS-Treiber: {drv}", "fr": "Pilote NTFS : {drv}", "es": "Controlador NTFS: {drv}", "pt": "Driver NTFS: {drv}", "pl": "Sterownik NTFS: {drv}", "uk": "Драйвер NTFS: {drv}", "zh": "NTFS 驱动：{drv}", "zh_TW": "NTFS 驅動：{drv}", "ja": "NTFS ドライバー：{drv}", "ko": "NTFS 드라이버: {drv}"},
    "tt_pro":       {"en": "Show advanced partitioning tools for experienced users",
                     "ru": "Показать инструменты разметки для опытных пользователей", "de": "Erweiterte Partitionierungswerkzeuge für erfahrene Benutzer anzeigen", "fr": "Afficher les outils de partitionnement avancés pour utilisateurs expérimentés", "es": "Mostrar herramientas avanzadas de particionado para usuarios expertos", "pt": "Mostrar ferramentas avançadas de particionamento para usuários experientes", "pl": "Pokaż zaawansowane narzędzia partycjonowania dla doświadczonych użytkowników", "uk": "Показати розширені інструменти розмітки для досвідчених користувачів", "zh": "为有经验的用户显示高级分区工具", "zh_TW": "為有經驗的使用者顯示高階分割槽工具", "ja": "上級者向けの高度なパーティション操作ツールを表示", "ko": "숙련된 사용자를 위한 고급 파티션 도구 표시"},
    "resize_na":    {"en": "Resize is not available for this filesystem",
                     "ru": "Для этой файловой системы изменение размера недоступно", "de": "Größenänderung ist für dieses Dateisystem nicht verfügbar", "fr": "Le redimensionnement n'est pas disponible pour ce système de fichiers", "es": "El cambio de tamaño no está disponible para este sistema de archivos", "pt": "O redimensionamento não está disponível para este sistema de arquivos", "pl": "Zmiana rozmiaru nie jest dostępna dla tego systemu plików", "uk": "Зміна розміру недоступна для цієї файлової системи", "zh": "此文件系统不支持调整大小", "zh_TW": "此檔案系統不支援調整大小", "ja": "このファイルシステムではサイズ変更を利用できません", "ko": "이 파일 시스템은 크기 조정을 지원하지 않습니다"},
}


class FormatConfirmDialog(QDialog):
    """Подтверждение форматирования: кнопка становится активной только после
    того, как пользователь вручную введёт имя раздела. Случайный клик или
    машинальное Enter (Enter = Отмена) стереть данные не могут."""

    def __init__(self, parent, t, dev_name, info, new_fs, cmd_str, note=""):
        super().__init__(parent)
        self.setObjectName("FmtConfirm")
        self.setWindowTitle(t("dlg_confirm_fmt"))
        self.setModal(True)
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        head = QLabel(t("fmt_warn"))
        head.setObjectName("DangerLabel")
        lay.addWidget(head)

        body = QLabel(t("confirm_fmt").format(dev=dev_name) + note)
        body.setObjectName("DlgText")
        body.setWordWrap(True)
        lay.addWidget(body)

        parts = [f"/dev/{dev_name}", info.get("size", "?")]
        if info.get("label"):
            parts.append(info["label"])
        old_fs = fs_display(info.get("fstype", "?"), info.get("fsver") or "")
        parts.append(f"{old_fs} → {fs_display(new_fs)}")
        info_lbl = QLabel("  —  ".join(parts))
        info_lbl.setObjectName("OrphanInfoLabel")
        lay.addWidget(info_lbl)

        if cmd_str:
            cmd_lbl = QLabel(cmd_str)
            cmd_lbl.setObjectName("CmdPreview")
            cmd_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(cmd_lbl)

        hint = QLabel(t("confirm_type_hint").format(dev=dev_name))
        hint.setObjectName("DlgText")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self._edit = QLineEdit()
        self._edit.setObjectName("DestEdit")
        self._edit.setPlaceholderText(dev_name)
        lay.addWidget(self._edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(t("cancel"))
        cancel_btn.setObjectName("BrowseBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setDefault(True)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._ok_btn = QPushButton(t("format_btn"))
        self._ok_btn.setObjectName("DangerBtn")
        self._ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok_btn.setEnabled(False)
        self._ok_btn.setAutoDefault(False)
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._ok_btn)
        lay.addLayout(btn_row)

        self._edit.textChanged.connect(
            lambda s: self._ok_btn.setEnabled(s.strip() == dev_name))
        self._edit.setFocus()


class ActionConfirmDialog(QDialog):
    """Универсальное подтверждение опасной операции разметки.
    Если задан confirm_name — кнопка активируется только после его ввода
    (как при форматировании); без него — обычное подтверждение."""

    def __init__(self, parent, t, body, info_line="", cmd_str="",
                 confirm_name=None, ok_text=None):
        super().__init__(parent)
        self.setObjectName("FmtConfirm")
        self.setWindowTitle(t("dlg_warning"))
        self.setModal(True)
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        head = QLabel(t("dlg_warning"))
        head.setObjectName("DangerLabel")
        lay.addWidget(head)

        body_lbl = QLabel(body)
        body_lbl.setObjectName("DlgText")
        body_lbl.setWordWrap(True)
        lay.addWidget(body_lbl)

        if info_line:
            info_lbl = QLabel(info_line)
            info_lbl.setObjectName("OrphanInfoLabel")
            lay.addWidget(info_lbl)

        if cmd_str:
            cmd_lbl = QLabel(cmd_str)
            cmd_lbl.setObjectName("CmdPreview")
            cmd_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(cmd_lbl)

        self._edit = None
        if confirm_name:
            hint = QLabel(t("confirm_type_hint").format(dev=confirm_name))
            hint.setObjectName("DlgText")
            hint.setWordWrap(True)
            lay.addWidget(hint)
            self._edit = QLineEdit()
            self._edit.setObjectName("DestEdit")
            self._edit.setPlaceholderText(confirm_name)
            lay.addWidget(self._edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(t("cancel"))
        cancel_btn.setObjectName("BrowseBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setDefault(True)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._ok_btn = QPushButton(ok_text or "OK")
        self._ok_btn.setObjectName("DangerBtn")
        self._ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok_btn.setAutoDefault(False)
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._ok_btn)
        lay.addLayout(btn_row)

        if self._edit is not None:
            self._ok_btn.setEnabled(False)
            self._edit.textChanged.connect(
                lambda s: self._ok_btn.setEnabled(s.strip() == confirm_name))
            self._edit.setFocus()


class DiskWorker(QThread):
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
            backend_script = os.path.join(os.path.dirname(sys.executable), "equestria-os-disk-backend")
            inner = [backend_script] + self.command_args
        else:
            backend_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disk_backend.py")
            inner = [sys.executable, backend_script] + self.command_args
        if os.path.basename(elevator) == "kdesu":
            cmd = [elevator, "--"] + inner
        else:
            cmd = [elevator] + inner

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate()

        if proc.returncode == 0:
            self.finished.emit(True, stdout.strip())
        else:
            self.finished.emit(False, stderr.strip())


class DiskManagerApp(QMainWindow):
    @staticmethod
    def _set_btn_state(btn, state):
        """Вид кнопки задаётся свойством state в style.qss, а не цветами в коде."""
        btn.setProperty("state", state)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def __init__(self):
        super().__init__()
        self.current_lang = detect_language()
        if self.current_lang not in LANGS:
            self.current_lang = "en"

        self.partitions = {}
        self._setup_ui()
        self._load_disks()

    def t(self, key):
        d = STRINGS.get(key, {})
        return d.get(self.current_lang) or d.get("en", key)

    def _change_lang(self, lang):
        self.current_lang = lang
        idx = self.lang_combo.findData(lang)
        if idx != -1 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.setCurrentIndex(idx)
        self._refresh_ui()

    def _refresh_ui(self):
        self.setWindowTitle(self.t("title"))
        self.app_title.setText(self.t("title"))
        self.lbl_select.setText(self.t("select_disk"))
        self.lbl_mount.setText(self.t("mount_point"))
        self.lbl_opts.setText(self.t("fstab_opts"))
        self.lbl_user.setText(self.t("select_user"))
        self.lbl_lbl_section.setText(self.t("lbl_section"))
        self.lbl_fmt_section.setText(self.t("fmt_section"))
        self.fmt_warn_lbl.setText(self.t("fmt_warn"))
        self.lbl_new_fs.setText(self.t("new_fs") + ":")

        self.mount_input.setPlaceholderText(self.t("ph_mount"))
        self.label_input.setPlaceholderText(self.t("ph_label"))
        self.format_label_input.setPlaceholderText(self.t("fmt_lbl_ph"))

        self.recursive_cb.setLabelText(self.t("recursive"))
        self.perms_btn.setText(self.t("fix_perms"))
        self.mount_now_btn.setText(self.t("mount_now"))
        self.umount_btn.setText(self.t("umount"))
        self.set_label_btn.setText(self.t("set_label"))
        self.format_btn.setText(self.t("format_btn"))

        self.disk_combo.setToolTip(self.t("tt_disk"))
        self.mount_input.setToolTip(self.t("tt_mount"))
        self.lbl_opts.setToolTip(self.t("tt_opts"))
        self.automount_btn.setToolTip(self.t("tt_auto"))
        self.opts_widget.set_lang(self.current_lang)
        self.user_combo.setToolTip(self.t("tt_user"))
        self.recursive_cb.setToolTip(self.t("tt_rec"))
        self.perms_btn.setToolTip(self.t("tt_perms"))
        self.refresh_btn.setToolTip(self.t("refresh"))
        self.mount_now_btn.setToolTip(self.t("tt_mount_now"))
        self.umount_btn.setToolTip(self.t("tt_umount"))
        self.set_label_btn.setToolTip(self.t("tt_set_label"))
        self.save_fstab_btn.setText(self.t("save_fstab"))
        self.save_fstab_btn.setToolTip(self.t("tt_save_fstab"))
        self.open_fstab_btn.setText(self.t("open_fstab"))
        self.open_fstab_btn.setToolTip(self.t("tt_open_fstab"))
        self.keep_uuid_cb.setLabelText(self.t("keep_uuid"))
        self.keep_uuid_cb.setToolTip(self.t("tt_keep_uuid"))
        self._update_fold_text()
        self.pro_fold_btn.setToolTip(self.t("tt_pro"))
        self.lbl_pro_section.setText(self.t("part_section"))
        self.pro_mktable_btn.setText(self.t("new_table"))
        if self.pro_fold_btn.isChecked():
            self._render_pro_disk()
        self._update_net_fold_text()
        self.net_hint_lbl.setText(self.t("net_hint"))
        self.net_add_btn.setText(self.t("add_net"))
        if self.net_fold_btn.isChecked():
            self._load_net_shares()

        self._fstab_health_title.setText(self.t("fstab_issues"))
        self._fstab_health_hint.setText(self.t("fstab_orphan_hint"))

        self._on_disk_selected()

    def _make_divider(self):
        d = QFrame()
        d.setObjectName("Divider")
        d.setFrameShape(QFrame.Shape.HLine)
        d.setFixedHeight(1)
        return d

    def _get_system_users(self):
        users = ["root"]
        try:
            with open("/etc/passwd", "r") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if len(parts) >= 3:
                        name = parts[0]
                        uid = int(parts[2])
                        if uid >= 1000 and name != "nobody":
                            users.append(name)
        except Exception:
            pass
        return sorted(list(set(users)))

    def _setup_ui(self):
        self.setWindowTitle(self.t("title"))
        self.resize(700, 820)

        base_path = os.path.dirname(os.path.abspath(__file__))

        # Load custom font first so we can inject its name into the QSS
        title_font_family = "sans-serif"
        font_path = os.path.join(base_path, "equestria_cyrillic.ttf")
        if os.path.exists(font_path):
            families = font_families(font_path)
            if families:
                title_font_family = families[0]

        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            qss = open(qss_path).read()
            # Цвета в style.qss — роли общей темы; ThemeManager сам перекрасит
            # приложение при выборе другого персонажа в переключателе тем.
            kit_qt.style(self, qss.replace("{{TITLE_FONT}}", f'"{title_font_family}"'))

        # Central → scroll → content
        central = QWidget()
        central.setObjectName("CentralBg")
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer_layout.addWidget(scroll, 1)

        self.root = QWidget()
        self.root.setObjectName("root")
        scroll.setWidget(self.root)

        main_layout = QVBoxLayout(self.root)
        main_layout.setContentsMargins(30, 20, 30, 20)
        main_layout.setSpacing(12)

        # --- Title + Language ---
        title_row = QHBoxLayout()
        self.app_title = QLabel(self.t("title"))
        self.app_title.setObjectName("AppTitle")
        title_row.addWidget(self.app_title)
        title_row.addStretch()

        # Компактный выпадающий список языков вместо ряда кнопок
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("LangCombo")
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for code in LANGS:
            self.lang_combo.addItem(code.upper(), code)
        idx = self.lang_combo.findData(self.current_lang)
        if idx != -1:
            self.lang_combo.setCurrentIndex(idx)
        # activated срабатывает только при выборе пользователем — без рекурсии
        self.lang_combo.activated.connect(
            lambda i: self._change_lang(self.lang_combo.itemData(i)))
        title_row.addWidget(self.lang_combo)
        main_layout.addLayout(title_row)
        main_layout.addWidget(self._make_divider())

        # --- Disk selection ---
        self.lbl_select = QLabel(self.t("select_disk"))
        self.lbl_select.setObjectName("SectionLabel")
        main_layout.addWidget(self.lbl_select)

        disk_row = QHBoxLayout()
        self.disk_combo = QComboBox()
        self.disk_combo.setObjectName("SourceEdit")
        self.disk_combo.setFixedHeight(34)
        self.disk_combo.currentIndexChanged.connect(self._on_disk_selected)

        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setObjectName("BrowseBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._load_disks)

        disk_row.addWidget(self.disk_combo, 1)
        disk_row.addWidget(self.refresh_btn)
        main_layout.addLayout(disk_row)

        # Info panel (UUID, fstype, size, mount status, usage)
        self.info_lbl = QLabel("")
        self.info_lbl.setObjectName("PartInfoLabel")  # сведения о разделе — обычный текст, не «успех»
        self.info_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info_lbl.setCursor(Qt.CursorShape.IBeamCursor)
        main_layout.addWidget(self.info_lbl)

        # Mount / Unmount quick buttons
        mount_row = QHBoxLayout()
        self.mount_now_btn = QPushButton(self.t("mount_now"))
        self.mount_now_btn.setObjectName("AddSourceBtn")
        self.mount_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mount_now_btn.clicked.connect(self._mount_now)

        self.umount_btn = QPushButton(self.t("umount"))
        self.umount_btn.setObjectName("BrowseBtn")
        self.umount_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.umount_btn.clicked.connect(self._umount_now)

        mount_row.addWidget(self.mount_now_btn)
        mount_row.addWidget(self.umount_btn)
        main_layout.addLayout(mount_row)
        main_layout.addWidget(self._make_divider())

        # --- fstab Health ---
        self._build_fstab_health_section(main_layout)

        # --- fstab / Automount ---
        self.lbl_mount = QLabel(self.t("mount_point"))
        self.lbl_mount.setObjectName("SectionLabel")
        main_layout.addWidget(self.lbl_mount)

        self.mount_input = QLineEdit()
        self.mount_input.setObjectName("DestEdit")
        main_layout.addWidget(self.mount_input)

        self.lbl_opts = QLabel(self.t("fstab_opts"))
        self.lbl_opts.setObjectName("SectionLabel")
        main_layout.addWidget(self.lbl_opts)

        self.opts_widget = FstabOptionsWidget()
        main_layout.addWidget(self.opts_widget)

        self.automount_btn = QPushButton(self.t("automount"))
        self.automount_btn.setObjectName("RelocateBtn")
        self.automount_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.automount_btn.clicked.connect(self._toggle_automount)
        main_layout.addWidget(self.automount_btn)

        self.save_fstab_btn = QPushButton(self.t("save_fstab"))
        self.save_fstab_btn.setObjectName("AddSourceBtn")
        self.save_fstab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_fstab_btn.clicked.connect(self._save_fstab)
        self.save_fstab_btn.setVisible(False)
        main_layout.addWidget(self.save_fstab_btn)

        self.open_fstab_btn = QPushButton(self.t("open_fstab"))
        self.open_fstab_btn.setObjectName("BrowseBtn")
        self.open_fstab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_fstab_btn.setToolTip(self.t("tt_open_fstab"))
        self.open_fstab_btn.clicked.connect(self._open_fstab)
        main_layout.addWidget(self.open_fstab_btn)
        main_layout.addWidget(self._make_divider())

        # --- Permissions ---
        self.lbl_user = QLabel(self.t("select_user"))
        self.lbl_user.setObjectName("SectionLabel")
        main_layout.addWidget(self.lbl_user)

        self.user_combo = QComboBox()
        self.user_combo.setObjectName("SourceEdit")
        self.user_combo.setFixedHeight(34)
        self.user_combo.addItems(self._get_system_users())
        current_user = os.environ.get("USER", "root")
        idx = self.user_combo.findText(current_user)
        if idx >= 0:
            self.user_combo.setCurrentIndex(idx)
        # Смена владельца обновляет uid/gid в сгенерированных опциях fstab,
        # но не трогает опции, отредактированные пользователем вручную
        self.user_combo.currentIndexChanged.connect(self._on_user_changed)
        main_layout.addWidget(self.user_combo)

        self.recursive_cb = SwitchToggle(self.t("recursive"))
        self.recursive_cb.setChecked(False)
        main_layout.addWidget(self.recursive_cb)

        self.perms_btn = QPushButton(self.t("fix_perms"))
        self.perms_btn.setObjectName("AddSourceBtn")
        self.perms_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.perms_btn.clicked.connect(self._fix_permissions)
        main_layout.addWidget(self.perms_btn)
        main_layout.addWidget(self._make_divider())

        # --- Partition Label ---
        self.lbl_lbl_section = QLabel(self.t("lbl_section"))
        self.lbl_lbl_section.setObjectName("SectionLabel")
        main_layout.addWidget(self.lbl_lbl_section)

        label_row = QHBoxLayout()
        self.label_input = QLineEdit()
        self.label_input.setObjectName("DestEdit")
        self.label_input.setPlaceholderText(self.t("ph_label"))

        self.set_label_btn = QPushButton(self.t("set_label"))
        self.set_label_btn.setObjectName("BrowseBtn")
        self.set_label_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_label_btn.clicked.connect(self._set_label)

        label_row.addWidget(self.label_input, 1)
        label_row.addWidget(self.set_label_btn)
        main_layout.addLayout(label_row)
        main_layout.addWidget(self._make_divider())

        # --- Format (danger zone) ---
        fmt_frame = QFrame()
        fmt_frame.setObjectName("DangerFrame")
        fmt_layout = QVBoxLayout(fmt_frame)
        fmt_layout.setContentsMargins(12, 10, 12, 10)
        fmt_layout.setSpacing(8)

        self.lbl_fmt_section = QLabel(self.t("fmt_section"))
        self.lbl_fmt_section.setObjectName("DangerLabel")
        fmt_layout.addWidget(self.lbl_fmt_section)

        self.fmt_warn_lbl = QLabel(self.t("fmt_warn"))
        self.fmt_warn_lbl.setObjectName("DangerWarn")
        fmt_layout.addWidget(self.fmt_warn_lbl)

        fs_row = QHBoxLayout()
        self.lbl_new_fs = QLabel(self.t("new_fs") + ":")
        self.lbl_new_fs.setObjectName("SectionLabel")
        self.fs_combo = QComboBox()
        self.fs_combo.setObjectName("SourceEdit")
        self.fs_combo.setFixedHeight(34)
        # В data лежит значение для mkfs/fstab, в тексте — полное имя без сокращений
        for fs_value in ("ext4", "btrfs", "ntfs", "exfat", "fat32", "fat16", "ext3", "ext2"):
            self.fs_combo.addItem(fs_display(fs_value), fs_value)
        fs_row.addWidget(self.lbl_new_fs)
        fs_row.addWidget(self.fs_combo, 1)
        fmt_layout.addLayout(fs_row)

        self.fs_desc_lbl = QLabel("")
        self.fs_desc_lbl.setObjectName("FmtDesc")
        self.fs_desc_lbl.setWordWrap(True)
        fmt_layout.addWidget(self.fs_desc_lbl)

        self.format_label_input = QLineEdit()
        self.format_label_input.setObjectName("DestEdit")
        self.format_label_input.setPlaceholderText(self.t("fmt_lbl_ph"))
        fmt_layout.addWidget(self.format_label_input)

        self.fmt_label_hint = QLabel("")
        self.fmt_label_hint.setObjectName("FmtLabelError")
        self.fmt_label_hint.setWordWrap(True)
        self.fmt_label_hint.setVisible(False)
        fmt_layout.addWidget(self.fmt_label_hint)

        self.keep_uuid_cb = SwitchToggle(self.t("keep_uuid"))
        self.keep_uuid_cb.setVisible(False)
        fmt_layout.addWidget(self.keep_uuid_cb)

        # Предпросмотр реальной команды — то, что действительно будет запущено
        self.fmt_preview = QLineEdit()
        self.fmt_preview.setObjectName("CmdPreview")
        self.fmt_preview.setReadOnly(True)
        self.fmt_preview.setVisible(False)
        fmt_layout.addWidget(self.fmt_preview)

        self.format_btn = QPushButton(self.t("format_btn"))
        self.format_btn.setObjectName("DangerBtn")
        self.format_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.format_btn.clicked.connect(self._format_disk)
        fmt_layout.addWidget(self.format_btn)

        self.fs_combo.currentIndexChanged.connect(self._update_fmt_ui)
        self.format_label_input.textChanged.connect(self._update_fmt_ui)
        self.keep_uuid_cb.stateChanged.connect(self._update_fmt_ui)

        main_layout.addWidget(fmt_frame)

        # --- Foldout «Сетевые диски»: SMB/NFS как настоящие папки ---
        self.net_fold_btn = QPushButton()
        self.net_fold_btn.setObjectName("FoldoutBtn")
        self.net_fold_btn.setCheckable(True)
        self.net_fold_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.net_fold_btn.toggled.connect(self._toggle_net)
        main_layout.addWidget(self.net_fold_btn)

        self.net_frame = QFrame()
        self.net_frame.setObjectName("ProFrame")
        net_layout = QVBoxLayout(self.net_frame)
        net_layout.setContentsMargins(12, 10, 12, 10)
        net_layout.setSpacing(8)

        self.net_hint_lbl = QLabel(self.t("net_hint"))
        self.net_hint_lbl.setObjectName("FmtDesc")
        self.net_hint_lbl.setWordWrap(True)
        net_layout.addWidget(self.net_hint_lbl)

        self._net_body_widget = QWidget()
        self._net_body = QVBoxLayout(self._net_body_widget)
        self._net_body.setContentsMargins(0, 2, 0, 0)
        self._net_body.setSpacing(6)
        net_layout.addWidget(self._net_body_widget)

        self.net_add_btn = QPushButton(self.t("add_net"))
        self.net_add_btn.setObjectName("AddSourceBtn")
        self.net_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.net_add_btn.clicked.connect(self._net_add)
        net_layout.addWidget(self.net_add_btn)

        main_layout.addWidget(self.net_frame)
        self.net_frame.setVisible(False)
        self._update_net_fold_text()

        # --- Foldout «Расширенные»: базовое всегда на виду, разметка дисков
        # раскрывается только осознанным кликом ---
        self.pro_fold_btn = QPushButton()
        self.pro_fold_btn.setObjectName("FoldoutBtn")
        self.pro_fold_btn.setCheckable(True)
        self.pro_fold_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pro_fold_btn.toggled.connect(self._toggle_pro)
        main_layout.addWidget(self.pro_fold_btn)
        self._update_fold_text()

        # --- Профи-режим: разметка дисков (скрыт по умолчанию) ---
        self.pro_frame = QFrame()
        self.pro_frame.setObjectName("ProFrame")
        pro_layout = QVBoxLayout(self.pro_frame)
        pro_layout.setContentsMargins(12, 10, 12, 10)
        pro_layout.setSpacing(8)

        self.lbl_pro_section = QLabel(self.t("part_section"))
        self.lbl_pro_section.setObjectName("ProLabel")
        pro_layout.addWidget(self.lbl_pro_section)

        pro_disk_row = QHBoxLayout()
        self.pro_disk_combo = QComboBox()
        self.pro_disk_combo.setObjectName("SourceEdit")
        self.pro_disk_combo.setFixedHeight(30)
        self.pro_disk_combo.currentIndexChanged.connect(self._render_pro_disk)
        pro_disk_row.addWidget(self.pro_disk_combo, 1)

        self.pro_table_combo = QComboBox()
        self.pro_table_combo.setObjectName("SourceEdit")
        self.pro_table_combo.setFixedHeight(30)
        self.pro_table_combo.addItem("GPT", "gpt")
        self.pro_table_combo.addItem("MBR", "dos")
        pro_disk_row.addWidget(self.pro_table_combo)

        self.pro_mktable_btn = QPushButton(self.t("new_table"))
        self.pro_mktable_btn.setObjectName("DangerBtn")
        self.pro_mktable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pro_mktable_btn.clicked.connect(self._pro_mktable)
        pro_disk_row.addWidget(self.pro_mktable_btn)
        pro_layout.addLayout(pro_disk_row)

        self._pro_body_widget = QWidget()
        self._pro_body = QVBoxLayout(self._pro_body_widget)
        self._pro_body.setContentsMargins(0, 4, 0, 0)
        self._pro_body.setSpacing(6)
        pro_layout.addWidget(self._pro_body_widget)

        main_layout.addWidget(self.pro_frame)
        self.pro_frame.setVisible(False)
        main_layout.addSpacing(10)

        # --- Progress (fixed at bottom, outside scroll) ---
        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("ProgressFrame")
        self.progress_frame.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_frame)
        prog_layout.setContentsMargins(30, 10, 30, 10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        prog_layout.addWidget(self.progress_bar)

        self.prog_status_lbl = QLabel(self.t("applying"))
        self.prog_status_lbl.setObjectName("StatusLabel")
        self.prog_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prog_layout.addWidget(self.prog_status_lbl)

        outer_layout.addWidget(self.progress_frame)

        self._refresh_ui()

    # ------------------------------------------------------------------ data

    def _load_disks(self):
        current_dev = self.disk_combo.currentData()
        self.disk_combo.clear()
        self.partitions.clear()

        try:
            result = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,UUID,FSTYPE,FSVER,MOUNTPOINTS,SIZE,TYPE,LABEL,RM,TRAN"],
                capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            self._parse_lsblk(data.get("blockdevices", []))
        except Exception as e:
            self.info_lbl.setText(f"Error loading disks: {e}")

        if not self.partitions:
            self.disk_combo.addItem("No suitable partitions found", None)
            self._refresh_fstab_health()
            return

        for name, info in self.partitions.items():
            label = info.get("label") or self.t("no_label")
            fs_name = fs_display(info.get("fstype", ""), info.get("fsver") or "")
            display = f"[{label}]  /dev/{name}  —  {info['size']}  ({fs_name})"
            self.disk_combo.addItem(display, name)

        # Restore previous selection
        if current_dev:
            for i in range(self.disk_combo.count()):
                if self.disk_combo.itemData(i) == current_dev:
                    self.disk_combo.setCurrentIndex(i)
                    break
        self._refresh_fstab_health()

    def _parse_lsblk(self, devices, parent=None):
        for dev in devices:
            # Транспорт и признак removable известны у диска — наследуем разделам
            if parent is not None:
                if not dev.get("tran"):
                    dev["tran"] = parent.get("tran")
                dev["rm"] = dev.get("rm") or parent.get("rm")
            if dev.get("type") == "part" and dev.get("fstype") and dev.get("uuid"):
                # swap монтировать нечем, LUKS сначала нужно расшифровать
                if dev.get("fstype") not in ("swap", "crypto_LUKS"):
                    self.partitions[dev["name"]] = dev
            if "children" in dev:
                self._parse_lsblk(dev["children"], dev)

    @staticmethod
    def _is_external(info):
        return bool(info) and (info.get("tran") == "usb" or bool(info.get("rm")))

    def _selected_ids(self):
        try:
            pw = pwd.getpwnam(self.user_combo.currentText())
            return pw.pw_uid, pw.pw_gid
        except (KeyError, AttributeError):
            return 1000, 1000

    def _generate_default_opts(self, fstype, info=None):
        uid, gid = self._selected_ids()
        # Внешний диск без nofail блокирует загрузку, если его отключить
        nofail = ",nofail" if self._is_external(info) else ""
        if fstype in ["ntfs", "ntfs-3g", "vfat", "fat32", "exfat"]:
            return f"defaults,noatime,uid={uid},gid={gid},dmask=022,fmask=022{nofail}"
        elif fstype == "btrfs":
            return f"defaults,noatime,compress=zstd,autodefrag{nofail}"
        elif fstype in ["ext4", "ext3"]:
            return f"defaults,noatime{nofail}"
        return "defaults" + nofail

    # ------------------------------------------------------------------ fstab health

    def _build_fstab_health_section(self, main_layout):
        self._fstab_health_frame = QFrame()
        self._fstab_health_frame.setObjectName("FstabHealthFrame")
        health_layout = QVBoxLayout(self._fstab_health_frame)
        health_layout.setContentsMargins(12, 10, 12, 10)
        health_layout.setSpacing(6)

        self._fstab_health_title = QLabel(self.t("fstab_issues"))
        self._fstab_health_title.setObjectName("FstabHealthTitle")
        health_layout.addWidget(self._fstab_health_title)

        self._fstab_health_hint = QLabel(self.t("fstab_orphan_hint"))
        self._fstab_health_hint.setObjectName("FstabHealthHint")
        self._fstab_health_hint.setWordWrap(True)
        health_layout.addWidget(self._fstab_health_hint)

        self._fstab_health_body_widget = QWidget()
        self._fstab_health_body = QVBoxLayout(self._fstab_health_body_widget)
        self._fstab_health_body.setContentsMargins(0, 4, 0, 0)
        self._fstab_health_body.setSpacing(6)
        health_layout.addWidget(self._fstab_health_body_widget)

        main_layout.addWidget(self._fstab_health_frame)
        self._fstab_health_frame.setVisible(False)

    def _parse_fstab_entries(self):
        """Return list of (uuid, mountpoint, fstype, options) for UUID= entries in /etc/fstab."""
        entries = []
        try:
            if not os.path.exists("/etc/fstab"):
                return entries
            with open("/etc/fstab") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("#") or not stripped:
                        continue
                    if not stripped.startswith("UUID="):
                        continue
                    raw_parts = stripped.split()
                    if len(raw_parts) >= 6:
                        uuid = raw_parts[0][5:]
                        mount = " ".join(raw_parts[1:-4]).replace("\\040", " ")
                        fstype = raw_parts[-4]
                        options = raw_parts[-3]
                    elif len(raw_parts) >= 4:
                        uuid = raw_parts[0][5:]
                        mount = raw_parts[1].replace("\\040", " ")
                        fstype = raw_parts[2]
                        options = raw_parts[3]
                    else:
                        continue
                    if fstype == "swap":
                        continue
                    entries.append((uuid, mount, fstype, options))
        except Exception:
            pass
        return entries

    def _get_orphaned_fstab_entries(self):
        known_uuids = {info.get("uuid") for info in self.partitions.values() if info.get("uuid")}
        return [(u, m, f, o) for u, m, f, o in self._parse_fstab_entries() if u not in known_uuids]

    def _refresh_fstab_health(self):
        while self._fstab_health_body.count():
            item = self._fstab_health_body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        orphaned = self._get_orphaned_fstab_entries()
        self._fstab_health_frame.setVisible(bool(orphaned))
        if not orphaned:
            return

        for uuid, mountpoint, fstype, options in orphaned:
            entry_frame = QFrame()
            entry_frame.setObjectName("OrphanEntryFrame")
            entry_layout = QVBoxLayout(entry_frame)
            entry_layout.setContentsMargins(8, 6, 8, 6)
            entry_layout.setSpacing(4)

            warn_lbl = QLabel(f"⚠  {self.t('fstab_orphan_warn')}")
            warn_lbl.setObjectName("OrphanWarnLabel")
            entry_layout.addWidget(warn_lbl)

            short_uuid = uuid[:8] + "…" if len(uuid) > 8 else uuid
            info_lbl = QLabel(f"UUID: {short_uuid}   →   {mountpoint}   ({fstype})")
            info_lbl.setObjectName("OrphanInfoLabel")
            info_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info_lbl.setCursor(Qt.CursorShape.IBeamCursor)
            entry_layout.addWidget(info_lbl)

            btn_row = QHBoxLayout()
            btn_row.addStretch()

            if "nofail" not in options.split(","):
                nofail_btn = QPushButton(self.t("fstab_add_nofail"))
                nofail_btn.setObjectName("BrowseBtn")
                nofail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                nofail_btn.clicked.connect(
                    lambda _, u=uuid: self._run_backend(["--add-nofail", u],
                                                        f"Adding nofail to fstab entry {u[:8]}…"))
                btn_row.addWidget(nofail_btn)

            rm_btn = QPushButton(self.t("fstab_orphan_rm"))
            rm_btn.setObjectName("DangerBtn")
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.clicked.connect(
                lambda _, u=uuid: self._run_backend(["--rm-fstab", u],
                                                    f"Removing orphaned fstab entry {u[:8]}…"))
            btn_row.addWidget(rm_btn)

            entry_layout.addLayout(btn_row)
            self._fstab_health_body.addWidget(entry_frame)

    # ------------------------------------------------------------------ UI update

    def _on_disk_selected(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name or dev_name not in self.partitions:
            self.info_lbl.setText("")
            for btn in (self.mount_now_btn, self.umount_btn, self.format_btn, self.set_label_btn):
                btn.setEnabled(False)
            self._update_fmt_ui()
            return

        info = self.partitions[dev_name]
        uuid   = info.get("uuid", "N/A")
        fstype = info.get("fstype", "N/A")
        size   = info.get("size", "?")
        mounts = [m for m in info.get("mountpoints", []) if m]

        lines = [
            f"{self.t('uuid')}: {uuid}",
            f"{self.t('fstype')}: {fs_display(fstype, info.get('fsver') or '')}   {self.t('size')}: {size}",
        ]

        if mounts:
            line = f"{self.t('mounted_at')}: {mounts[0]}"
            try:
                usage = shutil.disk_usage(mounts[0])
                used_gb = usage.used / 1024**3
                free_gb = usage.free / 1024**3
                pct     = usage.used / usage.total * 100
                line += f"\n{self.t('disk_used')}: {used_gb:.1f} GB ({pct:.0f}%)  —  {self.t('disk_free')}: {free_gb:.1f} GB"
            except Exception:
                pass
            lines.append(line)
        else:
            lines.append(self.t("not_mounted"))

        if self._is_external(info):
            lines.append(self.t("external_badge"))
        if fstype in ("ntfs", "ntfs-3g"):
            lines.append(self.t("ntfs_driver_line").format(
                drv=disk_backend.ntfs_mount_type()))

        self.info_lbl.setText("\n".join(lines))

        # Button states based on mount status
        self.mount_now_btn.setEnabled(not mounts)
        self.umount_btn.setEnabled(bool(mounts))
        self.set_label_btn.setEnabled(True)
        self.format_btn.setEnabled(not mounts)
        if mounts:
            self.format_btn.setToolTip(self.t("fmt_mounted"))
        else:
            self.format_btn.setToolTip(self.t("tt_format"))

        # fstab state
        is_in_fstab = False
        fstab_line = ""
        try:
            if os.path.exists("/etc/fstab"):
                with open("/etc/fstab") as f:
                    for line in f:
                        if uuid in line:
                            is_in_fstab = True
                            fstab_line = line
                            break
        except Exception:
            pass

        self.opts_widget.set_fstype(fstype)

        if is_in_fstab:
            self.automount_btn.setText(self.t("disable_auto"))
            self._set_btn_state(self.automount_btn, "danger")
            # Parse fstab line carefully: device and options/dump/pass have no
            # spaces, but the mount point might (e.g. "Documents Photo and Video").
            # Work from both ends: parts[-1]=pass, parts[-2]=dump,
            # parts[-3]=options, parts[-4]=fstype, parts[0]=device,
            # everything in between is the mount point.
            raw_parts = fstab_line.strip().split()
            if len(raw_parts) >= 6:
                mount_point = " ".join(raw_parts[1:-4]).replace("\\040", " ")
                options = raw_parts[-3]
                self.mount_input.setText(mount_point)
                self.opts_widget.set_options(options)
            elif len(raw_parts) == 5:
                self.mount_input.setText(raw_parts[1].replace("\\040", " "))
                self.opts_widget.set_options(raw_parts[3])
            elif len(raw_parts) >= 4:
                self.mount_input.setText(raw_parts[1].replace("\\040", " "))
                self.opts_widget.set_options(raw_parts[3])
            elif mounts:
                self.mount_input.setText(mounts[0])
                self._last_gen_opts = self._generate_default_opts(fstype, info)
                self.opts_widget.set_options(self._last_gen_opts)
        else:
            self.automount_btn.setText(self.t("automount"))
            self._set_btn_state(self.automount_btn, "")
            label = info.get("label")
            self.mount_input.setText(f"/mnt/{label}" if label else f"/mnt/{dev_name}")
            self._last_gen_opts = self._generate_default_opts(fstype, info)
            self.opts_widget.set_options(self._last_gen_opts)

        self.save_fstab_btn.setVisible(is_in_fstab)

        # Pre-fill label input with current label
        self.label_input.setText(info.get("label") or "")

        self._update_fmt_ui()

    def _on_user_changed(self):
        if not getattr(self, "_last_gen_opts", None):
            return
        if self.opts_widget.get_options() != self._last_gen_opts:
            return
        dev = self.disk_combo.currentData()
        info = self.partitions.get(dev) if dev else None
        if info:
            self._last_gen_opts = self._generate_default_opts(
                info.get("fstype", ""), info)
            self.opts_widget.set_options(self._last_gen_opts)

    # ------------------------------------------------------------------ backend runner

    def _run_backend(self, args, status=None):
        for w in (self.automount_btn, self.save_fstab_btn, self.perms_btn,
                  self.mount_now_btn, self.umount_btn, self.format_btn,
                  self.set_label_btn, self.recursive_cb, self.user_combo, self.disk_combo):
            w.setEnabled(False)
        self.pro_frame.setEnabled(False)
        self.net_frame.setEnabled(False)
        self.prog_status_lbl.setText(status or self.t("applying"))
        self.progress_frame.setVisible(True)

        self.worker = DiskWorker(args)
        self.worker.finished.connect(self._on_worker_done)
        self.worker.start()

    def _on_worker_done(self, success, message):
        for w in (self.automount_btn, self.save_fstab_btn, self.perms_btn,
                  self.mount_now_btn, self.umount_btn, self.format_btn,
                  self.set_label_btn, self.recursive_cb, self.user_combo, self.disk_combo):
            w.setEnabled(True)
        self.progress_frame.setVisible(False)

        if success:
            box = QMessageBox(QMessageBox.Icon.Information, self.t("dlg_success"),
                              self.t("success"), parent=self)
            if message.strip():
                # Полный вывод mkfs и других утилит — по кнопке «Подробнее»
                box.setDetailedText(message)
            box.exec()
        else:
            QMessageBox.critical(self, self.t("dlg_error"), f"{self.t('err_elevate')}\n{message}")
        self.pro_frame.setEnabled(True)
        self.net_frame.setEnabled(True)
        self._load_disks()
        if self.pro_fold_btn.isChecked():
            self._load_pro_disks()
        if self.net_fold_btn.isChecked():
            self._load_net_shares()

    # ------------------------------------------------------------------ actions

    def _save_fstab(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name:
            return
        info    = self.partitions[dev_name]
        uuid    = info["uuid"]
        fstype  = info["fstype"]
        mount   = self.mount_input.text().strip()
        options = self.opts_widget.get_options()
        if not mount or not options:
            QMessageBox.warning(self, self.t("dlg_warning"), self.t("warn_empty_mount"))
            return
        self._run_backend(["--add-fstab", uuid, mount, fstype, options],
                          f"Saving fstab entry for {uuid[:8]}...")

    def _open_fstab(self):
        """Open /etc/fstab in a GUI text editor for manual inspection/editing —
        e.g. to spot and remove a duplicate UUID entry the app's own
        add/remove flow wouldn't normally produce but hand-editing might."""
        editors = ["kate", "gnome-text-editor", "gedit", "featherpad", "xed", "kwrite", "mousepad"]
        editor = next((e for e in editors if shutil.which(e)), None)
        try:
            if editor:
                env_pass = [f"{k}={os.environ[k]}" for k in
                            ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY") if os.environ.get(k)]
                subprocess.Popen(
                    ["pkexec", "env", *env_pass, editor, "/etc/fstab"],
                    start_new_session=True,
                )
                return
            for term in (["konsole", "-e"], ["xterm", "-e"], ["gnome-terminal", "--"]):
                if shutil.which(term[0]):
                    subprocess.Popen(
                        ["pkexec"] + term + ["nano", "/etc/fstab"],
                        start_new_session=True,
                    )
                    return
            QMessageBox.warning(self, self.t("dlg_warning"), self.t("no_editor_found"))
        except Exception as e:
            QMessageBox.critical(self, self.t("dlg_error"), str(e))

    def _toggle_automount(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name:
            return
        info = self.partitions[dev_name]
        uuid     = info["uuid"]
        fstype   = info["fstype"]
        mount    = self.mount_input.text().strip()
        options  = self.opts_widget.get_options()

        if self.t("disable_auto") in self.automount_btn.text():
            self._run_backend(["--rm-fstab", uuid], f"Removing {uuid} from fstab...")
        else:
            if not mount or not options:
                QMessageBox.warning(self, self.t("dlg_warning"), self.t("warn_empty_mount"))
                return
            self._run_backend(["--add-fstab", uuid, mount, fstype, options],
                              f"Adding {uuid} to fstab...")

    def _mount_now(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name:
            return
        mount = self.mount_input.text().strip()
        if not mount:
            QMessageBox.warning(self, self.t("dlg_warning"), self.t("warn_no_mount"))
            return
        self._run_backend(["--mount", dev_name, mount],
                          f"Mounting /dev/{dev_name} → {mount}...")

    def _umount_now(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name:
            return
        mounts = [m for m in self.partitions[dev_name].get("mountpoints", []) if m]
        if not mounts:
            return
        self._run_backend(["--umount", mounts[0]],
                          f"Unmounting {mounts[0]}...")

    def _fix_permissions(self):
        mount = self.mount_input.text().strip()
        if not mount:
            QMessageBox.warning(self, self.t("dlg_warning"), self.t("warn_no_mount"))
            return
        user = self.user_combo.currentText()
        args = ["--fix-perms", mount, user]
        if self.recursive_cb.isChecked():
            args.append("--recursive")
        self._run_backend(args, f"Setting owner {user} on {mount}...")

    def _set_label(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name:
            return
        label = self.label_input.text().strip()
        if not label:
            QMessageBox.warning(self, self.t("dlg_warning"), self.t("warn_no_label"))
            return
        fstype = self.partitions[dev_name].get("fstype", "")
        self._run_backend(["--set-label", dev_name, fstype, label],
                          f"Setting label '{label}' on /dev/{dev_name}...")

    # ---- format helpers ---------------------------------------------------

    FS_FAMILY = {"ext2": "ext", "ext3": "ext", "ext4": "ext",
                 "btrfs": "btrfs", "vfat": "fat", "fat32": "fat", "fat16": "fat"}

    def _validate_fmt_label(self, fstype, label):
        if not label:
            return True, ""
        limit = disk_backend.LABEL_LIMITS.get(fstype)
        if limit and len(label) > limit:
            return False, self.t("warn_label_len").format(fs=fstype, max=limit)
        if fstype in ("fat32", "fat16", "vfat", "exfat") \
                and not disk_backend.FAT_LABEL_RE.fullmatch(label):
            return False, self.t("warn_label_chars")
        return True, ""

    def _keep_uuid_available(self, info, new_fs):
        """UUID переносим только внутри одной семьи ФС — форматы UUID разные."""
        fam_old = self.FS_FAMILY.get(info.get("fstype", ""))
        fam_new = self.FS_FAMILY.get(new_fs)
        if not fam_old or fam_old != fam_new:
            return False
        uuid = info.get("uuid") or ""
        pattern = disk_backend.FAT_ID_RE if fam_new == "fat" else disk_backend.UUID_RE
        return bool(pattern.fullmatch(uuid))

    @staticmethod
    def _part_size_mib(dev_name):
        try:
            with open(f"/sys/class/block/{dev_name}/size") as f:
                return int(f.read()) * 512 // (1024 * 1024)
        except (OSError, ValueError):
            return None

    def _fmt_preview_text(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name or dev_name not in self.partitions:
            return ""
        fstype = self.fs_combo.currentData()
        label = self.format_label_input.text().strip() or None
        keep = None
        if not self.keep_uuid_cb.isHidden() and self.keep_uuid_cb.isChecked():
            keep = self.partitions[dev_name].get("uuid")
        try:
            cmd = disk_backend.build_mkfs_cmd(dev_name, fstype, label, keep)
        except ValueError:
            return ""
        return "$ " + shlex.join(cmd)

    def _update_fmt_ui(self):
        dev_name = self.disk_combo.currentData()
        info = self.partitions.get(dev_name) if dev_name else None
        fstype = self.fs_combo.currentData()

        self.fs_desc_lbl.setText(self.t(f"fs_desc_{fstype}"))

        can_keep = bool(info) and self._keep_uuid_available(info, fstype)
        if not can_keep and self.keep_uuid_cb.isChecked():
            self.keep_uuid_cb.setChecked(False)
        self.keep_uuid_cb.setVisible(can_keep)

        ok, err = self._validate_fmt_label(
            fstype, self.format_label_input.text().strip())
        # FAT16 физически не бывает больше 4 ГиБ — глушим кнопку заранее
        if ok and fstype == "fat16" and dev_name:
            size_mib = self._part_size_mib(dev_name)
            if size_mib and size_mib > disk_backend.FAT16_MAX_MIB:
                ok, err = False, self.t("warn_fat16_size")
        self.fmt_label_hint.setText(err)
        self.fmt_label_hint.setVisible(not ok)

        preview = self._fmt_preview_text()
        self.fmt_preview.setText(preview)
        self.fmt_preview.setVisible(bool(preview))

        mounts = [m for m in info.get("mountpoints", []) if m] if info else []
        self.format_btn.setEnabled(bool(info) and not mounts and ok)

    def _format_disk(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name or dev_name not in self.partitions:
            return
        info   = self.partitions[dev_name]
        fstype = self.fs_combo.currentData()
        label  = self.format_label_input.text().strip()
        uuid   = info.get("uuid", "")

        ok, err = self._validate_fmt_label(fstype, label)
        if not ok:
            QMessageBox.warning(self, self.t("dlg_warning"), err)
            return

        keep_uuid = None
        if not self.keep_uuid_cb.isHidden() and self.keep_uuid_cb.isChecked():
            keep_uuid = uuid

        is_in_fstab = any(u == uuid for u, _, _, _ in self._parse_fstab_entries())

        note = ""
        if is_in_fstab:
            note = "\n\n" + (self.t("fmt_keep_fstab_note") if keep_uuid
                             else self.t("fmt_rm_fstab_note"))

        dlg = FormatConfirmDialog(self, self.t, dev_name, info, fstype,
                                  self._fmt_preview_text(), note)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if is_in_fstab and uuid and not keep_uuid:
            args = ["--rm-fstab-and-format", uuid, dev_name, fstype]
        else:
            args = ["--format", dev_name, fstype]
        if label:
            args.append(label)
        if keep_uuid:
            args += ["--keep-uuid", keep_uuid]
        self._run_backend(args, f"Formatting /dev/{dev_name} as {fstype}...")

    # ------------------------------------------------------------------ pro mode

    def _update_fold_text(self):
        arrow = "▾" if self.pro_fold_btn.isChecked() else "▸"
        self.pro_fold_btn.setText(f"{arrow}  {self.t('pro_mode')}")

    def _toggle_pro(self):
        on = self.pro_fold_btn.isChecked()
        self._update_fold_text()
        self.pro_frame.setVisible(on)
        if on:
            self._load_pro_disks()

    @staticmethod
    def _human_size(sectors):
        b = float(sectors) * 512
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if b < 1024 or unit == "TiB":
                return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
            b /= 1024

    def _load_pro_disks(self):
        cur = self.pro_disk_combo.currentData()
        self.pro_disk_combo.blockSignals(True)
        self.pro_disk_combo.clear()
        self._pro_disks = {}
        try:
            result = subprocess.run(
                ["lsblk", "-J", "-o",
                 "NAME,TYPE,SIZE,MODEL,PTTYPE,FSTYPE,FSVER,LABEL,MOUNTPOINTS,PARTN,RM,TRAN"],
                capture_output=True, text=True, check=True)
            for d in json.loads(result.stdout).get("blockdevices", []):
                if d.get("type") != "disk":
                    continue
                if d["name"].startswith(("zram", "loop", "sr", "ram")):
                    continue
                self._pro_disks[d["name"]] = d
        except Exception:
            pass
        for name, d in self._pro_disks.items():
            model = (d.get("model") or "").strip()
            usb = "  USB" if (d.get("tran") == "usb" or d.get("rm")) else ""
            pt = (d.get("pttype") or "—").upper().replace("DOS", "MBR")
            self.pro_disk_combo.addItem(
                f"/dev/{name}  —  {d.get('size', '?')}  {model}  ({pt}){usb}", name)
        self.pro_disk_combo.blockSignals(False)
        if cur:
            idx = self.pro_disk_combo.findData(cur)
            if idx >= 0:
                self.pro_disk_combo.setCurrentIndex(idx)
        self._render_pro_disk()

    def _pro_regions(self, disk, children):
        """Разделы и свободные промежутки по данным sysfs (в секторах 512Б).
        Пересекающиеся диапазоны (extended/logical на MBR) схлопываются."""
        base = f"/sys/block/{disk}"
        try:
            with open(f"{base}/size") as f:
                total = int(f.read())
        except OSError:
            return []
        parts = []
        for c in children:
            try:
                with open(f"{base}/{c['name']}/start") as f:
                    start = int(f.read())
                with open(f"{base}/{c['name']}/size") as f:
                    size = int(f.read())
            except OSError:
                continue
            parts.append({"kind": "part", "start": start, "size": size, "info": c})
        parts.sort(key=lambda p: p["start"])

        MIN_GAP = 16384              # промежутки мельче 8 MiB не предлагаем
        first_usable = 2048          # выравнивание 1 MiB
        last_usable = total - 2048   # запас под резервный заголовок GPT
        regions, cursor = [], first_usable
        for p in parts:
            if p["start"] - cursor >= MIN_GAP:
                regions.append({"kind": "free", "start": cursor,
                                "size": p["start"] - cursor})
            regions.append(p)
            cursor = max(cursor, p["start"] + p["size"])
        if last_usable - cursor >= MIN_GAP:
            regions.append({"kind": "free", "start": cursor,
                            "size": last_usable - cursor})
        return regions

    def _render_pro_disk(self):
        while self._pro_body.count():
            item = self._pro_body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        disk = self.pro_disk_combo.currentData()
        d = self._pro_disks.get(disk) if disk else None
        if not d:
            return

        if not d.get("pttype"):
            hint = QLabel(self.t("no_pt"))
            hint.setObjectName("FstabHealthHint")
            hint.setWordWrap(True)
            self._pro_body.addWidget(hint)
            return

        for region in self._pro_regions(disk, d.get("children", [])):
            row = QFrame()
            row.setObjectName("PartRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 5, 8, 5)
            rl.setSpacing(8)

            if region["kind"] == "free":
                lbl = QLabel(f"◇  {self.t('free_space')}  —  "
                             f"{self._human_size(region['size'])}")
                lbl.setObjectName("FreeLabel")
                rl.addWidget(lbl, 1)
                btn = QPushButton(self.t("create_part"))
                btn.setObjectName("AddSourceBtn")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(
                    lambda _, dk=disk, s=region["start"], sz=region["size"]:
                        self._pro_create(dk, s, sz))
                rl.addWidget(btn)
                self._pro_body.addWidget(row)
                continue

            c = region["info"]
            name = c["name"]
            partn = c.get("partn")
            fstype = c.get("fstype") or ""
            fs = fs_display(fstype, c.get("fsver") or "") if fstype else self.t("fs_none")
            mounts = [m for m in c.get("mountpoints", []) if m]

            text = f"◆  /dev/{name}  —  {self._human_size(region['size'])}  —  {fs}"
            if c.get("label"):
                text += f"  [{c['label']}]"
            lbl = QLabel(text)
            lbl.setObjectName("PartLabel")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rl.addWidget(lbl, 1)

            if mounts:
                m_lbl = QLabel(f"{self.t('mounted_at')}: {mounts[0]}")
                m_lbl.setObjectName("OptionsSubLabel")
                rl.addWidget(m_lbl)
            elif partn is not None:
                rz = QPushButton(self.t("resize_part"))
                rz.setObjectName("BrowseBtn")
                rz.setCursor(Qt.CursorShape.PointingHandCursor)
                if fstype in disk_backend.RESIZE_UNSUPPORTED or fstype == "swap":
                    rz.setEnabled(False)
                    rz.setToolTip(self.t("resize_na"))
                else:
                    rz.clicked.connect(
                        lambda _, dk=disk, n=partn, nm=name, sz=region["size"]:
                            self._pro_resize(dk, n, nm, sz))
                rl.addWidget(rz)

                rm = QPushButton(self.t("delete_part"))
                rm.setObjectName("DangerBtn")
                rm.setCursor(Qt.CursorShape.PointingHandCursor)
                rm.clicked.connect(
                    lambda _, dk=disk, n=partn, nm=name: self._pro_delete(dk, n, nm))
                rl.addWidget(rm)

            self._pro_body.addWidget(row)

    # -- операции разметки --------------------------------------------------

    def _pro_mktable(self):
        disk = self.pro_disk_combo.currentData()
        if not disk:
            return
        table = self.pro_table_combo.currentData()
        table_name = "GPT" if table == "gpt" else "MBR"
        d = self._pro_disks.get(disk, {})
        body = self.t("confirm_new_table").format(disk=disk, type=table_name)
        info_line = f"/dev/{disk}  —  {d.get('size', '?')}  {(d.get('model') or '').strip()}"
        cmd = f"$ echo 'label: {table}' | sfdisk --wipe always /dev/{disk}"
        dlg = ActionConfirmDialog(self, self.t, body, info_line, cmd,
                                  confirm_name=disk, ok_text=self.t("new_table"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_backend(["--mktable", disk, table],
                              f"Creating {table_name} table on /dev/{disk}...")

    def _pro_create(self, disk, start_sec, size_sec):
        mib = 1024 * 1024
        start_mib = (start_sec * 512 + mib - 1) // mib
        max_mib = (start_sec + size_sec) * 512 // mib - start_mib
        if max_mib < 8:
            return

        dlg = QDialog(self)
        dlg.setObjectName("FmtConfirm")
        dlg.setWindowTitle(self.t("create_part"))
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        head = QLabel(f"{self.t('create_part')}  —  /dev/{disk}")
        head.setObjectName("ProLabel")
        lay.addWidget(head)

        size_row = QHBoxLayout()
        size_lbl = QLabel(self.t("new_size"))
        size_lbl.setObjectName("DlgText")
        size_row.addWidget(size_lbl)
        spin = QDoubleSpinBox()
        spin.setObjectName("SmallEdit")
        spin.setSuffix(" GiB")
        spin.setDecimals(2)
        spin.setRange(0.01, max_mib / 1024)
        spin.setValue(max_mib / 1024)
        size_row.addWidget(spin, 1)
        lay.addLayout(size_row)

        fs_row = QHBoxLayout()
        fs_lbl = QLabel(self.t("new_fs"))
        fs_lbl.setObjectName("DlgText")
        fs_row.addWidget(fs_lbl)
        fs_combo = QComboBox()
        fs_combo.setObjectName("SourceEdit")
        for fs_value in ("ext4", "btrfs", "ntfs", "exfat", "fat32", "fat16"):
            fs_combo.addItem(fs_display(fs_value), fs_value)
        fs_combo.addItem(self.t("fs_none"), "none")
        fs_row.addWidget(fs_combo, 1)
        lay.addLayout(fs_row)

        label_edit = QLineEdit()
        label_edit.setObjectName("DestEdit")
        label_edit.setPlaceholderText(self.t("ph_label"))
        lay.addWidget(label_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(self.t("cancel"))
        cancel_btn.setObjectName("BrowseBtn")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton(self.t("create_part"))
        ok_btn.setObjectName("AddSourceBtn")
        ok_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        size_mib = min(max_mib, max(8, int(round(spin.value() * 1024))))
        fs_value = fs_combo.currentData()
        label = label_edit.text().strip()
        if fs_value == "fat16" and size_mib > disk_backend.FAT16_MAX_MIB:
            QMessageBox.warning(self, self.t("dlg_warning"),
                                self.t("warn_fat16_size"))
            return
        if label and fs_value != "none":
            ok, err = self._validate_fmt_label(fs_value, label)
            if not ok:
                QMessageBox.warning(self, self.t("dlg_warning"), err)
                return
        args = ["--mkpart", disk, str(start_mib), str(size_mib), fs_value]
        if label and fs_value != "none":
            args.append(label)
        self._run_backend(args, f"Creating {size_mib} MiB partition on /dev/{disk}...")

    def _pro_delete(self, disk, partn, node):
        c = None
        for child in self._pro_disks.get(disk, {}).get("children", []):
            if child["name"] == node:
                c = child
                break
        body = self.t("confirm_del_part").format(dev=node)
        info_parts = [f"/dev/{node}"]
        if c:
            fstype = c.get("fstype") or ""
            info_parts.append(fs_display(fstype, c.get("fsver") or "")
                              if fstype else self.t("fs_none"))
            if c.get("label"):
                info_parts.append(c["label"])
        cmd = f"$ sfdisk --delete /dev/{disk} {partn}"
        dlg = ActionConfirmDialog(self, self.t, body, "  —  ".join(info_parts), cmd,
                                  confirm_name=node, ok_text=self.t("delete_part"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_backend(["--rmpart", disk, str(partn)],
                              f"Deleting /dev/{node}...")

    def _resize_cmds(self, fstype, node, disk, partn, new_mib, grow):
        dev = f"/dev/{node}"
        sf = f"$ echo ',{new_mib}MiB' | sfdisk -N {partn} /dev/{disk}"
        if fstype in ("ext2", "ext3", "ext4"):
            fs_cmds = [f"$ e2fsck -f -y {dev}",
                       f"$ resize2fs {dev}" + ("" if grow else f" {new_mib}M")]
        elif fstype == "ntfs":
            fs_cmds = [f"$ ntfsresize -f {dev}" if grow
                       else f"$ ntfsresize -f -s {new_mib * 1024 * 1024} {dev}"]
        elif fstype == "btrfs":
            arg = "max" if grow else str(new_mib * 1024 * 1024)
            fs_cmds = [f"$ btrfs filesystem resize {arg} <mount>"]
        else:
            fs_cmds = []
        order = [sf] + fs_cmds if grow else fs_cmds + [sf]
        return "\n".join(order)

    def _pro_resize(self, disk, partn, node, cur_size_sec):
        mib = 1024 * 1024
        cur_mib = cur_size_sec * 512 // mib

        # предел роста — свободный промежуток сразу после раздела
        extra_mib = 0
        regions = self._pro_regions(disk, self._pro_disks.get(disk, {}).get("children", []))
        for i, r in enumerate(regions):
            if r["kind"] == "part" and r["info"]["name"] == node:
                if i + 1 < len(regions) and regions[i + 1]["kind"] == "free":
                    extra_mib = regions[i + 1]["size"] * 512 // mib
                break

        c = next((ch for ch in self._pro_disks.get(disk, {}).get("children", [])
                  if ch["name"] == node), {})
        fstype = c.get("fstype") or ""

        dlg = QDialog(self)
        dlg.setObjectName("FmtConfirm")
        dlg.setWindowTitle(self.t("resize_part"))
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        head = QLabel(f"{self.t('resize_part')}  —  /dev/{node}")
        head.setObjectName("ProLabel")
        lay.addWidget(head)
        cur_lbl = QLabel(f"{self.t('size')}: {self._human_size(cur_size_sec)}")
        cur_lbl.setObjectName("DlgText")
        lay.addWidget(cur_lbl)
        size_row = QHBoxLayout()
        size_lbl = QLabel(self.t("new_size"))
        size_lbl.setObjectName("DlgText")
        size_row.addWidget(size_lbl)
        spin = QDoubleSpinBox()
        spin.setObjectName("SmallEdit")
        spin.setSuffix(" GiB")
        spin.setDecimals(2)
        spin.setRange(0.05, (cur_mib + extra_mib) / 1024)
        spin.setValue(cur_mib / 1024)
        size_row.addWidget(spin, 1)
        lay.addLayout(size_row)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(self.t("cancel"))
        cancel_btn.setObjectName("BrowseBtn")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton(self.t("resize_part"))
        ok_btn.setObjectName("AddSourceBtn")
        ok_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_mib = int(round(spin.value() * 1024))
        if new_mib == cur_mib:
            return
        grow = new_mib > cur_mib

        human_new = f"{new_mib / 1024:.2f} GiB"
        body = self.t("confirm_resize").format(dev=node, size=human_new)
        if not grow:
            body += self.t("shrink_warn")
        cmd = self._resize_cmds(fstype, node, disk, partn, new_mib, grow)
        dlg2 = ActionConfirmDialog(self, self.t, body,
                                   f"/dev/{node}: {self._human_size(cur_size_sec)} → {human_new}",
                                   cmd,
                                   confirm_name=None if grow else node,
                                   ok_text=self.t("resize_part"))
        if dlg2.exec() == QDialog.DialogCode.Accepted:
            self._run_backend(["--resizepart", disk, str(partn), str(new_mib)],
                              f"Resizing /dev/{node} to {human_new}...")

    # ------------------------------------------------------------------ network drives

    def _update_net_fold_text(self):
        arrow = "▾" if self.net_fold_btn.isChecked() else "▸"
        self.net_fold_btn.setText(f"{arrow}  {self.t('net_section')}")

    def _toggle_net(self):
        on = self.net_fold_btn.isChecked()
        self._update_net_fold_text()
        self.net_frame.setVisible(on)
        if on:
            self._load_net_shares()

    def _parse_net_fstab(self):
        """(источник, точка, тип) для cifs/nfs-записей fstab."""
        shares = []
        try:
            with open("/etc/fstab") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4 and not line.strip().startswith("#") \
                            and parts[2] in ("cifs", "nfs", "nfs4", "davfs", "fuse.sshfs"):
                        shares.append((parts[0].replace("\\040", " "),
                                       parts[1].replace("\\040", " "),
                                       parts[2]))
        except OSError:
            pass
        return shares

    @staticmethod
    def _net_is_mounted(mountpoint):
        r = subprocess.run(["findmnt", "-no", "FSTYPE", mountpoint],
                           capture_output=True, text=True)
        types = [t for t in r.stdout.split() if t and t != "autofs"]
        return bool(types)

    def _load_net_shares(self):
        while self._net_body.count():
            item = self._net_body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for source, mount, fstype in self._parse_net_fstab():
            row = QFrame()
            row.setObjectName("PartRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 5, 8, 5)
            rl.setSpacing(8)

            proto = {"davfs": "WebDAV", "fuse.sshfs": "SSH"}.get(
                fstype, "NFS" if fstype.startswith("nfs") else "SMB")
            lbl = QLabel(f"🖧  {proto}  {source}  →  {mount}")
            lbl.setObjectName("PartLabel")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rl.addWidget(lbl, 1)

            mounted = self._net_is_mounted(mount)
            status = QLabel(self.t("net_connected") if mounted
                            else self.t("net_not_conn"))
            status.setObjectName("FreeLabel" if mounted else "OptionsSubLabel")
            rl.addWidget(status)

            if mounted:
                un = QPushButton(self.t("umount"))
                un.setObjectName("BrowseBtn")
                un.setCursor(Qt.CursorShape.PointingHandCursor)
                un.clicked.connect(
                    lambda _, m=mount: self._run_backend(
                        ["--umount", m], f"Unmounting {m}..."))
                rl.addWidget(un)
            else:
                co = QPushButton(self.t("connect"))
                co.setObjectName("BrowseBtn")
                co.setCursor(Qt.CursorShape.PointingHandCursor)
                co.clicked.connect(
                    lambda _, m=mount: self._run_backend(
                        ["--mount-path", m], f"Mounting {m}..."))
                rl.addWidget(co)

            rm = QPushButton(self.t("delete_part"))
            rm.setObjectName("DangerBtn")
            rm.setCursor(Qt.CursorShape.PointingHandCursor)
            rm.clicked.connect(
                lambda _, s=source, m=mount: self._net_remove(s, m))
            rl.addWidget(rm)

            self._net_body.addWidget(row)

    def _net_remove(self, source, mount):
        body = self.t("confirm_rm_net").format(src=source)
        dlg = ActionConfirmDialog(self, self.t, body,
                                  f"{source}  →  {mount}", "",
                                  confirm_name=None,
                                  ok_text=self.t("delete_part"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_backend(["--rm-net", mount],
                              f"Removing network drive {mount}...")

    @staticmethod
    def _write_pass_file(password):
        """Пароль уезжает в бэкенд через файл 0600: в аргументах командной
        строки он был бы виден всем в списке процессов."""
        pass_dir = f"/run/user/{os.getuid()}"
        if not os.path.isdir(pass_dir):
            pass_dir = os.path.expanduser("~/.cache")
            os.makedirs(pass_dir, exist_ok=True)
        pass_file = os.path.join(pass_dir, f"eq-net-pass-{os.getpid()}")
        fd = os.open(pass_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(password)
        return pass_file

    def _net_add(self):
        dlg = QDialog(self)
        dlg.setObjectName("FmtConfirm")
        dlg.setWindowTitle(self.t("add_net"))
        dlg.setModal(True)
        dlg.setMinimumWidth(440)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        head = QLabel(self.t("add_net"))
        head.setObjectName("ProLabel")
        lay.addWidget(head)

        def field(label_key, placeholder=""):
            lbl = QLabel(self.t(label_key))
            lbl.setObjectName("DlgText")
            lay.addWidget(lbl)
            e = QLineEdit()
            e.setObjectName("DestEdit")
            e.setPlaceholderText(placeholder)
            lay.addWidget(e)
            return e

        type_combo = QComboBox()
        type_combo.setObjectName("SourceEdit")
        type_combo.addItem("SMB (Windows / NAS)", "smb")
        type_combo.addItem("NFS", "nfs")
        type_combo.addItem("WebDAV (Nextcloud, ownCloud…)", "dav")
        type_combo.addItem("SSH (SFTP)", "ssh")
        lay.addWidget(type_combo)

        server_edit = field("server", "192.168.1.10 / mynas.local")
        share_edit = field("net_share", "Media")
        mount_edit = field("mount_point", "/mnt/NAS")

        guest_cb = SwitchToggle(self.t("guest_access"))
        lay.addWidget(guest_cb)
        user_edit = field("username", "")
        pass_edit = field("password", "")
        pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        default_key = ""
        for k in ("id_ed25519", "id_rsa"):
            p = os.path.expanduser(f"~/.ssh/{k}")
            if os.path.isfile(p):
                default_key = p
                break
        key_edit = field("ssh_key", os.path.expanduser("~/.ssh/id_ed25519"))
        key_edit.setText(default_key)

        def sync_fields():
            kind = type_combo.currentData()
            is_smb, is_dav, is_ssh = kind == "smb", kind == "dav", kind == "ssh"
            share_edit.setVisible(not is_dav)   # у WebDAV путь уже в адресе
            guest_cb.setVisible(is_smb)
            need_creds = is_dav or (is_smb and not guest_cb.isChecked())
            user_edit.setVisible(need_creds)
            pass_edit.setVisible(need_creds)
            key_edit.setVisible(is_ssh)
            if is_dav:
                server_edit.setPlaceholderText(
                    "https://cloud.example.com/remote.php/webdav")
            elif is_ssh:
                server_edit.setPlaceholderText("user@server")
            else:
                server_edit.setPlaceholderText("192.168.1.10 / mynas.local")
            share_edit.setPlaceholderText(
                "Media" if is_smb else ("/home/user" if is_ssh else "/export/data"))
        type_combo.currentIndexChanged.connect(sync_fields)
        guest_cb.stateChanged.connect(sync_fields)
        sync_fields()

        # авто-точка монтирования из имени шары / адреса облака
        def auto_mount():
            if type_combo.currentData() == "dav":
                m = re.search(r"://([^/:]+)", server_edit.text().strip())
                leaf = m.group(1).split(".")[0] if m else ""
            else:
                leaf = share_edit.text().strip().strip("/").split("/")[-1]
            if leaf and (not mount_edit.text().strip()
                         or mount_edit.text().startswith("/mnt/")):
                mount_edit.setText(f"/mnt/{leaf}")
        share_edit.textChanged.connect(auto_mount)
        server_edit.textChanged.connect(auto_mount)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(self.t("cancel"))
        cancel_btn.setObjectName("BrowseBtn")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton(self.t("add_net"))
        ok_btn.setObjectName("AddSourceBtn")
        ok_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        server = server_edit.text().strip()
        share = share_edit.text().strip().strip("/")
        mount = mount_edit.text().strip()
        kind = type_combo.currentData()
        if not server or not mount or (kind != "dav" and not share):
            QMessageBox.warning(self, self.t("dlg_warning"),
                                self.t("warn_net_fields"))
            return

        if kind == "dav":
            user = user_edit.text().strip()
            password = pass_edit.text()
            if not user or not password:
                QMessageBox.warning(self, self.t("dlg_warning"),
                                    self.t("warn_net_fields"))
                return
            uid, gid = self._selected_ids()
            pass_file = self._write_pass_file(password)
            self._run_backend(["--add-net-dav", server, mount,
                               "--uid", str(uid), "--gid", str(gid),
                               "--user", user, "--password-file", pass_file],
                              f"Adding WebDAV {server}...")
            return

        if kind == "ssh":
            key = key_edit.text().strip()
            if not key:
                QMessageBox.warning(self, self.t("dlg_warning"),
                                    self.t("warn_net_fields"))
                return
            uid, gid = self._selected_ids()
            src_spec = server if ":" in server else f"{server}:/{share}"
            self._run_backend(["--add-net-ssh", src_spec, mount,
                               "--uid", str(uid), "--gid", str(gid),
                               "--key", key],
                              f"Adding SSH drive {src_spec}...")
            return

        if kind == "nfs":
            self._run_backend(["--add-net-nfs", f"{server}:/{share}", mount],
                              f"Adding NFS share {server}:/{share}...")
            return

        uid, gid = self._selected_ids()
        args = ["--add-net-smb", server, share, mount,
                "--uid", str(uid), "--gid", str(gid)]
        if guest_cb.isChecked():
            args.append("--guest")
        else:
            user = user_edit.text().strip()
            password = pass_edit.text()
            if not user or not password:
                QMessageBox.warning(self, self.t("dlg_warning"),
                                    self.t("warn_net_fields"))
                return
            args += ["--user", user,
                     "--password-file", self._write_pass_file(password)]
        self._run_backend(args, f"Adding SMB share //{server}/{share}...")


def main():
    app = QApplication(sys.argv)
    kit_qt.ThemeManager(app)  # общая тема Equestria OS: следит за переключателем персонажей
    # Wayland: link window to the .desktop file so the compositor uses its icon
    app.setDesktopFileName("equestria-os-disk-manager")
    icon_path = os.path.join(os.path.dirname(__file__), "equestria-os-disk-manager.png")
    app.setWindowIcon(QIcon(icon_path))
    win = DiskManagerApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
