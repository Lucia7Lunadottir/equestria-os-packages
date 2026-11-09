from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout

from equestria_ue.kit import tr



try:
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAVE_WEB = True
except ImportError:      # пакет python-pyqt6-webengine не установлен
    HAVE_WEB = False
    QWebEnginePage = QWebEngineProfile = QWebEngineView = None

CHROME_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/130.0.0.0 Safari/537.36")

if HAVE_WEB:
    class WebPage(QWebEnginePage):
        """Открывает всплывающие окна (вход через Google, Facebook и т.д.) в отдельном окне."""
        popups: list = []

        def createWindow(self, _type):
            dlg = QDialog(QApplication.activeWindow())
            dlg.setWindowTitle(tr("webengine.sign"))
            dlg.resize(520, 720)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(0, 0, 0, 0)
            view = QWebEngineView(dlg)
            page = WebPage(self.profile(), view)
            view.setPage(page)
            lay.addWidget(view)
            page.windowCloseRequested.connect(dlg.close)
            WebPage.popups.append(dlg)
            dlg.finished.connect(lambda *_: WebPage.popups.remove(dlg) if dlg in WebPage.popups else None)
            dlg.show()
            return page
else:
    WebPage = None
