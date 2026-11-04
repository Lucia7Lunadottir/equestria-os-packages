from __future__ import annotations


from PyQt6.QtCore import QRectF, QTimer, QUrl, Qt
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget

from equestria_ue.projects import Project
from equestria_ue.kit import kit_qt, tr


def chip(text: str, lvl: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("chip")
    lab.setProperty("lvl", lvl)
    return lab


def small_btn(text: str, tip: str = "", name: str = "small") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(name)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if tip:
        b.setToolTip(tip)
    return b


def show_launching(btn: QPushButton, ms: int = 8000) -> None:
    """Редактор открывается долго: кнопка на это время пишет «Запускается…» и не нажимается,
    чтобы было видно, что нажатие сработало."""
    text, enabled = btn.text(), btn.isEnabled()
    btn.setText(tr("Запускается…"))
    btn.setEnabled(False)

    def restore():
        btn.setText(text)
        btn.setEnabled(enabled)
    # таймер-потомок кнопки: если карточку пересоздали раньше, таймер умрёт вместе с ней
    # (в PyQt6 нет перегрузки singleShot(msec, context, slot))
    timer = QTimer(btn)
    timer.setSingleShot(True)
    timer.timeout.connect(restore)
    timer.timeout.connect(timer.deleteLater)
    timer.start(ms)


def card_frame(name: str = "card"):
    f = QFrame()
    f.setObjectName(name)
    return f


def scrolled(inner: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.Shape.NoFrame)
    s.setWidget(inner)
    return s


def title_row(text: str, *widgets) -> QHBoxLayout:
    h = QHBoxLayout()
    t = QLabel(text)
    t.setObjectName("title")
    h.addWidget(t)
    h.addStretch()
    for w in widgets:
        h.addWidget(w)
    return h


def open_folder(path: str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def make_icon(pr: Project) -> QIcon:
    w, h = 256, 144
    pm = QPixmap(pr.thumb) if pr.thumb else QPixmap()
    if not pm.isNull():
        pm = pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        pm = pm.copy((pm.width() - w) // 2, (pm.height() - h) // 2, w, h)
    else:
        pm = QPixmap(w, h)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hue = sum(map(ord, pr.name)) % 360
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, QColor.fromHsl(hue, 110, 70))
        g.setColorAt(1, kit_qt.theme_color("surface1"))
        p.fillRect(0, 0, w, h, g)
        f = QFont()
        f.setPixelSize(72)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, pr.name[:1].upper() or "U")
        p.end()
    return QIcon(pm)
