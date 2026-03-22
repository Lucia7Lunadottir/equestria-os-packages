import sys
import os
import json
import shutil
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QFrame, QMessageBox,
    QCheckBox, QProgressBar, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFontDatabase, QFont, QIcon

import privilege


class SymbolToggle(QPushButton):
    """Checkable button that shows ☐/☑ instead of a native checkbox indicator."""
    stateChanged = pyqtSignal(int)

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self._label = label
        self.setCheckable(True)
        self.setObjectName("OptionsCb")
        self.toggled.connect(self._on_toggle)
        self._refresh()

    def _on_toggle(self, checked):
        self._refresh()
        self.stateChanged.emit(2 if checked else 0)

    def _refresh(self):
        self.setText(f"☑  {self._label}" if self.isChecked() else f"☐  {self._label}")

    def setChecked(self, val):
        super().setChecked(bool(val))
        self._refresh()


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
        t = SymbolToggle(key)
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
        nf.addWidget(self._lbl("── ntfs / fat options ───────────────────────────────────────────"))

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
        self._winnames = SymbolToggle("windows_names")
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
        self._autodefrag = SymbolToggle("autodefrag")
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
}


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
        for code, btn in self._lang_btns.items():
            btn.setProperty("active", "true" if code == lang else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
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

        self.recursive_cb.setText(self.t("recursive"))
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
        self.resize(600, 820)

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
        main_layout.addWidget(self.user_combo)

        self.recursive_cb = QCheckBox(self.t("recursive"))
        self.recursive_cb.setChecked(False)
        self.recursive_cb.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.fs_combo.addItems(["ext4", "btrfs", "ntfs", "exfat", "fat32", "ext3", "ext2"])
        fs_row.addWidget(self.lbl_new_fs)
        fs_row.addWidget(self.fs_combo, 1)
        fmt_layout.addLayout(fs_row)

        self.format_label_input = QLineEdit()
        self.format_label_input.setObjectName("DestEdit")
        self.format_label_input.setPlaceholderText(self.t("fmt_lbl_ph"))
        fmt_layout.addWidget(self.format_label_input)

        self.format_btn = QPushButton(self.t("format_btn"))
        self.format_btn.setObjectName("DangerBtn")
        self.format_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.format_btn.clicked.connect(self._format_disk)
        fmt_layout.addWidget(self.format_btn)

        main_layout.addWidget(fmt_frame)
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
                ["lsblk", "-J", "-o", "NAME,UUID,FSTYPE,MOUNTPOINTS,SIZE,TYPE,LABEL"],
                capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            self._parse_lsblk(data.get("blockdevices", []))
        except Exception as e:
            self.info_lbl.setText(f"Error loading disks: {e}")

        if not self.partitions:
            self.disk_combo.addItem("No suitable partitions found", None)
            return

        for name, info in self.partitions.items():
            label = info.get("label") or self.t("no_label")
            display = f"[{label}]  /dev/{name}  —  {info['size']}  ({info['fstype']})"
            self.disk_combo.addItem(display, name)

        # Restore previous selection
        if current_dev:
            for i in range(self.disk_combo.count()):
                if self.disk_combo.itemData(i) == current_dev:
                    self.disk_combo.setCurrentIndex(i)
                    break

    def _parse_lsblk(self, devices):
        for dev in devices:
            if dev.get("type") == "part" and dev.get("fstype") and dev.get("uuid"):
                if dev.get("fstype") not in ["swap"]:
                    self.partitions[dev["name"]] = dev
            if "children" in dev:
                self._parse_lsblk(dev["children"])

    def _generate_default_opts(self, fstype):
        if fstype in ["ntfs", "ntfs-3g", "vfat", "fat32", "exfat"]:
            return "defaults,noatime,uid=1000,gid=1000,dmask=022,fmask=022"
        elif fstype == "btrfs":
            return "defaults,noatime,compress=zstd,autodefrag"
        elif fstype in ["ext4", "ext3"]:
            return "defaults,noatime"
        return "defaults"

    # ------------------------------------------------------------------ UI update

    def _on_disk_selected(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name or dev_name not in self.partitions:
            self.info_lbl.setText("")
            for btn in (self.mount_now_btn, self.umount_btn, self.format_btn, self.set_label_btn):
                btn.setEnabled(False)
            return

        info = self.partitions[dev_name]
        uuid   = info.get("uuid", "N/A")
        fstype = info.get("fstype", "N/A")
        size   = info.get("size", "?")
        mounts = [m for m in info.get("mountpoints", []) if m]

        lines = [
            f"{self.t('uuid')}: {uuid}",
            f"{self.t('fstype')}: {fstype}   {self.t('size')}: {size}",
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
                self.opts_widget.set_options(self._generate_default_opts(fstype))
        else:
            self.automount_btn.setText(self.t("automount"))
            self.automount_btn.setStyleSheet("")
            label = info.get("label")
            self.mount_input.setText(f"/mnt/{label}" if label else f"/mnt/{dev_name}")
            self.opts_widget.set_options(self._generate_default_opts(fstype))

        # Pre-fill label input with current label
        self.label_input.setText(info.get("label") or "")

    # ------------------------------------------------------------------ backend runner

    def _run_backend(self, args, status=None):
        for w in (self.automount_btn, self.perms_btn, self.mount_now_btn,
                  self.umount_btn, self.format_btn, self.set_label_btn,
                  self.recursive_cb, self.user_combo, self.disk_combo):
            w.setEnabled(False)
        self.prog_status_lbl.setText(status or self.t("applying"))
        self.progress_frame.setVisible(True)

        self.worker = DiskWorker(args)
        self.worker.finished.connect(self._on_worker_done)
        self.worker.start()

    def _on_worker_done(self, success, message):
        for w in (self.automount_btn, self.perms_btn, self.mount_now_btn,
                  self.umount_btn, self.format_btn, self.set_label_btn,
                  self.recursive_cb, self.user_combo, self.disk_combo):
            w.setEnabled(True)
        self.progress_frame.setVisible(False)

        if success:
            QMessageBox.information(self, "Success", self.t("success"))
        else:
            QMessageBox.critical(self, "Error", f"{self.t('err_elevate')}\n{message}")
        self._load_disks()

    # ------------------------------------------------------------------ actions

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
                QMessageBox.warning(self, "Warning", "Mount point and options cannot be empty!")
                return
            self._run_backend(["--add-fstab", uuid, mount, fstype, options],
                              f"Adding {uuid} to fstab...")

    def _mount_now(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name:
            return
        mount = self.mount_input.text().strip()
        if not mount:
            QMessageBox.warning(self, "Warning", "Specify mount point first!")
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
            QMessageBox.warning(self, "Warning", "Specify mount point first!")
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
            QMessageBox.warning(self, "Warning", "Enter a label!")
            return
        fstype = self.partitions[dev_name].get("fstype", "")
        self._run_backend(["--set-label", dev_name, fstype, label],
                          f"Setting label '{label}' on /dev/{dev_name}...")

    def _format_disk(self):
        dev_name = self.disk_combo.currentData()
        if not dev_name:
            return
        fstype = self.fs_combo.currentText()
        label  = self.format_label_input.text().strip()

        msg = self.t("confirm_fmt").format(dev=dev_name)
        reply = QMessageBox.question(
            self, "Confirm Format", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        args = ["--format", dev_name, fstype]
        if label:
            args.append(label)
        self._run_backend(args, f"Formatting /dev/{dev_name} as {fstype}...")


def main():
    app = QApplication(sys.argv)
    # Wayland: link window to the .desktop file so the compositor uses its icon
    app.setDesktopFileName("equestria-os-disk-manager")
    icon_path = os.path.join(os.path.dirname(__file__), "EquestriaOS-Logo.png")
    app.setWindowIcon(QIcon(icon_path))
    win = DiskManagerApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
