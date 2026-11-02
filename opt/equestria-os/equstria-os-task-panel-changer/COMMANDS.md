# equestria-os-task-panel-changer — как устроено (2.0, переписано 2026-11-02)

Главное правило: с Plasma только через её официальные интерфейсы. Никаких копий
файлов конфигурации, `kquitapp6`, `rm -rf` кешей, подмены родных пакетов KDE.
Root не нужен: всё в домашнем каталоге.

## Модули

| Файл | Что делает |
|---|---|
| `main.py` | окно: связывает интерфейс с модулями; `install_excepthook()` — ошибка показывается окном и пишется в `~/.cache/equestria-os-task-panel-changer/error.log`, а не роняет программу молча |
| `presets.py` | `Preset`, `PresetStore`: системные `presets.json`, свои `~/.local/share/EquestriaOS/PanelStyles/presets.json`, снятые раскладки `layouts/<id>.json` |
| `preset_applier.py` | применение по шагам: стиль панели → вид рабочего стола (если меняется) → раскладка |
| `panel_style.py` | цвет/прозрачность панели: Plasma-стили `EquestriaPanel-Light` и `-Dark` |
| `panel_layout.py` | раскладка в формате KDE, поправки (ярлыки, монитор памяти), скрипт Plasma, перевод старых `.bak` |
| `desktop_icons.py` | значки рабочего стола (вид «Папка» / «Рабочий стол») |
| `plasma.py` | D-Bus plasmashell (QtDBus), `kreadconfig6`/`kwriteconfig6`, день/ночь, перезапуск оболочки через systemd |
| `localization.py` | строки из `localization.csv` (10 языков) |

## Цвет панели: день и ночь

* Два Plasma-стиля в `~/.local/share/plasma/desktoptheme/`: в каждом только `metadata.json` и
  `widgets/panel-background.svg`. **Файла `colors` нет** — текст и всплывающие окна берут цвета
  из цветовой схемы персонажа.
* `metadata.json`: обязательно `"X-Plasma-API": "5.0"` и `"fallbackPackage": "default"`. С ключом
  `X-Plasma-API-Minimum-Version` Plasma не берёт набор цветов Complementary — экран блокировки
  осветляется, текст в окне выхода тёмный (найдено 2026-11-02, Plasma 6.8).
* Переключает стили сама KDE: глобальные темы персонажей (`kde_laf.py` в
  equestria-os-character-theme) содержат `[plasmarc][Theme] name=EquestriaPanel-Light|-Dark` —
  так же Breeze указывает `name=default`. Базовые версии стилей (без своего фона, выглядят как Breeze)
  ставит пакет character-theme в `/usr/share`: глобальная тема **не должна** ссылаться на
  несуществующий стиль — Plasma тогда тоже ломает Complementary.
* Применение сразу: `plasma-apply-desktoptheme <стиль для текущего времени суток>`. Если этот стиль
  уже активен, сначала на миг `default` — иначе Plasma не перерисует панель с новым SVG.
* `LegacyThemeCleanup` при запуске убирает следы старых версий (только свои): заглушку
  `desktoptheme/default` («Equestria Fallback»), старый стиль `EquestriaPanel` с файлом `colors`,
  схему `color-schemes/EquestriaPanel.colors`.

## Раскладка панелей

* Формат — тот же, что отдаёт `org.kde.PlasmaShell.dumpCurrentLayoutJS` (им KDE делает раскладки
  глобальных тем): панели с `location/alignment/lengthMode/floating/hiding/height` (в gridUnit)
  и виджетами с конфигом по группам (`"/General": {...}`).
* «📸 Снять текущие панели» = `dumpCurrentLayoutJS` → `layouts/<id>.json`. Без перезапуска.
* Применение = скрипт Desktop Scripting API через `evaluateScript`: старые панели удаляются,
  новые создаются `new Panel` / `addWidget` / `writeConfig`. Рабочий стол и обои не трогаются.
* Перед применением: закреплённые ярлыки пользователя переносятся в панель задач (ярлыки
  удалённых программ отбрасываются); виджет памяти получает сенсоры и заголовок `Title`/`Title[xx]`
  (тот же блок, что пишет `fix_sysmon_title.sh`, чтобы он не перезапускал оболочку при входе).
* Старые снимки `layouts/*.bak` (копия всего конфига Plasma + `_shellrc`) один раз переводятся
  в `.json` (`LegacySnapshotConverter`), оригиналы переезжают в `layouts/legacy-backup/`.

## Значки рабочего стола

У Plasma нет D-Bus-метода смены вида рабочего стола. Если вид нужно сменить, `ShellRestart`:
`systemctl --user stop plasma-plasmashell.service` → `kwriteconfig6 ... --key plugin` →
`systemctl --user start ...` → ждёт появления plasmashell на D-Bus. Если менять нечего —
перезапуска нет.

## Режим правки KDE

D-Bus: `evaluateScript("lockCorona(false);")` и свойство `editMode = true`.

## Прочее

* `fix_sysmon_title.sh` (автозапуск при входе) — старая одноразовая миграция заголовка виджета памяти.
* `save_panel.sh` / `restore_panel.sh` — консольное резервное копирование конфига панелей, к окну не относятся.
