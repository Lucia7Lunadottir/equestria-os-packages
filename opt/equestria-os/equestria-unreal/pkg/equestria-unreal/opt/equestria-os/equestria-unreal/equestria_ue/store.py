from __future__ import annotations

import json
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from equestria_ue.webengine import QWebEngineProfile
from equestria_ue.webengine import QWebEngineView

from equestria_ue.engines import Engine, find_engine_root
from equestria_ue.fab import engine_for_fab, fab_steps, parse_fab_zip
from equestria_ue.jobs import Job, Step
from equestria_ue.kit import tr
from equestria_ue.paths import CONFIG_DIR
from equestria_ue.steps import zip_steps
from equestria_ue.versions import vstr
from equestria_ue.webengine import CHROME_UA, HAVE_WEB, WebPage


LINUX_URL = "https://www.unrealengine.com/linux"
JS_LIST = r"""(() => { const o = new Set();
  document.querySelectorAll('*').forEach(e => { if (!e.children.length) {
    const m = (e.textContent || '').match(/Linux_(?:Unreal_Engine|Fab)_[\d._]+\.zip/); if (m) o.add(m[0]); } });
  return [...o]; })()"""
# Кнопка Download рядом с именем архива. Если это ссылка — возвращаем её адрес (лаунчер скачает
# сам, без всплывающего окна), иначе нажимаем кнопку. Адреса на странице — подписанные ссылки
# Amazon S3, живут час с загрузки страницы (X-Amz-Expires=3600), см. PAGE_FRESH_SEC.
JS_LINK = r"""((n) => { for (const e of document.querySelectorAll('*')) {
  if (!e.children.length && (e.textContent || '').trim() === n) { let r = e;
    for (let i = 0; i < 8; i++) { r = r.parentElement; if (!r) break;
      const b = [...r.querySelectorAll('a,button')].find(x => /download/i.test(x.textContent));
      if (b) { if (b.href && /^https?:/.test(b.href)) return b.href; b.click(); return 'clicked'; } } } }
  return null; })(%s)"""
PAGE_FRESH_SEC = 40 * 60   # старше — перезагрузить страницу перед загрузкой (ссылки истекают через час)


class EpicStore(QObject):
    changed = pyqtSignal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.builds: list = []          # [(5, 8, 4), ...] — то, что видно на странице Epic
        self.fab: dict = {}             # {(5, 7): "Linux_Fab_5.7.0_0.0.12.zip"} — плагин Fab для каждой версии
        self.fab_target: Engine | None = None   # куда ставить Fab, который сейчас скачивается
        self.dl: dict | None = None     # активная загрузка
        self.req = None
        self.pending = None
        self.view = None
        self.status = tr("Войдите в Epic-аккаунт на вкладке «Магазин» — один раз.")
        if not HAVE_WEB:
            self.status = tr("Не установлен python-pyqt6-webengine — встроенный вход недоступен.")
            return
        self.profile = QWebEngineProfile("equestria-unreal", self)
        wd = CONFIG_DIR / "web"
        wd.mkdir(parents=True, exist_ok=True)
        self.profile.setPersistentStoragePath(str(wd))
        self.profile.setCachePath(str(wd / "cache"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setHttpUserAgent(CHROME_UA)      # Google не пускает «встроенные» браузеры по User-Agent
        self.profile.downloadRequested.connect(self.on_download)
        self.view = QWebEngineView()
        self.view.setPage(WebPage(self.profile, self.view))
        self.loaded_at = 0.0            # когда страница Epic загружена (для срока жизни ссылок)
        self.view.loadFinished.connect(self._loaded)
        self.view.page().renderProcessTerminated.connect(self._renderer_died)
        self.view.load(QUrl(LINUX_URL))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scan)
        self.timer.start(60000)

    def _loaded(self, ok: bool) -> None:
        if ok and "unrealengine.com/linux" in self.view.url().toString():
            self.loaded_at = time.monotonic()
        QTimer.singleShot(2500, self.scan)

    def _page_fresh(self) -> bool:
        return ("unrealengine.com/linux" in self.view.url().toString()
                and time.monotonic() - self.loaded_at < PAGE_FRESH_SEC)

    def _renderer_died(self, status, code) -> None:
        """Процесс отрисовки QtWebEngine упал — иначе страница просто остаётся пустой."""
        from PyQt6.QtWebEngineCore import QWebEnginePage
        if status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            return
        self.status = tr("✗ Встроенный браузер (QtWebEngine) аварийно завершился, код {}. Это неисправность "
                         "системного пакета qt6-webengine, а не сайта Epic — переустановите его: "
                         "sudo pacman -S qt6-webengine", code)
        self.changed.emit()

    @property
    def ok(self) -> bool:
        return HAVE_WEB and bool(self.builds)

    def apply_cookies(self, cookies: list) -> str:
        """Кладёт cookie из другого браузера во встроенный и перезагружает страницу."""
        from PyQt6.QtCore import QDateTime
        from PyQt6.QtNetwork import QNetworkCookie
        if not self.view:
            return tr("Встроенный браузер недоступен.")
        if not cookies:
            return tr("В этом браузере нет cookie Epic — сначала войдите на unrealengine.com в нём.")
        store = self.profile.cookieStore()
        for c in cookies:
            qc = QNetworkCookie(c.name.encode(), c.value.encode())
            qc.setDomain(c.domain)
            qc.setPath(c.path)
            qc.setSecure(c.secure)
            qc.setHttpOnly(c.http_only)
            if c.expires:
                qc.setExpirationDate(QDateTime.fromSecsSinceEpoch(c.expires))
            store.setCookie(qc, QUrl("https://" + c.domain.lstrip(".")))
        self.reload()
        return tr("Перенесено cookie: {}. Страница перезагружается — вход должен подхватиться.", len(cookies))

    def reload(self) -> None:
        if self.view:
            self.view.load(QUrl(LINUX_URL))

    def scan(self) -> None:
        if not self.view or "unrealengine.com/linux" not in self.view.url().toString():
            return

        def cb(res):
            names = [n for n in (res or []) if isinstance(n, str)]
            vs = sorted({tuple(int(x) for x in n[len("Linux_Unreal_Engine_"):-4].split("."))
                         for n in names if n.startswith("Linux_Unreal_Engine_")}, reverse=True)
            fab = {}
            for n in names:
                p = parse_fab_zip(n)
                if p and (p[0] not in fab or p[1] > parse_fab_zip(fab[p[0]])[1]):
                    fab[p[0]] = n
            if fab != self.fab:
                self.fab = fab
                self.win.pages["engines"].rebuild()
            if vs and vs != self.builds:
                self.builds = vs
                self.status = tr("✓ Вход выполнен · готовых сборок: {}", len(vs))
                self.win.pages["catalog"].rebuild()
            elif not vs:
                self.status = tr("Войдите в Epic-аккаунт и примите лицензию на вкладке «Магазин» — список появится сам.")
            self.changed.emit()

        self.view.page().runJavaScript(JS_LIST, cb)

    # --- запрос установки
    def request(self, ver: tuple) -> None:
        self.request_file(f"Linux_Unreal_Engine_{vstr(ver)}.zip")

    def request_fab(self, eng: Engine) -> None:
        """Скачать и поставить плагин Fab для этого движка."""
        name = self.fab.get(eng.version[:2])
        if not name:
            self._manual()
            return
        self.fab_target = eng
        self.request_file(name)

    def request_file(self, name: str, tries: int = 0) -> None:
        if not self.view:
            return
        self.pending = name
        if not self._page_fresh():     # нет страницы или её ссылки уже истекли — загрузить заново
            self.view.load(QUrl(LINUX_URL))
            QTimer.singleShot(4500, lambda: self.request_file(name, tries + 1) if tries < 3 else self._manual())
            return

        def cb(res):
            if isinstance(res, str) and res.startswith("http"):
                self.view.page().download(QUrl(res), name)   # прямо в «Загрузки», без всплывающего окна
            if res:
                QTimer.singleShot(8000, lambda: None if self.dl else self._manual())
            elif tries < 4:
                QTimer.singleShot(1500, lambda: self.request_file(name, tries + 1))
            else:
                self._manual()

        self.view.page().runJavaScript(JS_LINK % json.dumps(name), cb)

    def _manual(self) -> None:
        self.status = tr("Нужно действие на странице Epic: войдите / примите лицензию / нажмите Download у нужной версии.")
        self.win.go("store")
        self.changed.emit()

    # --- загрузка
    def on_download(self, req) -> None:
        d = Path(self.win.cfg["install_dir"])
        d.mkdir(parents=True, exist_ok=True)
        req.setDownloadDirectory(str(d))
        name = req.downloadFileName() or "Linux_Unreal_Engine.zip"
        req.setDownloadFileName(name)
        self.req = req
        self.dl = {"name": name, "path": str(d / name), "recv": 0, "total": 0, "speed": 0.0, "t": time.time(), "last": 0}
        req.receivedBytesChanged.connect(self._prog)
        req.isFinishedChanged.connect(self._fin)
        req.accept()
        self.win.go("downloads")
        self.changed.emit()

    def _prog(self) -> None:
        r, dl = self.req, self.dl
        if not r or not dl:
            return
        now = time.time()
        dl["recv"], dl["total"] = r.receivedBytes(), max(r.totalBytes(), 0)
        if now - dl["t"] >= 1:
            dl["speed"] = (dl["recv"] - dl["last"]) / (now - dl["t"])
            dl["t"], dl["last"] = now, dl["recv"]
            self.changed.emit()

    def _fin(self) -> None:
        r, dl = self.req, self.dl
        if not r or not dl or not r.isFinished():
            return
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest as D
        self.req, self.dl = None, None
        st = r.state()
        self.changed.emit()
        if st != D.DownloadState.DownloadCompleted:
            self.win.jobs.log.emit(tr("✗ Загрузка {} не завершена", dl["name"]))
            return
        zp = dl["path"]
        if parse_fab_zip(dl["name"]):
            eng = self.fab_target or engine_for_fab(self.win.engines, dl["name"])
            self.fab_target = None
            if not eng:
                self.win.jobs.log.emit(tr("✗ Нет установленного движка для {} — архив оставлен в {}", dl["name"], zp))
                return
            self.win.add_job(Job(tr("Плагин Fab для {}", eng.title), fab_steps(zp, eng, True)), True)
            return
        dest = str(Path(zp).with_suffix(""))

        def done():
            root = find_engine_root(dest)
            if not root:
                raise RuntimeError(tr("в архиве не найдена папка Engine"))
            self.win.register_engine(root)

        steps = zip_steps(zp, dest) + [Step(tr("Удаление архива"), ["rm", "-f", zp])]
        self.win.add_job(Job(tr("Установка {}", dl["name"]), steps, done), True)

    def toggle_pause(self) -> None:
        r, dl = self.req, self.dl
        if not r or not dl:
            return
        if dl.get("paused"):
            r.resume()
            dl["paused"] = False
        else:
            r.pause()
            dl["paused"], dl["speed"] = True, 0.0
        self.changed.emit()

    def cancel(self) -> None:
        if self.req:
            self.req.cancel()
            self.req, self.dl = None, None
            self.changed.emit()
