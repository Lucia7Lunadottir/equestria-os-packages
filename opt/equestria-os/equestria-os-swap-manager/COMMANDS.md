# equestria-os-swap-manager — команды и действия GUI

`swap_app.py` (GUI) → `pkexec [--] python3 swap_backend.py <флаги>` — один процесс-бэкенд принимает **несколько команд сразу** в одном вызове (например, `--zram-enable 8 lzo-rle --overcommit 1`).

## Элеватор

`privilege.find_elevator()` ищет `pkexec` → `kdesu` → `/usr/lib/kf6/kdesu`, что найдётся первым. **Важно:** `privilege.start_elevated()`/`needs_elevation()` в этом же файле — мёртвый код: там захардкожен путь `disk_backend.py`, которого в этом пакете не существует. `swap_app.py` его не вызывает — вместо этого сам строит команду с правильным путём к `swap_backend.py`. То же самое верно для `core.py` — не импортируется нигде. Похоже, оба файла — копия заготовки из другого пакета (relocator/rename-helper), прибрать можно смело.

## Флаги бэкенда → что реально выполняется (`swap_backend.py`)

| Флаг | Функция | Что делает |
|---|---|---|
| `--create <path> <size_gb> yes\|no` | `create_swap()` | См. подробный разбор ниже. |
| `--disable <path>` | `disable_swap()` | `swapoff <path>` + убирает строку из `/etc/fstab`. Файл подкачки не удаляется. |
| `--delete <path>` | `delete_swap()` | То же, что `--disable`, и затем `os.remove(path)` — сам файл стирается. |
| `--swappiness <N>` | `set_knob("swappiness")` | Синоним `--set swappiness <N>` (0–200): пишет `/proc/sys/vm/swappiness` (сразу) + ключ в `/etc/sysctl.d/99-swappiness.conf` (навсегда). |
| `--overcommit <N>` | `set_knob("overcommit")` | То же для `vm.overcommit_memory`, сохраняется в `/etc/sysctl.d/99-memory.conf`. |
| `--panic-on-oom <N>` | `set_knob("panic_on_oom")` | То же для `kernel.panic_on_oom` в тот же файл `99-memory.conf` — но только если `/proc/sys/kernel/panic_on_oom` вообще существует в текущем ядре (иначе тихо пропускается, без ошибки). |
| `--set <имя> <значение>` | `set_knob()` | Любой параметр из `memory_config.KNOBS` (таблица ниже). Значение проверяется (диапазон / список слов) до записи; неизвестное имя — ошибка. |
| `--zswap on\|off` | `ZramSetup.set_zswap()` | `off`: пишет `N` в `/sys/module/zswap/parameters/enabled` + `/etc/tmpfiles.d/equestria-swap-manager-zswap.conf` (повтор при загрузке). `on`: только если zswap выключали мы (есть наш файл) — удаляет файл и пишет `Y`. |
| `--oomd enable\|disable` | `set_oomd()` | `systemctl enable\|disable --now systemd-oomd`. |
| `--zram-enable <size_gb> <algorithm>` | `ZramSetup.enable()` | См. подробно ниже. |
| `--zram-disable` | `ZramSetup.disable()` | Выключает zram (drop-in с `zram-size = 0`) и возвращает zswap. |

### Объяснение параметров ядра

> **`vm.swappiness`** (0-200 в современных ядрах, раньше 0-100) — насколько активно ядро выгружает малоиспользуемую память в swap вместо того, чтобы держать её в RAM. Низкое значение — ядро до последнего держит всё в RAM, использует swap только когда памяти совсем не хватает (лучше для отзывчивости при достаточном объёме RAM); высокое — ядро охотнее выгружает неактивные страницы заранее.
>
> **`vm.overcommit_memory`** — политика ядра на выделение памяти сверх реально доступной (многие программы резервируют больше памяти, чем реально используют — например, при `fork()`). `0` — эвристика ядра «на глазок», `1` — разрешить всегда, `2` — запретить выделение сверх реального лимита (строже, но безопаснее от internóusing OOM killer в неожиданный момент).
>
> **`kernel.panic_on_oom`** — что делать, когда памяти не хватает совсем ни на что (Out Of Memory): `0` — вызвать OOM killer (ядро само выбирает и убивает «самый прожорливый» процесс, обычная практика), `1` — вместо этого **паниковать всем ядром** (полная остановка системы) — используется редко, обычно на серверах, где непредсказуемое убийство процесса хуже контролируемой перезагрузки.
>
> **`systemd-oomd`** — более новый, «умный» OOM-демон в userspace (в дополнение к встроенному в ядро OOM killer), который следит за системой на уровне cgroups и убивает проблемные процессы раньше, чем ядро окончательно захлебнётся — `systemctl enable/disable --now` включает/выключает именно его, ядерный OOM killer при этом продолжает работать в любом случае как последняя линия защиты.

### Параметры `--set` (`memory_config.KNOBS`)

Все параметры описаны **один раз** в `memory_config.py`: окно читает оттуда текущие значения и список файлов, бэкенд — применяет. Классы:
- `SysctlKnob` — целое число в `/proc/sys/...`, сохраняется строкой `ключ=значение` в свой файл `/etc/sysctl.d/`;
- `DirtyKnob` — то же, но в MiB; `0` = «Авто»: ядро не принимает `*_bytes = 0`, поэтому пишется `*_ratio` со стандартным процентом, а строка `*_bytes` убирается из файла;
- `SysfsChoiceKnob` — слово в `/sys/...` (`always [madvise] never`); у sysfs нет своего конфига, поэтому сохраняется строкой `w <путь> - - - - <слово>` в `/etc/tmpfiles.d/equestria-swap-manager-mm.conf` — systemd-tmpfiles повторяет её при каждой загрузке.

| Имя | Что | Файл | Диапазон | Стандарт ядра |
|---|---|---|---|---|
| `swappiness` | `vm.swappiness` | `99-swappiness.conf` | 0–200 | 60 |
| `overcommit` | `vm.overcommit_memory` | `99-memory.conf` | 0–2 | 0 |
| `panic_on_oom` | `kernel.panic_on_oom` | `99-memory.conf` | 0–2 | 0 |
| `page_cluster` | `vm.page-cluster` | `99-zram.conf` | 0–10 | 3 |
| `vfs_cache_pressure` | `vm.vfs_cache_pressure` | `99-vm-tuning.conf` | 1–1000 | 100 |
| `watermark_boost_factor` | `vm.watermark_boost_factor` | `99-vm-tuning.conf` | 0–30000 | 15000 |
| `watermark_scale_factor` | `vm.watermark_scale_factor` | `99-vm-tuning.conf` | 1–3000 | 10 |
| `dirty_background_mb` | `vm.dirty_background_bytes` / `_ratio` | `99-vm-tuning.conf` | 0 (Авто) – 65536 MiB | 10% ОЗУ |
| `dirty_mb` | `vm.dirty_bytes` / `_ratio` | `99-vm-tuning.conf` | 0 (Авто) – 65536 MiB | 20% ОЗУ |
| `thp` | `/sys/kernel/mm/transparent_hugepage/enabled` | tmpfiles `…-mm.conf` | always / madvise / never | always |
| `thp_defrag` | `/sys/kernel/mm/transparent_hugepage/defrag` | tmpfiles `…-mm.conf` | always / defer / defer+madvise / madvise / never | madvise |

Почему именно эти: при zram swap дешёвый, а перечитывать с диска код программ — дорого. `swappiness` > 100 заставляет ядро сжимать неактивные данные в zram, а не выбрасывать кэш программ; `watermark_boost_factor = 0` убирает резкие всплески освобождения памяти; `watermark_scale_factor = 125` начинает фоновое освобождение раньше, чтобы программам не приходилось самим останавливаться на нём (direct reclaim); `thp = madvise` убирает остановки на уплотнение памяти (compaction stall) у программ, которые огромных страниц не просили. Это же ставит пресет «как в Windows».

### Проверка системы (`health.py`)

Работает без root, только чтение. `MemoryState.from_system()` снимает состояние (активные swap, zram-устройства с алгоритмом и степенью сжатия из `/sys/block/zramN/mm_stat`, наш drop-in, zswap, значения всех `KNOBS`), затем каждый класс-проверка из `CHECKS` возвращает `Issue` (ключ перевода + аргументы бэкенда для исправления) или `None`:

| Проверка | Когда срабатывает | Исправление |
|---|---|---|
| `LegacyServiceCheck` | есть `/etc/systemd/system/equestria-zram.service` | `--zram-enable` (сам убирает службу) |
| `ExtraZramCheck` | активно больше одного zram-swap | `--zram-enable` (сбрасывает лишние устройства) |
| `ZramNotRunningCheck` | наш drop-in просит zram, но zram-swap не активен | `--zram-enable` с сохранёнными размером/алгоритмом |
| `NoSwapCheck` | нет ни одного swap и zram не настроен | `--zram-enable` (50% ОЗУ, zstd) |
| `ZswapWithZramCheck` | zram активен и zswap включён | `--zswap off` |
| `LowSwappinessCheck` | zram активен и swappiness < 100 | `--set swappiness 150` |
| `PageClusterCheck` | zram активен и page-cluster ≠ 0 | `--set page_cluster 0` |
| `ThpAlwaysCheck` | THP = always | `--set thp madvise` |

«Исправить всё» склеивает исправления в **один** вызов бэкенда (один запрос пароля), без повторов; `--zram-enable` идёт первым.

### Файлы настроек (`panels.ConfigFilesPanel`)

Внизу окна — каждый файл из `memory_config.CONFIG_FILES` с путём (можно выделить и скопировать), кнопками «Открыть» (`QDesktopServices.openUrl` — открывается в текстовом редакторе по умолчанию; файлы в `/etc` принадлежат root, поэтому только для чтения) и «Показать в папке» (D-Bus `org.freedesktop.FileManager1.ShowItems` через `dbus-send` — Dolphin открывает папку с выделенным файлом; если не вышло — просто папка). Ещё не созданные файлы помечены «ещё не создан».

### Создание файла подкачки (`create_swap()`)

1. `swapoff <path>` — на случай если файл уже используется как swap (например, при пересоздании).
2. `touch <path>` — создать пустой файл.
3. `chattr +C <path>` — специальный атрибут файловой системы Btrfs: «No_COW» (без copy-on-write) именно для этого файла. Своп-файл на Btrfs без этого атрибута работает крайне плохо/может вообще не работать, потому что механизм copy-on-write (при любой записи создаётся новая версия блока, а не правится старая на месте) конфликтует с тем, как ядро использует swap-файл напрямую по фиксированным смещениям на диске. На других файловых системах (ext4 и т.п.) `chattr +C` просто не имеет эффекта — команда безопасна везде.
4. `dd if=/dev/zero of=<path> bs=1M count=<size_gb*1024> status=none` — `dd` копирует данные блоками; `if=/dev/zero` — источник, виртуальное «устройство», бесконечно отдающее нулевые байты; `bs=1M` — размер блока копирования 1 мегабайт (влияет только на скорость операции, не на результат); `count=<N>` — сколько таких блоков скопировать, то есть итоговый размер файла в мегабайтах; `status=none` — не печатать статистику копирования (иначе `dd` выводит прогресс, не нужный при фоновом вызове). Итог — файл нужного размера, полностью заполненный нулями.
5. `chmod 0600 <path>` — права «только владелец может читать и писать» — `swapon` в принципе откажется работать с файлом, чьи права шире (защита от того, что содержимое оперативной памяти, которое окажется в swap, сможет прочитать кто-то ещё).
6. `mkswap <path>` — записывает служебные структуры файловой системы swap (сигнатуру, размер) — без этого ядро не распознает файл как валидный swap, даже если он правильного размера.
7. `swapon <path>` — включает файл как активную область подкачки прямо сейчас.
8. Если выбрано «добавить в fstab» — дописывает строку `<path> none swap defaults 0 0`, чтобы своп включался автоматически при каждой загрузке (без строки в fstab своп работал бы только до перезагрузки).

### zram — сжатый swap в оперативной памяти (класс `ZramSetup`, `swap_backend.py`)

Устройство создаёт не само приложение, а штатный **zram-generator** (зависимость пакета). Приложение только пишет свой drop-in `/etc/systemd/zram-generator.conf.d/90-equestria-swap-manager.conf` с секцией `[zram0]`. Drop-in перекрывает одноимённые ключи основного `/etc/systemd/zram-generator.conf`, сам основной файл не трогается. Так zram-устройство всегда одно — `/dev/zram0`.

> Раньше (до 2.0.1-10) приложение создавало своё устройство через `zramctl --find` и службу `equestria-zram.service`. Если zram-generator уже держал `zram0`, получалось **два** zram-устройства (`zram0` + `zram1`), а при выключении `swapoff /dev/zram0` гасил чужое устройство вместо своего.

**Включение** (кнопка «Применить zram» — работает и на уже запущенном zram, меняя размер/алгоритм):
0. Запоминает текущий drop-in и был ли zram активен — для отката. Если любой следующий шаг упадёт, старый drop-in возвращается на место, старое устройство поднимается заново, а ошибка показывается пользователю — система не остаётся «наполовину переключённой».
1. Если осталась старая `equestria-zram.service` — `systemctl disable --now` и удаление файла юнита (её `ExecStop` сбрасывает все `/dev/zram*`, это нормально: `zram0` сразу пересоздаётся).
1a. Выключает и сбрасывает все **другие** zram-swap, кроме `zram0` (`swapoff` + `echo 1 > /sys/block/zramN/reset`).
2. Пишет drop-in: `zram-size = <N×1024>` (в МиБ), `compression-algorithm = <алгоритм>`, `swap-priority = 100` (выше дискового свопа — ядро сначала жмёт в RAM), `fs-type = swap`.
3. `systemctl daemon-reload` (генератор перечитывает конфиг) → **по очереди** `stop dev-zram0.swap` → `swapoff /dev/zram0` → `stop systemd-zram-setup@zram0.service` → `echo 1 > /sys/block/zram0/reset` → `systemctl start dev-zram0.swap`. Порядок важен: остановка обоих юнитов одной командой давала сброс раньше swapoff («Device or resource busy»), и новый алгоритм не применялся.
4. Выключает **zswap**: пишет `N` в `/sys/module/zswap/parameters/enabled` и `/etc/tmpfiles.d/equestria-swap-manager-zswap.conf`, чтобы это повторялось при каждой загрузке. zswap поверх zram сжимает те же страницы второй раз и держит в RAM свой пул (до 20% памяти).
5. `vm.page-cluster=0` — для zram (память, а не диск) чтение «кластерами» по несколько страниц только замедляет; `0` — читать по одной странице.

**Выключение (`ZramSetup.disable()`):** убирает старую службу (если есть) и лишние zram-устройства, пишет тот же drop-in с `zram-size = 0` (генератор тогда не создаёт устройство — даже если в основном конфиге оно описано), останавливает `dev-zram0.swap` и setup-юнит, и только после этого возвращает zswap (только если выключали его сами — есть наш tmpfiles-файл), `vm.page-cluster=3`, удаляет `99-zram.conf`.

## Прочее

* Ничего не запускается по расписанию/автоматически — только по явному действию в GUI (кроме уже созданного `equestria-zram.service`, который стартует при каждой загрузке, если zram был включён).
* `test_fstab_parse.py` — юнит-тесты для парсинга/генерации строк fstab, не часть рантайма приложения.
