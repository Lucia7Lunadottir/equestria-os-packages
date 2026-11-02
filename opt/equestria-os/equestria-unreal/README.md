# Equestria Unreal Launcher

    python equestria_unreal.py        # нужны python-pyqt6 и equestria-qt-kit (+ python-pyqt6-webengine для магазина Epic)

Структура (каждый модуль — одна ответственность):

| Модуль | Что делает |
|---|---|
| `paths.py` | пути конфигурации и кеша |
| `kit.py` | подключение equestria-qt-kit: `tr()` и общая тема |
| `theme.py` | QSS-шаблон с ролями общей темы (цвета — из переключателя «Тема персонажа») |
| `i18n.json` | переводы строк на 12 языков (ключ — русская строка) |
| `config.py` | `Config` — настройки в JSON |
| `engines.py` | модель `Engine`, поиск, Install.ini |
| `projects.py` | модель `Project`, поиск .uproject, привязка версии |
| `launcher.py` | запуск редактора; `DdcPolicy` — где хранится кеш шейдеров (Zen / папка / память), `ShaderThreads` — потоки компиляции, `RayTracing` — трассировка лучей «как в проекте / выключить» без правки проекта; встроенный браузер (CEF) без GPU |
| `gpu_memory.py` | свободная видеопамять NVIDIA и кто её занимает (nvidia-smi); `ui/vram_check.py` предупреждает перед запуском, если свободно меньше 5 ГБ — редактор с Lumen/RT иначе падает с «Out of memory on Vulkan» или segfault в mimalloc |
| `versions.py` | теги GitHub, зависимости, константы версий |
| `steps.py` | шаги установки/обновления/сборки (`Step`-списки) |
| `jobs.py` | `Step`, `Job`, `Worker`, `JobManager` — очередь задач |
| `webengine.py` | необязательный QtWebEngine, `WebPage` |
| `browser_cookies.py` | перенос входа Epic из Firefox- и Chromium-браузеров (по классу на семейство) |
| `fab.py` | плагин Fab для Linux: распознать архив `Linux_Fab_*.zip`, поставить в `Engine/Plugins/Fab`, включить |
| `store.py` | `EpicStore` — вход в Epic, список сборок, загрузка |
| `ui/*.py` | страницы: library, engines_page, catalog, store_page, downloads, settings; main_window |
| `ui/tray.py` | `LauncherTray` — значок в трее: окно прячется, загрузки и сборка идут дальше; последние проекты, выход. Одна копия лаунчера (`SingleInstance`) |

Редактор Unreal запускается отдельным сеансом процессов (`start_new_session=True`) — выход из лаунчера его не закрывает.
| `app.py` | `main()` |
