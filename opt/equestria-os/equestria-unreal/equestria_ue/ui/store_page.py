from __future__ import annotations

from equestria_kit import live_i18n


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
        reload_b = small_btn(tr("store_page.reload_page"))
        reload_b.clicked.connect(st.reload)
        ff = small_btn(tr("store_page.transfer_sign_from_browser"), tr("store_page.sign_unrealengine_com_your_regular"))
        ff.clicked.connect(lambda: self._pick_browser(st, ff))
        v.addLayout(title_row(tr("common.epic_store"), ff, reload_b))
        g = live_i18n.call(QLabel, tr("store_page.google_does_not_allow_embedded"))
        g.setObjectName("hint")
        g.setWordWrap(True)
        v.addWidget(g)
        self.lbl = live_i18n.call(QLabel, st.status)
        self.lbl.setObjectName("hint")
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        if st.view:
            v.addWidget(st.view, 1)
        else:
            e = live_i18n.call(QLabel, tr("store_page.install_python_pyqt6_webengine_package"))
            e.setObjectName("hint")
            e.setWordWrap(True)
            v.addWidget(e)
            v.addStretch()
        self.st = st
        st.changed.connect(self._status)

    def _status(self) -> None:
        live_i18n.call(self.lbl.setText, self.st.status)

    def _pick_browser(self, st, anchor) -> None:
        found = [(src, src.read()) for src in discover()]
        found = [(s, c) for s, c in found if c]
        if not found:
            st.status = tr("store_page.no_epic_sign_found_any")
            st.changed.emit()
            return
        m = QMenu(self)
        for src, cookies in found:
            live_i18n.call(m.addAction, f"{src.label}  ({len(cookies)})").triggered.connect(
                lambda _=False, c=cookies: (setattr(st, "status", st.apply_cookies(c)), st.changed.emit()))
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
