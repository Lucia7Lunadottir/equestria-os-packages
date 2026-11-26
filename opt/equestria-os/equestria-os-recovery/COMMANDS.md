# equestria-os-recovery — как устроено

Среда восстановления на диске: live-ISO Equestria OS лежит файлом (в `/var/lib/equestria-recovery/`
или на другом разделе), GRUB грузит его через `loopback`, мастер в live-среде сам находит и чинит
установленную систему. Флешка не нужна. Как в Windows: после неудачных загрузок подряд GRUB сам
открывает восстановление. Установщик кладёт ISO сразу — с той же флешки.

## Две половины

| Где | Окно | Root-часть |
|---|---|---|
| Установленная система | `recovery_manager.py` → `RecoveryManagerApp` (и страница Настроек `mod_recovery`) | `recovery_backend.py` через **pkexec** |
| Live-среда (флешка или пункт GRUB) | `recovery_wizard.py` → `RescueWizard` | `recovery_rescue.py` через **sudo -n** (liveuser без пароля) |

`recovery_app.py` выбирает окно: в live (`/run/archiso` есть) — мастер, иначе — менеджер; `--wizard` — мастер всегда.
`--autostart` (из `/etc/xdg/autostart/equestria-os-recovery-live.desktop`) открывает мастер **только** если в
`/proc/cmdline` есть `equestria.recovery=1`, то есть загрузились через пункт «Восстановление»; обёртка
`/usr/bin/equestria-recovery` проверяет это ещё до запуска Python.

## Модули

- `recovery_paths.py` — все пути и имена (единственный источник).
- `recovery_image.py` — `IsoInspector` (bsdtar, без монтирования: `boot/grub/loopback.cfg`, `arch/version`,
  размер `airootfs.sfs`; выбирает LTS-ядро, если оно есть), `RecoveryState` (`state.json`), `ImageStatus`, `copytoram_fits`.
- `recovery_grub.py` — `IsoLocation.probe` (grub-probe/grub-mkrelpath; LUKS → отказ), `EntryRenderer` (текст
  `equestria-recovery.cfg`), `GrubIntegration` (запись пункта, блок в grub.cfg, разовый переход).
- `recovery_source.py` — `ReleaseFeed` (RSS SourceForge: имя, размер, md5), `Downloader` (в `~/.cache/equestria-os-recovery`,
  от пользователя, докачка по Range, проверка размера и md5).
- `recovery_storage.py` — `StorageLocations` (куда можно положить ISO: системный раздел или раздел из
  fstab на ext*/Btrfs/XFS, без LUKS/LVM/RAID), `env_location()` (куда GRUB может писать файл окружения).
- `recovery_livemedia.py` — `LiveMedium` (откуда запущена live-среда: ISO-файл или флешка; точный размер
  ISO на флешке — по резервному заголовку GPT образа), `RootfsVerifier` (airootfs.sfs против airootfs.sha512).
- `recovery_backend.py` — `install | refresh | remove | location | auto | one-shot | clear-one-shot | boot-ok |
  import-live`.
- `recovery_rescue.py` — `scan | fscheck | mount | diagnose | fix | umount`; проверки — подклассы `Check`, исправления — `Fix`.
- `recovery_widgets.py` — переводы (`live_i18n`, `locales/*.json`, 12 языков, смысловые ключи), карточки, `PrivilegedTask` (QProcess).

## GRUB

- Пункты — в `/boot/grub/equestria-recovery.cfg` (переписывается при каждой установке образа).
- В `grub.cfg` **один раз дописывается** блок между `### BEGIN/END equestria-recovery ###`, который делает
  `source` этого файла, если он есть. Меню системы не пересобирается (`grub-mkconfig` не вызывается);
  копия до правки — `grub.cfg.before-equestria-recovery`. `/etc/grub.d/42_equestria-recovery` выдаёт тот же
  блок, чтобы он пережил следующий `grub-mkconfig`.
- Два пункта: с `copytoram=y` (образ копируется в память, раздел отпускается → можно `fsck` и переустановка) и
  `copytoram=n` («мало памяти»). Первым идёт тот, на который хватает памяти: `airootfs.sfs ≤ 75 % ОЗУ` и остаётся ≥ 2 ГиБ.
- Параметры: `img_dev=UUID=… img_loop=<путь от корня ФС>` (хук `archiso_loop_mnt` initramfs образа),
  для Btrfs ещё `img_flags=subvolid=5` (путь от верхнего тома, как его видит GRUB), `equestria.recovery=1` и
  остальные параметры из `loopback.cfg` самого ISO.
- Названия пунктов — на языке окна; не-латиница только если `grub.cfg` грузит шрифт (`loadfont`/`theme`),
  иначе английские. Для ja/ko/zh в переводах сразу английские (в шрифтах GRUB обычно нет CJK).
- Своё окружение GRUB — `equestria-recovery.env`: в `/boot/grub`, если GRUB может туда писать (ext2/3/4
  или FAT без LUKS/LVM/RAID), иначе на EFI-разделе (`EFI/equestria-recovery/`). Поэтому всё ниже работает
  и при корне на Btrfs/XFS. Нет ни того, ни другого (BIOS + Btrfs) — кнопка и автозапуск выключены с пояснением.
- «Перезагрузиться в восстановление»: `equestria_recovery_once=1`; код в `equestria-recovery.cfg` при
  загрузке ставит `default` на пункт и сам стирает флаг (`save_env`).
- **Автозапуск после неудачных загрузок.** `equestria-recovery.cfg` переопределяет функцию `load_video`
  (тело берётся из `grub.cfg` системы) — её вызывает каждый пункт 10_linux, а Windows и прочие нет.
  Каждый вызов: `eqrec_fails` +1 (цепочкой `if`, GRUB не умеет складывать; потолок 9).
  Служба `equestria-recovery-boot-ok` (multi-user.target, то есть Emergency Mode и сбой initramfs сюда
  не доходят) и хук `/usr/lib/systemd/system-sleep/equestria-recovery` (выход из гибернации тоже идёт
  через GRUB) обнуляют счёт. `eqrec_fails ≥ eqrec_limit` → GRUB выбирает восстановление, показывает
  меню (timeout 0 → 10) и передаёт `equestria.recovery_reason=auto` — мастер объясняет, что случилось.
  Пункт восстановления сам обнуляет счёт. `eqrec_limit`: 2; 4, если Save Point откатывает систему
  (Btrfs, `equestria-boot-guard` включён) — его откат на 3-й неудаче получает шанс; 0 — выключено
  галочкой в окне. Пишет предел служба при каждой загрузке. Если пункты Linux не вызывают
  `load_video` (`GRUB_GFXPAYLOAD_LINUX=text`) — счётчика нет, окно это показывает.

Проверено в QEMU (OVMF, 26.11): флаг переключает выбор на пункт восстановления и стирается; следующая
загрузка — обычная; ядро/initramfs из ISO, раздел найден по UUID, copytoram, live-сессия до SDDM.

## Где хранить ISO

Окно («Где хранить образ») предлагает системный раздел и разделы из fstab, которые подключены сейчас
(ext*/Btrfs/XFS, не LUKS/LVM/RAID, FAT — нет: файл больше 4 ГиБ). Раздел на другом физическом диске
помечен. Образ там — в `<точка>/.equestria-recovery/` (root:root 0755); бэкенд работает через
дескриптор папки с `O_NOFOLLOW` и проверяет владельца. `location <ключ>` переносит готовый образ
(копия → пункт GRUB → удаление старого); если GRUB новое место не прочитал — всё возвращается назад.

На системном разделе: если он не монтируется даже на чтение или повреждены блоки самого ISO — среда не
загрузится (нужна флешка); в режиме «мало памяти» раздел занят: `fsck` недоступен, переустановка
заблокирована. На другом разделе этих ограничений нет.

## Установщик (Calamares)

`shellprocess@recoveryimage` (после `installgrub`, вне chroot):
`equestria-recovery-backend import-live --root ${ROOT}` — копирует ISO, с которого идёт установка
(флешка: читается ровно образ; ISO-файл, в том числе с раздела, отключённого copytoram), сверяет
airootfs.sha512, пишет `state.json` и в chroot — `refresh`. Нужно ≥ 10 ГиБ свободного места сверх образа.
Любая неудача установку не прерывает (`-` перед командой). Ярлык мастера на рабочем столе live-среды
`shellprocess@cleanup` из новой системы убирает.

## Ограничения

- Btrfs мастер только проверяет (`btrfs check --readonly`, `scrub`), автоматически не ремонтирует.
- Мастер — часть **нового** ISO: в образах до добавления пакета в `packages.x86_64` пункт GRUB загрузит
  обычную live-среду без мастера.

## Проверки и исправления мастера (`recovery_rescue.py`)

| Check | Находит | Fix |
|---|---|---|
| `MountCheck` | раздел из fstab (/boot, /boot/efi…) не смонтировался | — |
| `FreeSpaceCheck` | `/` < 2 ГиБ, `/boot` < 150 МиБ | `clean-cache` (`pacman -Sc`), `remove-fallback` |
| `PacmanLockCheck` | `db.lck` | `unlock` |
| `KernelCheck` | нет/не совпадает `/boot/vmlinuz-*` с `/usr/lib/modules/*/vmlinuz`, нет `modules.dep`, initramfs пустой или битый (`lsinitcpio -a`) | `rebuild-boot`: `depmod`, ядро `cp --reflink=never --sparse=never`, `mkinitcpio -P` |
| `BootloaderCheck` | только если стоит пакет grub: нет `grub.cfg`, нет GRUB на ESP | `repair-grub`: `grub-install` (+ `--removable`, если EFI/BOOT был GRUB), `grub-mkconfig` |
| `PackageFilesCheck` | `pacman -Qk`: пропавшие файлы (кроме doc/man/locale), `pacman -Dk` | `reinstall`: `pacman -Syu <пакеты>` (сеть) |

Вне проверок: `finish-update` (`pacman -Syu`), терминал (`konsole -e sudo arch-chroot`), файлы, переустановка
(`/usr/local/bin/install-equestria.sh` после `umount`), перезагрузка. `fscheck` до монтирования: ext* `e2fsck -f -n`,
при ошибках по согласию `e2fsck -f -y`.

## Тесты

- `python3 tests/test_recovery.py` — без root и сети: синтаксис GRUB (`grub-script-check`, с контролем на
  битый файл), счётчик в cfg, разбор `load_video`, файл окружения, размер ISO на флешке (и на собранных ISO),
  сверка sha512 (целый/испорченный образ), порядок пунктов по памяти, лента, загрузка с
  обрывом/докачкой/неверным md5/отменой, проверки движка на поддельном корне.
- `python3 tests/sandbox_backend.py` — бэкенд целиком в `unshare -r` (root только для себя, пути во
  временной папке): установка, отказ испорченного образа, перенос туда-обратно, откат переноса, папка-ссылка,
  boot-ok/auto, удаление, импорт с «флешки» с мусором после образа.
- `python3 tests/vm_grub_counter.py` — настоящий GRUB в QEMU+OVMF (~2 мин): 2 неудачи → восстановление и
  меню видно; удачная загрузка сбрасывает; Windows не считается; разовый флаг; предел 0.
