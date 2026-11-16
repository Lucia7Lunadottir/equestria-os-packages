"""Line icons for the sidebar, coloured from the current theme: muted normally, accent when the page is open."""
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from kit import qt

SHAPES = {
    # a folder
    "projects": '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2h9A1.5 1.5 0 0 1 21 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-15'
                'A1.5 1.5 0 0 1 3 17.5z"/>',
    # four tiles
    "templates": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/>'
                 '<rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    # a cube, like the Unity logo's shape
    "editors": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
    # a Git branch: two commits on a line and one branching off
    "branch": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/>'
              '<path d="M6 7v10M18 9c0 5-6 4-11 8"/>',
}
SIZE = 18


def pixmap(name, color, size=SIZE):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{SHAPES[name]}</svg>')
    scale = 2  # sharp on HiDPI screens
    image = QPixmap(size * scale, size * scale)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    image.setDevicePixelRatio(scale)
    return image


def icon(name):
    """Normal: muted text colour; checked (the open page): accent; hovered: text colour."""
    result = QIcon()
    result.addPixmap(pixmap(name, qt.theme_color("subtext").name()), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(pixmap(name, qt.theme_color("text").name()), QIcon.Mode.Active, QIcon.State.Off)
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active):
        result.addPixmap(pixmap(name, qt.theme_color("accent").name()), mode, QIcon.State.On)
    return result
