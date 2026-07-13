from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QComboBox, QScrollArea, QFrame,
                             QAbstractButton)
from PyQt6.QtCore import (Qt, pyqtSignal, pyqtProperty, QPropertyAnimation,
                          QEasingCurve, QSize, QRectF)
from PyQt6.QtGui import QPainter, QColor


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
        self.label.setStyleSheet("color: rgb(210, 200, 230); font-size: 13px; background: transparent;")
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
        self.setFixedHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)

        info_layout = QVBoxLayout()
        self.lbl_name = QLabel(pkg_data.name)
        self.lbl_name.setStyleSheet("color: white; font-weight: bold; font-size: 15px; background: transparent;")

        self.lbl_info = QLabel(f"{pkg_data.category} ({pkg_data.source})")
        self.lbl_info.setStyleSheet("color: rgb(180, 170, 200); font-size: 12px; background: transparent;")

        info_layout.addWidget(self.lbl_name)
        info_layout.addWidget(self.lbl_info)

        self.btn_delete = QPushButton(delete_text)
        self.btn_delete.setObjectName("ListDeleteBtn") # ФИКС: Жесткая привязка по ID
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setFixedWidth(110)
        self.btn_delete.clicked.connect(lambda checked=False, p=self.pkg_data: on_delete_callback(p))

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
        self.modal_title.setStyleSheet("color: white; font-size: 22px; font-weight: bold; background: transparent;")
        self.modal_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.modal_text = QLabel("Confirm?")
        self.modal_text.setStyleSheet("color: rgb(210, 200, 230); font-size: 15px; background: transparent;")
        self.modal_text.setWordWrap(True)
        self.modal_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Появляется, только если у пакета нашлись данные в домашней папке
        self.chk_delete_data = SwitchRow()
        self.chk_delete_data.hide()

        self.modal_paths = QLabel("")
        self.modal_paths.setStyleSheet("color: rgb(150, 140, 175); font-size: 12px; background: transparent;")
        self.modal_paths.setWordWrap(True)
        self.modal_paths.hide()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)

        self.btn_confirm_cancel = QPushButton("Cancel")
        self.btn_confirm_cancel.setObjectName("ModalCancelBtn") # ФИКС: ID
        self.btn_confirm_cancel.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_confirm_delete = QPushButton("Delete")
        self.btn_confirm_delete.setObjectName("ModalDeleteBtn") # ФИКС: ID
        self.btn_confirm_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_delete.setMinimumHeight(45)

        btn_row.addWidget(self.btn_confirm_cancel)
        btn_row.addWidget(self.btn_confirm_delete)

        m_layout.addWidget(self.modal_title)
        m_layout.addStretch()
        m_layout.addWidget(self.modal_text)
        m_layout.addWidget(self.chk_delete_data)
        m_layout.addWidget(self.modal_paths)
        m_layout.addStretch()
        m_layout.addLayout(btn_row)
        v_modal.addWidget(self.modal_box, 0, Qt.AlignmentFlag.AlignCenter)
