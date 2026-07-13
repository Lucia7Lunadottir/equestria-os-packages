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

import privilege
import disk_backend  # только константы и build_mkfs_cmd для предпросмотра


class SwitchToggle(QAbstractButton):
    """Переключатель-пилюля с бегунком: фон плавно заливается акцентным
    цветом, бегунок едет вправо. Рисуется вручную — QSS такое не умеет."""
    stateChanged = pyqtSignal(int)

    TRACK_W, TRACK_H, KNOB_M = 34, 18, 3
    C_TRACK_OFF = (69, 71, 90)
    C_TRACK_ON  = (245, 194, 231)
    C_KNOB_OFF  = (205, 214, 244)
    C_KNOB_ON   = (30, 30, 46)
    C_TEXT_OFF  = (147, 153, 178)
    C_TEXT_ON   = (203, 166, 247)

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
    def _blend(a, b, t):
        return QColor(*(round(x + (y - x) * t) for x, y in zip(a, b)))

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
        p.setBrush(self._blend(self.C_TRACK_OFF, self.C_TRACK_ON, t))
        p.drawRoundedRect(QRectF(0, ty, self.TRACK_W, self.TRACK_H),
                          self.TRACK_H / 2, self.TRACK_H / 2)

        kd = self.TRACK_H - 2 * self.KNOB_M
        kx = self.KNOB_M + t * (self.TRACK_W - kd - 2 * self.KNOB_M)
        p.setBrush(self._blend(self.C_KNOB_OFF, self.C_KNOB_ON, t))
        p.drawEllipse(QRectF(kx, ty + self.KNOB_M, kd, kd))

        p.setPen(self._blend(self.C_TEXT_OFF, self.C_TEXT_ON, t))
        p.drawText(QRectF(self.TRACK_W + 8, 0,
                          self.width() - self.TRACK_W - 8, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._label)


class FstabOptionsWidget(QFrame):
    """User-friendly fstab options editor."""

    OPTS_TIPS = {
        "noatime":    {"en": "Don't update file access time — improves disk performance",
                       "ru": "Не обновлять время последнего доступа — ускоряет работу диска"},
        "nofail":     {"en": "Don't fail boot if the drive is missing or unavailable",
                       "ru": "Не прерывать загрузку системы, если диск недоступен"},
        "ro":         {"en": "Mount read-only — no writes allowed",
                       "ru": "Монтировать только для чтения — запись запрещена"},
        "exec":       {"en": "Explicitly allow executing binaries.\n"
                             "Use this to override 'noexec' from an old fstab entry.\n"
                             "Not needed if noexec is not set — exec is the default.",
                       "ru": "Явно разрешить запуск исполняемых файлов.\n"
                             "Используй чтобы перебить 'noexec' из старой записи fstab.\n"
                             "Не нужен если noexec не установлен — exec включён по умолчанию."},
        "noexec":     {"en": "Prevent execution of any binaries on this partition.\n"
                             "⚠ Don't enable for Steam game drives!",
                       "ru": "Запретить запуск исполняемых файлов с этого раздела.\n"
                             "⚠ Не включать для дисков с играми Steam!"},
        "noauto":     {"en": "Don't auto-mount when 'mount -a' runs — mount manually only",
                       "ru": "Не монтировать при 'mount -a' — только вручную"},
        "uid":        {"en": "User ID that owns all files on this drive.\n"
                             "Find yours in terminal: id -u",
                       "ru": "UID пользователя-владельца всех файлов на диске.\n"
                             "Узнать в терминале: id -u"},
        "gid":        {"en": "Group ID that owns all files on this drive.\n"
                             "Find yours in terminal: id -g",
                       "ru": "GID группы-владельца всех файлов на диске.\n"
                             "Узнать в терминале: id -g"},
        "dmask":      {"en": "Permission mask for directories.\n"
                             "022  →  rwxr-xr-x  (recommended)",
                       "ru": "Маска прав доступа для папок.\n"
                             "022  →  rwxr-xr-x  (рекомендуется)"},
        "fmask":      {"en": "Permission mask for files.\n"
                             "022  →  rwxr-xr-x  ← use this for Steam/games\n"
                             "133  →  rw-r--r--  ← use this for documents only",
                       "ru": "Маска прав доступа для файлов.\n"
                             "022  →  rwxr-xr-x  ← для Steam/игр\n"
                             "133  →  rw-r--r--  ← только для документов"},
        "winnames":   {"en": "Restrict filenames to Windows-compatible characters.\n"
                             "⚠ DO NOT use for Steam game libraries — breaks game files!",
                       "ru": "Ограничить имена файлов символами, совместимыми с Windows.\n"
                             "⚠ НЕ использовать для библиотек Steam — ломает файлы игр!"},
        "compress":   {"en": "Transparent compression algorithm.\n"
                             "zstd = best speed/ratio on modern CPUs",
                       "ru": "Алгоритм прозрачного сжатия.\n"
                             "zstd = лучшее соотношение скорости и сжатия"},
        "autodefrag": {"en": "Automatic background defragmentation",
                       "ru": "Автоматическая дефрагментация в фоновом режиме"},
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


LANGS = ["en", "ru", "de", "fr", "es", "pt", "pl", "uk", "zh", "ja"]
STRINGS = {
    "title":        {"en": "Equestria OS Disk Manager",           "ru": "Equestria OS: Менеджер Дисков",      "de": "Equestria OS Festplatten-Manager",        "fr": "Equestria OS Gestionnaire de disques",    "es": "Equestria OS Gestor de discos",          "pt": "Equestria OS Gerenciador de discos",     "pl": "Equestria OS Menedżer dysków",           "uk": "Equestria OS Менеджер дисків",           "zh": "Equestria OS 磁盘管理器",                "ja": "Equestria OS ディスクマネージャー"},
    "select_disk":  {"en": "Select Partition",                    "ru": "Выберите раздел",                    "de": "Partition auswählen",                    "fr": "Sélectionner une partition",             "es": "Seleccionar partición",                  "pt": "Selecionar partição",                    "pl": "Wybierz partycję",                       "uk": "Виберіть розділ",                        "zh": "选择分区",                               "ja": "パーティションを選択"},
    "mount_point":  {"en": "Mount Point",                         "ru": "Точка монтирования",                 "de": "Einhängepunkt",                          "fr": "Point de montage",                       "es": "Punto de montaje",                       "pt": "Ponto de montagem",                      "pl": "Punkt montowania",                       "uk": "Точка монтування",                       "zh": "挂载点",                                 "ja": "マウントポイント"},
    "fstab_opts":   {"en": "fstab Options",                       "ru": "Опции fstab",                        "de": "fstab-Optionen",                         "fr": "Options fstab",                          "es": "Opciones fstab",                         "pt": "Opções fstab",                           "pl": "Opcje fstab",                            "uk": "Параметри fstab",                        "zh": "fstab 选项",                             "ja": "fstab オプション"},
    "select_user":  {"en": "Target User",                         "ru": "Владелец диска",                     "de": "Zielbenutzer",                           "fr": "Utilisateur cible",                      "es": "Usuario destino",                        "pt": "Usuário destino",                        "pl": "Użytkownik docelowy",                    "uk": "Цільовий користувач",                    "zh": "目标用户",                               "ja": "対象ユーザー"},
    "uuid":         {"en": "UUID",                                "ru": "UUID",                               "de": "UUID",                                   "fr": "UUID",                                   "es": "UUID",                                   "pt": "UUID",                                   "pl": "UUID",                                   "uk": "UUID",                                   "zh": "UUID",                                   "ja": "UUID"},
    "fstype":       {"en": "File System",                         "ru": "Файловая система",                   "de": "Dateisystem",                            "fr": "Système de fichiers",                    "es": "Sistema de archivos",                    "pt": "Sistema de arquivos",                    "pl": "System plików",                          "uk": "Файлова система",                        "zh": "文件系统",                               "ja": "ファイルシステム"},
    "size":         {"en": "Size",                                "ru": "Размер",                             "de": "Größe",                                  "fr": "Taille",                                 "es": "Tamaño",                                 "pt": "Tamanho",                                "pl": "Rozmiar",                                "uk": "Розмір",                                 "zh": "大小",                                   "ja": "サイズ"},
    "automount":    {"en": "Enable Automount",                    "ru": "Включить автомонтирование",          "de": "Automount aktivieren",                   "fr": "Activer le montage auto",                "es": "Activar automontaje",                    "pt": "Ativar montagem automática",             "pl": "Włącz automontowanie",                   "uk": "Увімкнути автомонтування",               "zh": "启用自动挂载",                           "ja": "自動マウントを有効化"},
    "disable_auto": {"en": "Disable Automount",                   "ru": "Отключить автомонтирование",         "de": "Automount deaktivieren",                 "fr": "Désactiver le montage auto",             "es": "Desactivar automontaje",                 "pt": "Desativar montagem automática",          "pl": "Wyłącz automontowanie",                  "uk": "Вимкнути автомонтування",                "zh": "禁用自动挂载",                           "ja": "自動マウントを無効化"},
    "fix_perms":    {"en": "Take Ownership",                      "ru": "Установить владельца и права",       "de": "Eigentümerschaft übernehmen",            "fr": "Prendre possession",                     "es": "Tomar propiedad",                        "pt": "Assumir propriedade",                    "pl": "Przejmij własność",                      "uk": "Взяти у власність",                      "zh": "设置所有权",                             "ja": "所有権を取得"},
    "recursive":    {"en": "Recursive (includes files inside)",   "ru": "Рекурсивно (включая все файлы)",     "de": "Rekursiv (alle Dateien eingeschlossen)", "fr": "Récursif (tous les fichiers inclus)",    "es": "Recursivo (todos los archivos)",         "pt": "Recursivo (todos os arquivos)",          "pl": "Rekurencyjnie (wszystkie pliki)",        "uk": "Рекурсивно (всі файли)",                 "zh": "递归（包括所有文件）",                   "ja": "再帰的（全ファイル含む）"},
    "ph_mount":     {"en": "e.g., /mnt/Work",                     "ru": "напр., /mnt/Work",                   "de": "z.B. /mnt/Work",                         "fr": "ex. /mnt/Work",                          "es": "p.ej. /mnt/Work",                        "pt": "ex. /mnt/Work",                          "pl": "np. /mnt/Work",                          "uk": "напр. /mnt/Work",                        "zh": "例如 /mnt/Work",                         "ja": "例: /mnt/Work"},
    "ph_opts":      {"en": "e.g., defaults,noatime",              "ru": "напр., defaults,noatime",            "de": "z.B. defaults,noatime",                  "fr": "ex. defaults,noatime",                   "es": "p.ej. defaults,noatime",                 "pt": "ex. defaults,noatime",                   "pl": "np. defaults,noatime",                   "uk": "напр. defaults,noatime",                 "zh": "例如 defaults,noatime",                 "ja": "例: defaults,noatime"},
    "ph_label":     {"en": "e.g., Work",                          "ru": "напр., Work",                        "de": "z.B. Work",                              "fr": "ex. Work",                               "es": "p.ej. Work",                             "pt": "ex. Work",                               "pl": "np. Work",                               "uk": "напр. Work",                             "zh": "例如 Work",                              "ja": "例: Work"},
    "refresh":      {"en": "Refresh disk list",                   "ru": "Обновить список дисков",             "de": "Festplattenliste aktualisieren",         "fr": "Actualiser la liste des disques",        "es": "Actualizar lista de discos",             "pt": "Atualizar lista de discos",              "pl": "Odśwież listę dysków",                   "uk": "Оновити список дисків",                  "zh": "刷新磁盘列表",                           "ja": "ディスク一覧を更新"},
    "success":      {"en": "Operation successful!",               "ru": "Операция выполнена успешно!",        "de": "Vorgang erfolgreich!",                   "fr": "Opération réussie !",                    "es": "¡Operación exitosa!",                    "pt": "Operação bem-sucedida!",                 "pl": "Operacja zakończona pomyślnie!",         "uk": "Операцію виконано успішно!",             "zh": "操作成功！",                             "ja": "操作が完了しました！"},
    "err_elevate":  {"en": "Failed to get root access.",          "ru": "Не удалось получить права root.",    "de": "Root-Zugriff fehlgeschlagen.",           "fr": "Échec de l'accès root.",                 "es": "Error al obtener acceso root.",          "pt": "Falha ao obter acesso root.",            "pl": "Błąd uzyskania dostępu root.",           "uk": "Помилка отримання прав root.",           "zh": "获取 root 权限失败。",                   "ja": "root アクセスに失敗しました。"},
    "applying":     {"en": "Applying changes...",                 "ru": "Применение изменений...",            "de": "Änderungen werden angewendet...",        "fr": "Application des modifications...",       "es": "Aplicando cambios...",                   "pt": "Aplicando alterações...",                "pl": "Stosowanie zmian...",                    "uk": "Застосування змін...",                   "zh": "正在应用更改...",                        "ja": "変更を適用中..."},
    "mount_now":    {"en": "Mount Now",                           "ru": "Монтировать",                        "de": "Jetzt einbinden",                        "fr": "Monter maintenant",                      "es": "Montar ahora",                           "pt": "Montar agora",                           "pl": "Zamontuj teraz",                         "uk": "Монтувати зараз",                        "zh": "立即挂载",                               "ja": "今すぐマウント"},
    "umount":       {"en": "Unmount",                             "ru": "Размонтировать",                     "de": "Aushängen",                              "fr": "Démonter",                               "es": "Desmontar",                              "pt": "Desmontar",                              "pl": "Odmontuj",                               "uk": "Розмонтувати",                           "zh": "卸载",                                   "ja": "アンマウント"},
    "not_mounted":  {"en": "Not mounted",                         "ru": "Не смонтирован",                     "de": "Nicht eingebunden",                      "fr": "Non monté",                              "es": "No montado",                             "pt": "Não montado",                            "pl": "Nie zamontowany",                        "uk": "Не змонтований",                         "zh": "未挂载",                                 "ja": "未マウント"},
    "mounted_at":   {"en": "Mounted at",                          "ru": "Смонтирован в",                      "de": "Eingebunden unter",                      "fr": "Monté sur",                              "es": "Montado en",                             "pt": "Montado em",                             "pl": "Zamontowany w",                          "uk": "Змонтований у",                          "zh": "挂载于",                                 "ja": "マウント先"},
    "disk_used":    {"en": "Used",                                "ru": "Занято",                             "de": "Belegt",                                 "fr": "Utilisé",                                "es": "Usado",                                  "pt": "Usado",                                  "pl": "Zajęte",                                 "uk": "Зайнято",                                "zh": "已用",                                   "ja": "使用中"},
    "disk_free":    {"en": "Free",                                "ru": "Свободно",                           "de": "Frei",                                   "fr": "Libre",                                  "es": "Libre",                                  "pt": "Livre",                                  "pl": "Wolne",                                  "uk": "Вільно",                                 "zh": "可用",                                   "ja": "空き"},
    "lbl_section":  {"en": "Partition Label",                     "ru": "Метка раздела",                      "de": "Partitionsbezeichnung",                  "fr": "Étiquette de partition",                 "es": "Etiqueta de partición",                  "pt": "Rótulo da partição",                     "pl": "Etykieta partycji",                      "uk": "Мітка розділу",                          "zh": "分区标签",                               "ja": "パーティションラベル"},
    "set_label":    {"en": "Set Label",                           "ru": "Установить метку",                   "de": "Bezeichnung setzen",                     "fr": "Définir l'étiquette",                    "es": "Establecer etiqueta",                    "pt": "Definir rótulo",                         "pl": "Ustaw etykietę",                         "uk": "Встановити мітку",                       "zh": "设置标签",                               "ja": "ラベルを設定"},
    "fmt_section":  {"en": "Format Partition",                    "ru": "Форматирование раздела",             "de": "Partition formatieren",                  "fr": "Formater la partition",                  "es": "Formatear partición",                    "pt": "Formatar partição",                      "pl": "Formatuj partycję",                      "uk": "Форматування розділу",                   "zh": "格式化分区",                             "ja": "パーティションをフォーマット"},
    "fmt_warn":     {"en": "WARNING: All data will be ERASED!",   "ru": "ВНИМАНИЕ: Все данные будут УНИЧТОЖЕНЫ!", "de": "WARNUNG: Alle Daten werden GELÖSCHT!",   "fr": "ATTENTION : Toutes les données seront EFFACÉES !", "es": "¡ADVERTENCIA: Todos los datos serán BORRADOS!", "pt": "AVISO: Todos os dados serão APAGADOS!", "pl": "OSTRZEŻENIE: Wszystkie dane zostaną USUNIĘTE!", "uk": "УВАГА: Усі дані будуть ЗНИЩЕНІ!",        "zh": "警告：所有数据将被清除！",               "ja": "警告：すべてのデータが消去されます！"},
    "new_fs":       {"en": "Filesystem",                          "ru": "Файловая система",                   "de": "Dateisystem",                            "fr": "Système de fichiers",                    "es": "Sistema de archivos",                    "pt": "Sistema de arquivos",                    "pl": "System plików",                          "uk": "Файлова система",                        "zh": "文件系统",                               "ja": "ファイルシステム"},
    "fmt_lbl_ph":   {"en": "Label after format (optional)",       "ru": "Метка после форматирования (опц.)", "de": "Bezeichnung nach Format (optional)",     "fr": "Étiquette après format (optionnel)",     "es": "Etiqueta tras formato (opcional)",       "pt": "Rótulo após formatação (opcional)",      "pl": "Etykieta po formatowaniu (opcja)",       "uk": "Мітка після форматування (опц.)",        "zh": "格式化后的标签（可选）",                 "ja": "フォーマット後のラベル（任意）"},
    "format_btn":   {"en": "Format Partition",                    "ru": "Форматировать раздел",               "de": "Partition formatieren",                  "fr": "Formater la partition",                  "es": "Formatear partición",                    "pt": "Formatar partição",                      "pl": "Formatuj partycję",                      "uk": "Форматувати розділ",                     "zh": "格式化分区",                             "ja": "パーティションをフォーマット"},
    "fmt_mounted":  {"en": "Unmount partition before formatting", "ru": "Сначала размонтируйте раздел",       "de": "Zuerst aushängen vor dem Formatieren",  "fr": "Démontez d'abord avant de formater",     "es": "Desmonte antes de formatear",            "pt": "Desmonte antes de formatar",             "pl": "Najpierw odmontuj przed formatowaniem",  "uk": "Спочатку розмонтуйте розділ",            "zh": "格式化前请先卸载",                       "ja": "フォーマット前にアンマウントを"},
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
        "ja": "/dev/{dev} をフォーマットしますか？\n\nすべてのデータが完全に消去されます。\nこの操作は元に戻せません！",
    },
    # Tooltips (EN + RU; other langs fall back to EN via t())
    "tt_disk":      {"en": "Select the physical drive or partition to configure",    "ru": "Выберите физический диск или раздел для настройки"},
    "tt_mount":     {"en": "Absolute path where the drive will be mounted",          "ru": "Абсолютный путь, куда будет примонтирован диск"},
    "tt_opts":      {"en": "Mount options for /etc/fstab. You can edit these manually.", "ru": "Параметры монтирования для /etc/fstab. Можно редактировать вручную."},
    "tt_auto":      {"en": "Write this drive to /etc/fstab so it mounts on boot",   "ru": "Прописать диск в /etc/fstab для монтирования при загрузке"},
    "tt_user":      {"en": "Select the system user who will own this drive",         "ru": "Выберите пользователя системы, который станет владельцем диска"},
    "tt_perms":     {"en": "Change directory owner and grant read/write access",     "ru": "Сменить владельца директории и выдать полные права"},
    "tt_rec":       {"en": "Apply permissions to all nested folders and files (may take time)", "ru": "Применить права ко всем вложенным папкам и файлам (может занять время)"},
    "tt_mount_now": {"en": "Mount the partition to the path specified above",        "ru": "Монтировать раздел по указанному пути"},
    "tt_umount":    {"en": "Unmount the currently mounted partition",                "ru": "Размонтировать смонтированный раздел"},
    "tt_set_label": {"en": "Change the partition label",                             "ru": "Изменить метку раздела"},
    "tt_format":    {"en": "Format with a new filesystem — ERASES ALL DATA",        "ru": "Форматировать с новой ФС — УНИЧТОЖАЕТ ВСЕ ДАННЫЕ"},
    "no_label":     {"en": "No Label",                                             "ru": "Без метки",                          "de": "Kein Name",                              "fr": "Sans nom",                               "es": "Sin nombre",                             "pt": "Sem nome",                               "pl": "Bez nazwy",                              "uk": "Без мітки",                              "zh": "无标签",                                 "ja": "ラベルなし"},
    "fstab_issues":      {"en": "⚠  fstab Issues",
                          "ru": "⚠  Проблемы fstab"},
    "fstab_orphan_hint": {"en": "These /etc/fstab entries have no matching connected disk.\n"
                                "Without 'nofail' they may block system boot.",
                          "ru": "Эти записи /etc/fstab не имеют соответствующего подключённого диска.\n"
                                "Без 'nofail' они могут блокировать загрузку системы."},
    "fstab_orphan_warn": {"en": "Disk not connected — may block boot",
                          "ru": "Диск не подключён — может блокировать загрузку"},
    "fstab_orphan_rm":   {"en": "Remove from fstab",
                          "ru": "Удалить из fstab"},
    "fstab_add_nofail":  {"en": "Add nofail",
                          "ru": "Добавить nofail"},
    "fmt_rm_fstab_note": {"en": "(The existing fstab entry for this partition will be removed automatically)",
                          "ru": "(Существующая запись fstab для этого раздела будет удалена автоматически)"},
    "dlg_warning":      {"en": "Warning",                                     "ru": "Предупреждение",                     "de": "Warnung",                                "fr": "Avertissement",                          "es": "Advertencia",                            "pt": "Aviso",                                  "pl": "Ostrzeżenie",                            "uk": "Попередження",                           "zh": "警告",                                   "ja": "警告"},
    "dlg_error":        {"en": "Error",                                        "ru": "Ошибка",                             "de": "Fehler",                                 "fr": "Erreur",                                 "es": "Error",                                  "pt": "Erro",                                   "pl": "Błąd",                                   "uk": "Помилка",                                "zh": "错误",                                   "ja": "エラー"},
    "dlg_success":      {"en": "Success",                                      "ru": "Успешно",                            "de": "Erfolg",                                 "fr": "Succès",                                 "es": "Éxito",                                  "pt": "Sucesso",                                "pl": "Sukces",                                 "uk": "Успіх",                                  "zh": "成功",                                   "ja": "成功"},
    "dlg_confirm_fmt":  {"en": "Confirm Format",                               "ru": "Подтвердите форматирование",         "de": "Format bestätigen",                      "fr": "Confirmer le formatage",                 "es": "Confirmar formato",                      "pt": "Confirmar formatação",                   "pl": "Potwierdź formatowanie",                 "uk": "Підтвердіть форматування",               "zh": "确认格式化",                             "ja": "フォーマットの確認"},
    "warn_empty_mount": {"en": "Mount point and options cannot be empty!",     "ru": "Точка монтирования и опции не могут быть пустыми!", "de": "Einhängepunkt und Optionen dürfen nicht leer sein!", "fr": "Le point de montage et les options ne peuvent pas être vides !", "es": "¡El punto de montaje y las opciones no pueden estar vacíos!", "pt": "O ponto de montagem e as opções não podem estar vazios!", "pl": "Punkt montowania i opcje nie mogą być puste!", "uk": "Точка монтування та параметри не можуть бути порожніми!", "zh": "挂载点和选项不能为空！", "ja": "マウントポイントとオプションを入力してください！"},
    "warn_no_mount":    {"en": "Specify mount point first!",                   "ru": "Сначала укажите точку монтирования!", "de": "Bitte zuerst Einhängepunkt angeben!",    "fr": "Veuillez d'abord spécifier un point de montage !", "es": "¡Primero especifique el punto de montaje!", "pt": "Especifique o ponto de montagem primeiro!", "pl": "Najpierw podaj punkt montowania!",       "uk": "Спочатку вкажіть точку монтування!",     "zh": "请先指定挂载点！",                       "ja": "最初にマウントポイントを指定してください！"},
    "warn_no_label":    {"en": "Enter a label!",                               "ru": "Введите метку!",                     "de": "Bezeichnung eingeben!",                  "fr": "Entrez une étiquette !",                 "es": "¡Introduzca una etiqueta!",              "pt": "Digite um rótulo!",                      "pl": "Podaj etykietę!",                        "uk": "Введіть мітку!",                         "zh": "请输入标签！",                           "ja": "ラベルを入力してください！"},
    "save_fstab":   {"en": "Save fstab",                                  "ru": "Сохранить fstab",                    "de": "fstab speichern",                        "fr": "Enregistrer fstab",                      "es": "Guardar fstab",                          "pt": "Salvar fstab",                           "pl": "Zapisz fstab",                           "uk": "Зберегти fstab",                         "zh": "保存 fstab",                             "ja": "fstab を保存"},
    "tt_save_fstab":{"en": "Update mount point and options in /etc/fstab", "ru": "Обновить точку монтирования и опции в /etc/fstab"},
    "cancel":       {"en": "Cancel",                                       "ru": "Отмена",                             "de": "Abbrechen",                              "fr": "Annuler",                                "es": "Cancelar",                               "pt": "Cancelar",                               "pl": "Anuluj",                                 "uk": "Скасувати",                              "zh": "取消",                                   "ja": "キャンセル"},
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
        "ja": "確認のためパーティション名（{dev}）を入力してください：",
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
        "ja": "UUID を保持（fstab エントリは有効なまま）",
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
        "ja": "{fs} のラベルが長すぎます — 最大 {max} 文字",
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
        "ja": "FAT16 は最大 4 GiB のボリュームのみ対応 — FAT32 か exFAT を使ってください",
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
        "ja": "FAT/exFAT ラベル：英数字・空白・'_'・'.'・'-' のみ",
    },
    # Подсказки и описания ФС — en+ru, остальные языки падают на en через t()
    "fmt_keep_fstab_note": {"en": "(UUID will be kept — the existing fstab entry stays valid)",
                            "ru": "(UUID будет сохранён — существующая запись fstab останется рабочей)"},
    "tt_keep_uuid": {"en": "Create the new filesystem with the same UUID so /etc/fstab and other references keep working. Available when the new filesystem is the same family as the current one.",
                     "ru": "Создать новую ФС с прежним UUID — /etc/fstab и другие ссылки продолжат работать. Доступно, когда новая ФС той же семьи, что и текущая."},
    "fs_desc_ext4":  {"en": "Linux standard — fast and reliable; best choice for internal drives",
                      "ru": "Стандарт Linux — быстрая и надёжная; лучший выбор для внутренних дисков"},
    "fs_desc_btrfs": {"en": "Modern Linux FS with snapshots and transparent compression",
                      "ru": "Современная ФС Linux со снапшотами и прозрачным сжатием"},
    "fs_desc_ntfs":  {"en": "Windows filesystem; use for drives shared with Windows",
                      "ru": "ФС Windows; для дисков, общих с Windows"},
    "fs_desc_exfat": {"en": "Flash drives and cross-OS exchange; no Linux permissions",
                      "ru": "Флешки и обмен между ОС; без прав доступа Linux"},
    "fs_desc_fat32": {"en": "Maximum compatibility; single file up to 4 GB",
                      "ru": "Максимальная совместимость; файл не больше 4 ГБ"},
    "fs_desc_fat16": {"en": "Legacy devices (cameras, MP3 players, embedded); volume up to 4 GiB",
                      "ru": "Старые устройства (фотоаппараты, MP3-плееры, встраиваемые); том до 4 ГиБ"},
    "fs_desc_ext3":  {"en": "Older ext generation — only for compatibility with old systems",
                      "ru": "Старое поколение ext — только для совместимости со старыми системами"},
    "fs_desc_ext2":  {"en": "Legacy ext without journal — loses data on power failure",
                      "ru": "Древняя ext без журнала — теряет данные при сбое питания"},
    # ── Профи-режим: разметка дисков ──
    "pro_mode":     {"en": "Advanced",                 "ru": "Расширенные",                "de": "Erweitert",                   "fr": "Avancé",                       "es": "Avanzado",                     "pt": "Avançado",                     "pl": "Zaawansowane",                "uk": "Розширені",                   "zh": "高级",                  "ja": "詳細設定"},
    "part_section": {"en": "Disk Partitioning",        "ru": "Разметка дисков",            "de": "Festplatten-Partitionierung", "fr": "Partitionnement des disques",  "es": "Particionado de discos",       "pt": "Particionamento de discos",    "pl": "Partycjonowanie dysków",      "uk": "Розмітка дисків",             "zh": "磁盘分区",              "ja": "パーティション管理"},
    "free_space":   {"en": "Free space",               "ru": "Свободное место",            "de": "Freier Speicherplatz",        "fr": "Espace libre",                 "es": "Espacio libre",                "pt": "Espaço livre",                 "pl": "Wolne miejsce",               "uk": "Вільне місце",                "zh": "可用空间",              "ja": "空き領域"},
    "create_part":  {"en": "Create partition",         "ru": "Создать раздел",             "de": "Partition erstellen",         "fr": "Créer une partition",          "es": "Crear partición",              "pt": "Criar partição",               "pl": "Utwórz partycję",             "uk": "Створити розділ",             "zh": "创建分区",              "ja": "パーティションを作成"},
    "delete_part":  {"en": "Delete",                   "ru": "Удалить",                    "de": "Löschen",                     "fr": "Supprimer",                    "es": "Eliminar",                     "pt": "Excluir",                      "pl": "Usuń",                        "uk": "Видалити",                    "zh": "删除",                  "ja": "削除"},
    "resize_part":  {"en": "Resize",                   "ru": "Изменить размер",            "de": "Größe ändern",                "fr": "Redimensionner",               "es": "Redimensionar",                "pt": "Redimensionar",                "pl": "Zmień rozmiar",               "uk": "Змінити розмір",              "zh": "调整大小",              "ja": "サイズ変更"},
    "new_table":    {"en": "New partition table",      "ru": "Новая таблица разделов",     "de": "Neue Partitionstabelle",      "fr": "Nouvelle table de partitions", "es": "Nueva tabla de particiones",   "pt": "Nova tabela de partições",     "pl": "Nowa tablica partycji",       "uk": "Нова таблиця розділів",       "zh": "新建分区表",            "ja": "新しいパーティションテーブル"},
    "new_size":     {"en": "New size",                 "ru": "Новый размер",               "de": "Neue Größe",                  "fr": "Nouvelle taille",              "es": "Nuevo tamaño",                 "pt": "Novo tamanho",                 "pl": "Nowy rozmiar",                "uk": "Новий розмір",                "zh": "新大小",                "ja": "新しいサイズ"},
    "fs_none":      {"en": "no filesystem",            "ru": "без файловой системы",       "de": "kein Dateisystem",            "fr": "sans système de fichiers",     "es": "sin sistema de archivos",      "pt": "sem sistema de arquivos",      "pl": "bez systemu plików",          "uk": "без файлової системи",        "zh": "无文件系统",            "ja": "ファイルシステムなし"},
    "external_badge": {"en": "External drive (USB)",   "ru": "Внешний диск (USB)",         "de": "Externes Laufwerk (USB)",     "fr": "Disque externe (USB)",         "es": "Disco externo (USB)",          "pt": "Disco externo (USB)",          "pl": "Dysk zewnętrzny (USB)",       "uk": "Зовнішній диск (USB)",        "zh": "外部驱动器（USB）",     "ja": "外付けドライブ（USB）"},
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
        "ja": "パーティション /dev/{dev} を削除しますか？\n\nこのパーティションのすべてのデータが完全に失われます！",
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
        "ja": "/dev/{disk} に新しい {type} パーティションテーブルを作成しますか？\n\nディスク全体のすべてのパーティションとデータが破壊されます！",
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
        "ja": "/dev/{dev} を {size} にサイズ変更しますか？",
    },
    # ── Сетевые диски ──
    "net_section":  {"en": "Network Drives",           "ru": "Сетевые диски",              "de": "Netzlaufwerke",               "fr": "Lecteurs réseau",              "es": "Unidades de red",              "pt": "Unidades de rede",             "pl": "Dyski sieciowe",              "uk": "Мережеві диски",              "zh": "网络驱动器",            "ja": "ネットワークドライブ"},
    "add_net":      {"en": "Add network drive",        "ru": "Добавить сетевой диск",      "de": "Netzlaufwerk hinzufügen",     "fr": "Ajouter un lecteur réseau",    "es": "Añadir unidad de red",         "pt": "Adicionar unidade de rede",    "pl": "Dodaj dysk sieciowy",         "uk": "Додати мережевий диск",       "zh": "添加网络驱动器",        "ja": "ネットワークドライブを追加"},
    "server":       {"en": "Server",                   "ru": "Сервер",                     "de": "Server",                      "fr": "Serveur",                      "es": "Servidor",                     "pt": "Servidor",                     "pl": "Serwer",                      "uk": "Сервер",                      "zh": "服务器",                "ja": "サーバー"},
    "net_share":    {"en": "Share (folder on server)", "ru": "Шара (папка на сервере)",    "de": "Freigabe (Ordner am Server)", "fr": "Partage (dossier du serveur)", "es": "Recurso (carpeta del servidor)", "pt": "Compartilhamento (pasta)",   "pl": "Udział (folder na serwerze)", "uk": "Спільна тека на сервері",     "zh": "共享（服务器上的文件夹）", "ja": "共有（サーバー上のフォルダー）"},
    "username":     {"en": "Username",                 "ru": "Имя пользователя",           "de": "Benutzername",                "fr": "Nom d'utilisateur",            "es": "Usuario",                      "pt": "Usuário",                      "pl": "Nazwa użytkownika",           "uk": "Ім'я користувача",            "zh": "用户名",                "ja": "ユーザー名"},
    "password":     {"en": "Password",                 "ru": "Пароль",                     "de": "Passwort",                    "fr": "Mot de passe",                 "es": "Contraseña",                   "pt": "Senha",                        "pl": "Hasło",                       "uk": "Пароль",                      "zh": "密码",                  "ja": "パスワード"},
    "guest_access": {"en": "Guest access (no password)", "ru": "Гостевой доступ (без пароля)", "de": "Gastzugang (ohne Passwort)", "fr": "Accès invité (sans mot de passe)", "es": "Acceso de invitado (sin contraseña)", "pt": "Acesso de convidado (sem senha)", "pl": "Dostęp gościa (bez hasła)", "uk": "Гостьовий доступ (без пароля)", "zh": "来宾访问（无密码）",    "ja": "ゲストアクセス（パスワードなし）"},
    "connect":      {"en": "Connect",                  "ru": "Подключить",                 "de": "Verbinden",                   "fr": "Connecter",                    "es": "Conectar",                     "pt": "Conectar",                     "pl": "Połącz",                      "uk": "Підключити",                  "zh": "连接",                  "ja": "接続"},
    "net_connected": {"en": "Connected",               "ru": "Подключён",                  "de": "Verbunden",                   "fr": "Connecté",                     "es": "Conectado",                    "pt": "Conectado",                    "pl": "Połączono",                   "uk": "Підключено",                  "zh": "已连接",                "ja": "接続済み"},
    "net_not_conn": {"en": "Not connected",            "ru": "Не подключён",               "de": "Nicht verbunden",             "fr": "Non connecté",                 "es": "No conectado",                 "pt": "Não conectado",                "pl": "Nie połączono",               "uk": "Не підключено",               "zh": "未连接",                "ja": "未接続"},
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
        "ja": "ネットワークドライブ {src} を削除しますか？\n\nサーバー上のデータは影響を受けません — 接続のみ削除されます。",
    },
    "ssh_key":      {"en": "SSH key file",             "ru": "Файл SSH-ключа",             "de": "SSH-Schlüsseldatei",          "fr": "Fichier de clé SSH",           "es": "Archivo de clave SSH",         "pt": "Arquivo de chave SSH",         "pl": "Plik klucza SSH",             "uk": "Файл SSH-ключа",              "zh": "SSH 密钥文件",          "ja": "SSH 鍵ファイル"},
    "net_hint":     {"en": "The drive is mounted into a real folder visible to ALL apps (not only Dolphin). It connects on first access; boot never hangs if the server is off.",
                     "ru": "Диск монтируется в настоящую папку, видимую ВСЕМ программам (не только Dolphin). Подключается при первом обращении; загрузка не виснет, если сервер выключен."},
    "warn_net_fields": {"en": "Fill in server and share!", "ru": "Заполни сервер и шару!",
                        "de": "Server und Freigabe ausfüllen!", "fr": "Renseignez le serveur et le partage !",
                        "es": "¡Rellena el servidor y el recurso!", "pt": "Preencha o servidor e o compartilhamento!",
                        "pl": "Wypełnij serwer i udział!", "uk": "Заповни сервер і теку!",
                        "zh": "请填写服务器和共享！", "ja": "サーバーと共有を入力してください！"},
    # en+ru — прочие языки берут en через t()
    "shrink_warn":  {"en": "\n\nShrinking moves the filesystem boundary — back up important data first!",
                     "ru": "\n\nУменьшение сдвигает границу файловой системы — сначала сделай резервную копию важных данных!"},
    "no_pt":        {"en": "No partition table — create one to use this disk",
                     "ru": "Нет таблицы разделов — создай её, чтобы использовать диск"},
    "ntfs_driver_line": {"en": "NTFS driver: {drv}", "ru": "Драйвер NTFS: {drv}"},
    "tt_pro":       {"en": "Show advanced partitioning tools for experienced users",
                     "ru": "Показать инструменты разметки для опытных пользователей"},
    "resize_na":    {"en": "Resize is not available for this filesystem",
                     "ru": "Для этой файловой системы изменение размера недоступно"},
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
    def __init__(self):
        super().__init__()
        self.current_lang = os.getenv("LANG", "en")[:2]
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
            fid = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                title_font_family = families[0]

        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            qss = open(qss_path).read()
            qss = qss.replace("{{TITLE_FONT}}", f'"{title_font_family}"')
            self.setStyleSheet(qss)

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
        self.info_lbl.setObjectName("StatusLabel")
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
            self.automount_btn.setStyleSheet(
                "background-color: transparent; color: rgb(243, 139, 168); border: 1px solid rgb(243, 139, 168);"
            )
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
            self.automount_btn.setStyleSheet("")
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
    # Wayland: link window to the .desktop file so the compositor uses its icon
    app.setDesktopFileName("equestria-os-disk-manager")
    icon_path = os.path.join(os.path.dirname(__file__), "equestria-os-disk-manager.png")
    app.setWindowIcon(QIcon(icon_path))
    win = DiskManagerApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
