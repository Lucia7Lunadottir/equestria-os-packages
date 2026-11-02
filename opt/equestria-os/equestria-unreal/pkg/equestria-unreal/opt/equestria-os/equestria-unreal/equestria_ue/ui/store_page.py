from __future__ import annotations


from PyQt6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from equestria_ue.browser_cookies import discover

from equestria_ue.kit import tr
from equestria_ue.ui.widgets import small_btn, title_row


class StorePage(QWidget):
    def __init__(self, win):
        super().__init__()
        st = win.store
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(12)
        reload_b = small_btn(tr("Обновить страницу"))
        reload_b.clicked.connect(st.reload)
        ff = small_btn(tr("Перенести вход из браузера ▾"), tr("Войдите на unrealengine.com в обычном браузере (хоть через Google)"))
        ff.clicked.connect(lambda: self._pick_browser(st, ff))
        v.addLayout(title_row(tr("Магазин Epic"), ff, reload_b))
        g = QLabel(tr("Google не пускает во встроенные браузеры. Вариант 1: войдите на unrealengine.com в обычном браузере "
                      "(через Google можно), затем нажмите «Перенести вход из браузера» и выберите его. Вариант 2: вход "
                      "по e-mail и паролю (пароль задаётся на epicgames.com → Аккаунт → Пароль)."))
        g.setObjectName("hint")
        g.setWordWrap(True)
        v.addWidget(g)
        self.lbl = QLabel(st.status)
        self.lbl.setObjectName("hint")
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        if st.view:
            v.addWidget(st.view, 1)
        else:
            e = QLabel(tr("Установите пакет python-pyqt6-webengine (pacman -S python-pyqt6-webengine) и перезапустите лаунчер."))
            e.setObjectName("hint")
            e.setWordWrap(True)
            v.addWidget(e)
            v.addStretch()
        self.st = st
        st.changed.connect(self._status)

    def _status(self) -> None:
        self.lbl.setText(self.st.status)

    def _pick_browser(self, st, anchor) -> None:
        found = [(src, src.read()) for src in discover()]
        found = [(s, c) for s, c in found if c]
        if not found:
            st.status = tr("Не нашла вход Epic ни в одном браузере. Войдите на unrealengine.com в Firefox, Chrome, Brave, "
                           "Vivaldi и т.п. (закройте браузер или оставьте открытым) и нажмите снова.")
            st.changed.emit()
            return
        m = QMenu(self)
        for src, cookies in found:
            m.addAction(f"{src.label}  ({len(cookies)})").triggered.connect(
                lambda _=False, c=cookies: (setattr(st, "status", st.apply_cookies(c)), st.changed.emit()))
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
