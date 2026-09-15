# equestria-os-settings — команды и действия GUI, по модулям

Архитектура: плагинная (`base_module.py` → `BaseModule`), каждый `modules/mod_*.py` — один пункт в сайдбаре, автообнаруживается при старте (см. README проекта). Часть модулей — просто **встроенные копии других приложений** (`EmbeddedAppModule`), часть — самостоятельная логика прямо здесь.

## Модули-обёртки (просто встраивают окно другого пакета — своих команд нет)

Все ниже — 18-строчные файлы вида `class X(EmbeddedAppModule): lib_dir=... main_file=... main_class=...`. Реальная логика и команды — в `COMMANDS.md` того пакета.

| Модуль | Встраивает | Смотреть команды в |
|---|---|---|
| `mod_disk_manager.py` | `equestria-os-disk-manager` | `../equestria-os-disk-manager/COMMANDS.md` |
| `mod_package_manager.py` | `equestria-os-package-manager` | `../equestria-os-package-manager/COMMANDS.md` |
| `mod_save_point.py` | `equestria-os-save-point` | `../equestria-os-save-point/COMMANDS.md` |
| `mod_services.py` | `equestria-os-services-manager` | `../equestria-os-services-manager/COMMANDS.md` |
| `mod_swap_manager.py` | `equestria-os-swap-manager` | `../equestria-os-swap-manager/COMMANDS.md` |
| `mod_software_center.py` | `equestria-os-software-center` | `../equestria-os-software-center/COMMANDS.md` |
| `mod_character_theme.py` | `equestria-os-character-theme` | `../equestria-os-character-theme/COMMANDS.md` |
| `mod_task_panel.py` | `equstria-os-task-panel-changer` | `../equstria-os-task-panel-changer/COMMANDS.md` |
| `mod_tutorial.py` | `equestria-os-tutorial` | `../equestria-os-tutorial/COMMANDS.md` |
| `mod_mirrors.py` | `pg-rankmirrors` | `../pg-rankmirrors/COMMANDS.md` |

Каждый такой модуль показывается в сайдбаре, только если `required_binary` реально существует (иначе — экран «не установлено» с кнопкой `yay -S <package_name>`).

## `mod_gpu.py` — Драйвер GPU

* Детект: `pg-gpu-sync --show-gpu` (`_detect_gpu()`, `mod_gpu.py:55`), `lspci [-k]`, `glxinfo -B`, `vulkaninfo --summary`, `qdbus6 org.kde.KWin ...` (`_detect_kwin_compositor()`, `mod_gpu.py:162`), `nvidia-smi`, `dkms status`, наличие `/etc/modprobe.d/blacklist-nouveau.conf`.
* **«Переконфигурировать драйвер»** (`_run_reconfigure()`, `mod_gpu.py:798`) → `pkexec pg-gpu-sync --auto --32 --reset-mode`. `pg-gpu-sync` — отдельный пакет проекта, который сам определяет модель GPU и ставит подходящий проприетарный/открытый драйвер; `--32` означает «поставить также 32-битные библиотеки» (нужны для старых игр и Proton/Wine, которые часто 32-битные); `--reset-mode` — вернуться к автовыбору, даже если раньше пользователь вручную переключался на nouveau.
* **«Переключить на Nouveau»** (`_run_switch_nouveau()`, `mod_gpu.py:819`) → `pkexec pg-gpu-sync --nouveau`. `nouveau` — открытый (reverse-engineered) драйвер NVIDIA в самом ядре Linux, в отличие от проприетарного, который ставится отдельным пакетом — переключение означает удаление всех проприетарных NVIDIA-пакетов.
* **«Тестовый режим»** (`_run_test_mode()`, `mod_gpu.py:838`) → `pkexec pg-gpu-sync --test --32` (dry-run — не меняет систему, только проверяет).
* **«Открыть NVIDIA Settings»** (`_open_nvidia_settings()`, `mod_gpu.py:793`) → запускает `nvidia-settings` — официальная утилита NVIDIA для контроля драйвера (не часть этого проекта).
* Требует `pg-gpu-sync` (`required_binary`); диагностические утилиты (`lspci`, `glxinfo`, `vulkaninfo`, `qdbus6`) не обязательны — их отсутствие просто скрывает часть информации, не ломает модуль.

## `mod_brightness.py` — Яркость экрана

* **Аппаратная подсветка** — сначала `busctl call org.freedesktop.login1 <путь_сессии> org.freedesktop.login1.Session SetBrightness ssu backlight <устройство> <значение>` (`_set_backlight_via_logind()`, `mod_brightness.py:193`). `busctl` — консольный клиент к системной D-Bus шине (аналог `qdbus`, но от systemd, а не от Qt/KDE). `Session.SetBrightness` — метод самого `systemd-logind` (менеджера сессий пользователей), которым реально пользуется и штатная регулировка яркости KDE — он **не требует пароля**, потому что logind сам решает, что активная сессия имеет право менять яркость своего же экрана. Путь сессии находится через `GetSessionByPID` (`_get_logind_session_path()`, `mod_brightness.py:146`) — метод, который по PID процесса возвращает, какой сессии он принадлежит. Если этот способ недоступен — фолбэк на `brightnessctl`, затем на прямую запись числа в файл `/sys/class/backlight/<dev>/brightness` (виртуальный файл ядра — запись числа туда напрямую меняет яркость, это самый низкоуровневый способ), и только в крайнем случае `pkexec tee <файл>` (`_set_backlight()`, `mod_brightness.py:209`).
* **DDC/CI** (внешние мониторы) — `ddcutil detect`/`getvcp 10`/`setvcp 10` (`_set_ddc_brightness()`, `mod_brightness.py:313`). DDC/CI — протокол, которым монитор общается с видеокартой через тот же кабель (HDMI/DisplayPort), которым пользуются кнопки на корпусе самого монитора. `10` — это номер VCP-кода (VCP = Virtual Control Panel, стандарт VESA MCCS) конкретно для яркости; у мониторов десятки таких кодов для разных параметров (контраст, цветовая температура и т.д.), 0x10=10 зарезервирован стандартом именно под brightness.
* **Программная (xrandr)** — только на X11 (`_is_wayland_session()`, `mod_brightness.py:73`, отключает её на Wayland). `xrandr --output <o> --brightness <v>` (`_set_xrandr_brightness()`, `mod_brightness.py:106`) не меняет реальную яркость лампы подсветки — это программный гамма-фильтр (умножает значения пикселей перед выводом), поэтому и работает на любом мониторе без DDC, но и не экономит энергию, в отличие от настоящей аппаратной регулировки. На Wayland `xrandr` обращается к XWayland — прослойке совместимости, а не к настоящему композитору, поэтому команда «выполняется», но реального экрана не касается — отсюда отключение.
* **Параметр ядра** (карточка «Параметр загрузки ядра») — правит `GRUB_CMDLINE_LINUX_DEFAULT` в `/etc/default/grub` через `pkexec sh -c "cp ... && cp ... && grub-mkconfig -o /boot/grub/grub.cfg"` (`_apply_kernel_param()`, `mod_brightness.py:396`, восстановление — `_restore_grub_backup()`, `mod_brightness.py:456`). `grub-mkconfig` — официальная утилита GRUB, которая **перегенерирует** конфиг загрузчика (`/boot/grub/grub.cfg`) из файлов настроек (`/etc/default/grub` и сканирования установленных ядер) — редактировать `grub.cfg` напрямую нельзя, он всегда пересобирается заново этой командой. Параметр `acpi_backlight=native`/`vendor`/`video`/`none` передаётся ядру при загрузке и определяет, какой из нескольких возможных интерфейсов управления подсветкой ядро будет создавать (подробности — в самом коде и истории разработки этого модуля).

## `mod_report_issue.py` — Сообщить о проблеме

* Не отправляет ничего сама — собирает диагностику: `lspci -k` (`_detect_gpu_and_driver()`, `mod_report_issue.py:77`) — флаг `-k` у `lspci` добавляет к списку устройств строку «Kernel driver in use», то есть какой именно драйвер ядра сейчас реально управляет конкретным устройством (в отличие от простого списка PCI-устройств без этого флага); `/etc/os-release`, `/proc/cpuinfo` (оба — стандартные текстовые файлы ядра/дистрибутива с информацией о системе, не требующие никаких команд для чтения); `pacman -Qs equestria` — поиск среди установленных пакетов по подстроке «equestria» в имени (`_collect_diagnostics()`, `mod_report_issue.py:121`). Затем открывает браузер (`QDesktopServices.openUrl` — стандартный кроссплатформенный метод Qt «открыть эту ссылку системным способом», в Linux обычно вызывает `xdg-open` под капотом) на предзаполненную форму нового issue (`_on_send()`, `mod_report_issue.py:317`) вида `github.com/.../issues/new?title=...&body=...` — GitHub сам поддерживает предзаполнение формы через query-параметры URL, это не хак, а официально документированная возможность. Отправляет сам пользователь, залогинившись в GitHub — токен доступа нигде не хранится и не передаётся.

## `mod_suggest_feature.py` — Предложить идею

Брат-близнец `mod_report_issue.py` выше, но без сбора диагностики (идея не привязана к конкретному железу) и с другим адресом назначения: **GitHub Discussions**, а не Issues. `_on_send()` (`mod_suggest_feature.py`) открывает браузер на `github.com/Lucia7Lunadottir/equestria-os-packages/discussions/new?category=ideas&title=...&body=...`.

> **Чем Discussions отличается от Issues** — Issues в GitHub предназначены для конкретных, действенных задач (баг, который нужно починить, конкретная фича, которую нужно сделать), тогда как Discussions — форум для обсуждений, идей и вопросов, необязательно требующих немедленного действия; у Discussions есть отдельные категории (здесь используется `ideas` — «💡 Ideas», одна из шести стандартных категорий GitHub Discussions). `category`, `title` и `body` в URL — такие же официально документированные query-параметры GitHub, как и у `issues/new`, только для другого раздела репозитория; сама возможность их использовать подтверждена напрямую (страница категории `discussions/categories/ideas` реально существует в этом репозитории на момент написания).

## `mod_auto_update.py` — Обновления

* **Проверить сейчас** (`_check_now()`, `mod_auto_update.py:477`) → `/usr/bin/pg-update` — внешний бинарь одноимённого пакета, который сам проверяет наличие обновлений и шлёт уведомление KDE.
* **Интервал проверки** (`_on_interval_changed()`, `mod_auto_update.py:369`) → пишет systemd user drop-in `~/.config/systemd/user/pg-update.timer.d/override.conf`, затем `systemctl --user daemon-reload` (заставляет systemd перечитать изменённые файлы юнитов — без этого шага изменения не подхватятся) `&& systemctl --user restart pg-update.timer`.
* **Автоустановка обновлений** (`_enable_auto_install()`, `mod_auto_update.py:440`) — сама создаёт юниты `~/.config/systemd/user/equestria-autoupdate.{service,timer}` (содержимое — `_AI_SERVICE_CONTENT`/`_AI_TIMER_CONTENT`, строки 53/63: `ExecStart=pkexec pacman -Syu --noconfirm`, таймер `OnBootSec=15min` — через 15 минут после каждой загрузки, `OnUnitActiveSec=24h` — и затем каждые 24 часа после предыдущего запуска) и включает их через `systemctl --user enable --now` (`--now` — включить автозапуск И запустить прямо сейчас одной командой, а не двумя отдельными).
* **«Обновить систему»** (`_update_system()`, `mod_auto_update.py:491`) → открывает `konsole -e bash -c "<скрипт>"` с самовосстанавливающимся апдейтом:
  1. `pkexec pacman -Syu --noconfirm` — `-Sy` синхронизирует базы данных пакетов с зеркалами, `-Su` обновляет всё установленное до последних версий (вместе `-Syu` — полное обновление системы, именно так и рекомендует делать Arch Wiki, никогда не `-Sy` отдельно от `-u`, чтобы не словить рассинхронизацию версий пакетов);
  2. если в логе встречается «operation too slow» / «failed to retrieve» — определяет страну по `curl https://ipinfo.io/country` (внешний сервис геолокации по IP), перезапускает `pkexec pg-rankmirrors-backend rank <страна>` (см. `pg-rankmirrors/COMMANDS.md` — переранжирование зеркал через `reflector`), повторяет `pacman -Syu`;
  3. если в логе «are in conflict» — вытаскивает конфликтующие пакеты регуляркой из текста ошибки pacman, `pkexec pacman -Rdd --noconfirm <пакеты>` (`-Rdd` — удалить, полностью игнорируя проверку зависимостей — обычно опасно, но здесь оправдано: пакет и так будет переустановлен следующим шагом), повторяет `pacman -Syu`;
  4. `yay -Qua` (список пакетов из AUR, у которых есть обновление) → по одному `yay -S --noconfirm <pkg>` — по одному специально, чтобы ошибка сборки одного AUR-пакета не остановила обновление остальных;
  5. `flatpak update -y`, если flatpak установлен.

## `mod_install_packages.py` — Системные компоненты

* Список пакетов — из `packages.json` рядом с приложением (не хардкод в коде).
* Статус — `pacman -Q <pkg>` (`mod_install_packages.py:106`, установлен?) и `pacman -Qu` (строка 122, есть обновление? — без аргумента `pacman -Qu` проверяет ВСЕ установленные пакеты разом, результат потом фильтруется по нужному имени).
* **Установить/Обновить/Удалить** (`_on_action()`, `mod_install_packages.py:269`) → открывает `konsole -e yay -S <pkg>` / `konsole -e yay -R --noconfirm <pkg>` — интерактивный терминал: `yay` (AUR-помощник) сам вызывает `sudo`/спрашивает пароль при необходимости внутри себя, `pkexec` тут не используется, потому что `yay` не рассчитан на запуск под `pkexec` (ждёт интерактивный терминал для части своих вопросов, включая сборку AUR-пакетов).

## `mod_network.py` — Интернет (самый большой модуль)

| Секция | Что читает | Что применяет |
|---|---|---|
| DNS (`_apply_dns()`, `mod_network.py:1489`) | `nmcli -t -f IP4.DNS device show` / `resolvectl dns` | `nmcli con mod <conn> ipv4.dns "<ip1> <ip2>"` + `ipv4.ignore-auto-dns yes`. `nmcli` — командная строка NetworkManager (сетевого менеджера, который реально управляет соединениями в фоне — GUI-виджет в трее просто его отображает); `con mod` меняет настройки уже существующего сетевого профиля («соединения»), `ignore-auto-dns yes` запрещает NetworkManager подмешивать DNS-серверы, полученные автоматически по DHCP, поверх заданных вручную. Откат (`_run_dns_revert()`, `mod_network.py:1574`) — те же поля в пустую строку + `ignore-auto-dns no`. |
| TCP-оптимизации (`_apply_tcp()`, `mod_network.py:1621`) | `sysctl -n <ключ>` по каждому параметру | Собранный `.conf` → `pkexec tee /etc/sysctl.d/99-equestria-network.conf` (строка 1650), затем `pkexec sysctl --system`. `sysctl` — интерфейс к настройкам ядра во время работы (`net.ipv4.tcp_congestion_control` и т.п. — параметры сетевого стека ядра Linux); файлы в `/etc/sysctl.d/*.conf` — это то, что ядро применяет автоматически при каждой загрузке, а `sysctl --system` перечитывает их все немедленно, без перезагрузки. Паттерн `pkexec tee <файл>` — способ записать содержимое в системный файл с правами root, где сами данные приходят через stdin процесса, а не как аргумент командной строки (иначе `pkexec` пришлось бы запускать через `bash -c` с пользовательским текстом внутри команды — риск инъекции при неаккуратном экранировании). Откат — `pkexec rm -f <file>` + `sysctl --system`. |
| WiFi энергосбережение (строка 1714) | — | `pkexec tee /etc/NetworkManager/conf.d/99-equestria-wifi-powersave.conf` + `pkexec systemctl restart NetworkManager` — файлы в `conf.d/` NetworkManager читает при старте, поэтому нужен перезапуск самой службы, чтобы новая настройка энергосбережения WiFi-адаптера подхватилась. |
| Драйвер WiFi (`_apply_driver_params()`, `mod_network.py:870`) | — | `pkexec tee /etc/modprobe.d/99-equestria-wifi.conf` (строка 901) — файлы `modprobe.d` задают параметры, с которыми ядро загружает конкретный модуль (например, `iwlwifi`, драйвер WiFi-чипов Intel); кнопка «Перезагрузить модуль» (`_reload_wifi_module()`, `mod_network.py:997`) → `pkexec bash -c "modprobe -r <drv> && modprobe <drv>"` — `-r` выгружает модуль ядра из памяти, без аргумента — загружает заново, вместе это заставляет модуль перечитать новые параметры без перезагрузки всей системы (для `iwlwifi` сначала дополнительно выгружается `iwlmvm` — зависимый модуль, который держит `iwlwifi` занятым и не даст его выгрузить, пока сам не выгружен). Плюс `nmcli con down/up <conn>` — «выключить-включить» конкретное сетевое соединение, чтобы WiFi реально переподключился с новыми параметрами модуля. |
| IPv6 (строка 1780+) | `sysctl -n net.ipv6.conf.all.disable_ipv6` | Отдельный sysctl-файл `/etc/sysctl.d/99-equestria-ipv6.conf` через тот же паттерн `pkexec tee` + `sysctl --system`. |
| Speedtest (`_run_speedtest()`, `mod_network.py:1846`) | — | `speedtest-cli --simple`, при отсутствии — `speedtest --simple` (официальный клиент Ookla, другой проект с похожим именем и другим форматом вывода — код умеет оба). |

## `mod_proton.py` — Windows-игры и приложения

* Список установленных Proton-приложений и их размер префикса — `~/.local/share/Equestria OS/ProtonApps/` («префикс» Wine/Proton — отдельная папка-имитация диска `C:\`, у каждого приложения обычно своя, чтобы они не конфликтовали друг с другом реестром/установленными библиотеками).
* Настройки по умолчанию (DXVK/VKD3D/Esync/Fsync — все это разные технологии совместимости DirectX↔Vulkan и производительности Wine, не изобретения проекта) — просто JSON `~/.config/Equestria OS/Proton/defaults.json`, команд не вызывает.
* **Очистить кеш шейдеров** (`_clear_shaders()`, `mod_proton.py:163`) конкретного приложения → находит файлы шейдеров в префиксе и удаляет (`shutil.rmtree`/`os.remove` — функции Python, не внешние команды), без `pkexec` — это всё в домашнем каталоге пользователя. Кеш шейдеров — скомпилированные под конкретную видеокарту версии графических шейдеров игры; после смены GPU/драйвера старый кеш бесполезен, но занимает место и может даже мешать (устаревшие скомпилированные шейдеры).
* **Удалить префикс** (`_clear_prefix()`, `mod_proton.py:189`) → `shutil.rmtree(prefix_path)` — удаляет всю имитацию `C:\` для приложения целиком, при следующем запуске Proton создаст новую с нуля.
* **Очистить кеш Mesa/GPU** (`_clear_mesa()`, `mod_proton.py:423`, пути — `_MESA_CACHE_DIRS`, строка 41) → чистит `~/.cache/mesa_shader_cache`, `~/.cache/mesa`, `~/.cache/radeonsi`, `~/.cache/AMD` — Mesa — открытая реализация OpenGL/Vulkan для видеокарт AMD/Intel (и частично NVIDIA через nouveau), у неё свой отдельный от Proton кеш скомпилированных шейдеров.
* **«Открыть настройки Proton»** → запускает `/usr/bin/equestria-proton-settings` (это и есть `proton-exe-starter`, см. `../proton-exe-starter/COMMANDS.md`).

## Прочее

* Ни один модуль настроек не хранит собственное отдельное состояние в `/etc` без разметки `equestria-` в имени файла — все системные файлы, созданные модулями (`99-equestria-*.conf`, `.grub-backup-*`), легко найти и вручную откатить при необходимости.
