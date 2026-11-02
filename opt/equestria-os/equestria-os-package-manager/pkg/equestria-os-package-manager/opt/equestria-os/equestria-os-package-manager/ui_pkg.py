import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QComboBox, QScrollArea, QFrame,
                             QAbstractButton)
from PyQt6.QtCore import (Qt, pyqtSignal, pyqtProperty, QPropertyAnimation,
                          QEasingCurve, QSize, QRectF)
from PyQt6.QtGui import QPainter, QColor, QIcon
try:
    import equestria_kit  # noqa: F401
except ImportError:  # запуск из исходников, пакет equestria-qt-kit не установлен
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "equestria-qt-kit"))
from equestria_kit import qt as kit_qt


class SwitchToggle(QAbstractButton):
    """Переключатель-пилюля с бегунком, как в disk-manager: фон плавно
    заливается акцентным цветом, бегунок едет вправо. Рисуется вручную —
    QSS такое не умеет. Метка отдельно (SwitchRow), чтобы переносилась."""
    stateChanged = pyqtSignal(int)

    TRACK_W, TRACK_H, KNOB_M = 34, 18, 3
    C_TRACK_OFF = (69, 71, 90)
    C_TRACK_ON  = (245, 194, 231)
    C_KNOB_OFF  = (205, 214, 244)
    C_KNOB_ON   = (30, 30, 46)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pos = 0.0
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        return QSize(self.TRACK_W, self.TRACK_H + 4)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.35)
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


class SwitchRow(QWidget):
    """SwitchToggle + переносимая метка справа; клик по метке тоже переключает.
    Повторяет API QCheckBox (setText/text/isChecked/setChecked)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(8)
        self.switch = SwitchToggle(self)
        self.label = QLabel("", self)
        self.label.setWordWrap(True)
        kit_qt.style(self.label, "color: @text@; font-size: 13px; background: transparent;")
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.label, 1)

    def mousePressEvent(self, _event):
        # Клик по метке или фону строки — тоже переключение
        self.switch.toggle()

    def setText(self, text):
        self.label.setText(text)

    def text(self):
        return self.label.text()

    def isChecked(self):
        return self.switch.isChecked()

    def setChecked(self, val):
        self.switch.setChecked(bool(val))

class PackageRow(QFrame):
    def __init__(self, pkg_data, delete_text, on_delete_callback):
        super().__init__()
        self.pkg_data = pkg_data
        self.setObjectName("PackageRow")
        self.setFixedHeight(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(12)

        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(40, 40)
        self.lbl_icon.setScaledContents(True)
        icon = QIcon()
        if pkg_data.icon_name:
            # Third-party .deb/.rpm apps sometimes point Icon= at an actual
            # path (e.g. "/opt/someapp/icon.png") instead of a theme name —
            # fromTheme() alone would never find those.
            if os.path.isabs(pkg_data.icon_name) and os.path.isfile(pkg_data.icon_name):
                icon = QIcon(pkg_data.icon_name)
            else:
                icon = QIcon.fromTheme(pkg_data.icon_name)
        if icon.isNull():
            icon = QIcon.fromTheme("package-x-generic")
        if not icon.isNull():
            self.lbl_icon.setPixmap(icon.pixmap(40, 40))

        info_layout = QVBoxLayout()
        self.lbl_name = QLabel(pkg_data.name)
        kit_qt.style(self.lbl_name, "color: white; font-weight: bold; font-size: 15px; background: transparent;")

        info_text = f"{pkg_data.category} ({pkg_data.source})"
        if getattr(pkg_data, "size_text", ""):
            info_text += f" • {pkg_data.size_text}"
        self.lbl_info = QLabel(info_text)
        kit_qt.style(self.lbl_info, "color: @subtext@; font-size: 12px; background: transparent;")

        desc = pkg_data.description
        self.lbl_desc = QLabel(desc if len(desc) <= 90 else desc[:87] + "...")
        kit_qt.style(self.lbl_desc, "color: @subtext@; font-size: 11px; background: transparent;")
        if desc:
            self.lbl_desc.setToolTip(desc)
        else:
            self.lbl_desc.hide()

        info_layout.addWidget(self.lbl_name)
        info_layout.addWidget(self.lbl_info)
        info_layout.addWidget(self.lbl_desc)

        self.btn_delete = QPushButton(delete_text)
        self.btn_delete.setObjectName("ListDeleteBtn") # ФИКС: Жесткая привязка по ID
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setFixedWidth(110)
        self.btn_delete.clicked.connect(lambda checked=False, p=self.pkg_data: on_delete_callback(p))

        layout.addWidget(self.lbl_icon)
        layout.addLayout(info_layout)
        layout.addStretch()
        layout.addWidget(self.btn_delete)

class Ui_PackageManager:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1000, 750)

        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        self.main_layout = QVBoxLayout(self.root)
        self.main_layout.setContentsMargins(25, 25, 25, 25)

        self.title_label = QLabel("✨ Equestria OS Packages")
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.lang_layout = QHBoxLayout()
        self.lang_layout.setSpacing(5)
        self.lang_layout.addStretch()
        self.main_layout.addLayout(self.lang_layout)

        filter_box = QHBoxLayout()
        self.search_field = QLineEdit()
        self.search_field.setObjectName("SearchField")
        self.search_field.setPlaceholderText("Search...")

        self.category_dropdown = QComboBox()
        self.category_dropdown.setObjectName("CategoryDropdown")
        self.category_dropdown.setFixedWidth(200)

        filter_box.addWidget(self.search_field, 1)
        filter_box.addWidget(self.category_dropdown)
        self.main_layout.addLayout(filter_box)

        # Fetching pacman/AUR/flatpak/pip/etc all takes a few seconds — without
        # this, the window just shows an empty list while that happens, which
        # reads as "broken" rather than "loading".
        self.loading_lbl = QLabel("Loading...")
        self.loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kit_qt.style(self.loading_lbl, "color: @subtext@; font-size: 14px; padding: 30px;")
        self.main_layout.addWidget(self.loading_lbl)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("PackageList")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSpacing(2)
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)
        self.scroll_area.hide()  # shown once the first fetch completes

        # Пагинация: список установленных пакетов (pacman + AUR + flatpak +
        # pip + ...) на живой системе легко переваливает за тысячу — рендерить
        # их все разом как виджеты одновременно то же самое, что вешать
        # приложение на пару секунд при каждом обновлении/поиске.
        pagination_box = QHBoxLayout()
        self.btn_prev_page = QPushButton("⬅ Previous")
        self.btn_prev_page.setObjectName("PaginationBtn")
        self.btn_prev_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev_page.setFixedWidth(120)

        self.lbl_page_info = QLabel("Page 1 / 1")
        kit_qt.style(self.lbl_page_info, "color: @subtext@; font-weight: bold;")
        self.lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_next_page = QPushButton("Next ➡")
        self.btn_next_page.setObjectName("PaginationBtn")
        self.btn_next_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next_page.setFixedWidth(120)

        pagination_box.addWidget(self.btn_prev_page)
        pagination_box.addWidget(self.lbl_page_info, 1)
        pagination_box.addWidget(self.btn_next_page)
        self.pagination_widget = QWidget()
        self.pagination_widget.setLayout(pagination_box)
        self.main_layout.addWidget(self.pagination_widget)
        self.pagination_widget.hide()  # shown once the first fetch completes

        # ФИКС: QFrame позволяет задать фон (черное перекрытие) через QSS!
        self.modal_overlay = QFrame(self.root)
        self.modal_overlay.setObjectName("ModalOverlay")
        self.modal_overlay.hide()

        v_modal = QVBoxLayout(self.modal_overlay)
        self.modal_box = QFrame()
        self.modal_box.setObjectName("ModalBox")
        # Ширина фиксированная, высота растёт под список найденных данных
        self.modal_box.setFixedWidth(440)
        self.modal_box.setMinimumHeight(240)

        m_layout = QVBoxLayout(self.modal_box)
        m_layout.setContentsMargins(30, 30, 30, 30)

        self.modal_title = QLabel("✨ Confirmation")
        kit_qt.style(self.modal_title, "color: white; font-size: 22px; font-weight: bold; background: transparent;")
        self.modal_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.modal_text = QLabel("Confirm?")
        kit_qt.style(self.modal_text, "color: @text@; font-size: 15px; background: transparent;")
        self.modal_text.setWordWrap(True)
        self.modal_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Появляется, только если у пакета нашлись данные в домашней папке
        self.chk_delete_data = SwitchRow()
        self.chk_delete_data.hide()

        self.modal_paths = QLabel("")
        kit_qt.style(self.modal_paths, "color: @subtext@; font-size: 12px; background: transparent;")
        self.modal_paths.setWordWrap(True)
        self.modal_paths.hide()

        # Появляется только при попытке удалить python-pip, если через него
        # что-то установлено — гейтит кнопку "Удалить" до явного подтверждения
        self.chk_pip_ack = SwitchRow()
        self.chk_pip_ack.hide()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)

        self.btn_confirm_cancel = QPushButton("Cancel")
        self.btn_confirm_cancel.setObjectName("ModalCancelBtn") # ФИКС: ID
        self.btn_confirm_cancel.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_confirm_delete = QPushButton("Delete")
        self.btn_confirm_delete.setObjectName("ModalDeleteBtn") # ФИКС: ID
        self.btn_confirm_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_delete.setMinimumHeight(45)

        # Отдельная кнопка вместо переиспользования btn_confirm_delete — иначе
        # пришлось бы перецеплять его click-обработчик туда-сюда между обычным
        # удалением пакета и авто-чисткой shell rc, что ломко и легко забыть вернуть
        self.btn_rc_auto = QPushButton("Remove automatically")
        self.btn_rc_auto.setObjectName("ModalDeleteBtn")
        self.btn_rc_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rc_auto.setMinimumHeight(45)
        self.btn_rc_auto.hide()

        btn_row.addWidget(self.btn_confirm_cancel)
        btn_row.addWidget(self.btn_confirm_delete)
        btn_row.addWidget(self.btn_rc_auto)

        m_layout.addWidget(self.modal_title)
        m_layout.addStretch()
        m_layout.addWidget(self.modal_text)
        m_layout.addWidget(self.chk_delete_data)
        m_layout.addWidget(self.modal_paths)
        m_layout.addWidget(self.chk_pip_ack)
        m_layout.addStretch()
        m_layout.addLayout(btn_row)
        v_modal.addWidget(self.modal_box, 0, Qt.AlignmentFlag.AlignCenter)
