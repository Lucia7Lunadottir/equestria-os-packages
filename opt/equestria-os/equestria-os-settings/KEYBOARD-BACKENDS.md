# Подсветка клавиатуры у разных брендов: что известно

Собрано 23.11.2026 из первоисточников (документация ядра, README проектов, исходник драйвера).
Метки: **[док]** — прочитано в документации; **[код]** — прочитано в исходнике драйвера;
**[нет данных]** — страницу не удалось прочитать или в ней этого нет (не домысливать).
Железо, на котором всё проверено вживую: только **ASUS TUF Gaming F15 (FX507VV)**.

## 1. Общий интерфейс ядра (самое важное)

Стандартный класс светодиодов ядра, у цветных — «multicolor» (`/sys/class/leds/<имя>/`):

| Файл | Смысл |
|---|---|
| `brightness`, `max_brightness` | общая яркость (0…max) |
| `multi_index` | порядок цветов, например `green blue red` (произвольный) |
| `multi_intensity` | интенсивность каждого цвета; «все элементы нужно записать сразу» |
| `multi_max_intensity` | максимум по цвету; больше — обрезается |

Формула [док]: `яркость_светодиода = brightness * multi_intensity / max_brightness`.
Имя светодиода клавиатуры [док]: заканчивается на `:kbd_backlight` (одна зона); у многозонных —
`…:kbd_zoned_backlight-<зона>`; клавиатуры с подсветкой отдельных клавиш LED-класс использовать **не должны**.
Права [док]: файлы принадлежат root (запись только владельцу): обычному пользователю нужен udev-правило
или привилегированный помощник. Общей готовой udev-строки в документации нет.

## 2. По брендам

| Бренд / драйвер | Что даёт | Цвет? | Источник |
|---|---|---|---|
| **ASUS TUF/ROG** (`asus-wmi`) | `kbd_rgb_mode` (команда «режим R G B скорость») + яркость | да, 4 эффекта проверены | [код] ядро; проверено на железе |
| **ASUS ROG с USB/I2C-клавиатурой** | `asusctl` + `asusd` | да (эффекты Stars, Rain…) | [док] `asusctl --help`; **не проверено на ROG** |
| **Uniwill / TUXEDO / часть Tongfang** (`uniwill-laptop`) | светодиод `uniwill:rgb:kbd_backlight`; макс. интенсивность канала 50; чёрный `000000` невозможен (станет `010101`), выключение — яркостью | да (RGB) | [док] kernel docs; имена файлов в ABI не читали |
| **TUXEDO** (`tuxedo-drivers`, DKMS) | модули `clevo_*`, `ite_829x`, `tuxedo_nb0x_kbd_backlight`; яркость по D-Bus UPower | пути sysfs не описаны | [док] README; **цвет не подтверждён** |
| **System76** (`system76_acpi`) | `/sys/class/leds/system76_acpi::kbd_backlight/` (`brightness` до 255) и файл `color` — 6 hex-цифр `RRGGBB`, макс. `FFFFFF` | да, один цвет | [код] исходник драйвера (путь к `color` выведен из кода) |
| **Lenovo Legion** | драйвер `legion_laptop` клавиатуру RGB **не** красит; в проекте советуют L5P-Keyboard-RGB или OpenRGB | через сторонние программы | [док] LenovoLegionLinux docs |
| **Lenovo LG gram** (`lg-laptop`) | светодиод `kbd_led`: 0 / 127 / 255 | нет | [док] kernel docs |
| **MSI** (`msi-ec`, DKMS) | `/sys/class/leds/msiacpi::kbd_backlight/brightness`, 0–3 | нет | [док] README |
| **Samsung Galaxy Book** | `samsung-galaxybook::kbd_backlight`, только `brightness` | нет | [док] kernel docs |
| **ThinkPad** (`thinkpad-acpi`) | на странице ядра раздела о подсветке нет [док]; на практике подсветка — светодиод `tpacpi::kbd_backlight` (знание автора, не из этих страниц) | нет | [нет данных] |
| **Razer** (`openrazer`, DKMS) | собственный демон + D-Bus + библиотека Python; пользователь в группе `plugdev` | да (много эффектов) | [док] сайт проекта; имена атрибутов не подтверждены |
| **Dell/Alienware** | страница `alienware-wmi` про подсветку клавиатуры ничего не говорит | [нет данных] | [док] |
| **HP / Omen, Acer, Framework** | в документации ядра нет страниц | [нет данных] | — |

## 3. Универсальный путь: OpenRGB

OpenRGB (GPL-2.0) — отдельная программа и сетевой SDK для RGB-устройств; есть библиотеки для Python и др.
(`openrgb-python`, автор jath03). udev-правила `60-openrgb.rules` OpenRGB генерирует сам
(`openrgb --generate-udev-rules`). **Не удалось прочитать:** порт и протокол SDK, примеры Python-клиента,
таблицу поддерживаемых ноутбуков (страницы 404 или не отрисовались). Это нужно перепроверить перед работой.

## 4. Предлагаемая структура кода (по файлу на способ управления)

```
modules/kbd_lighting/
    base.py              Effect, RgbSetting, абстрактный бэкенд (общее, без железа)
    asus_wmi.py          ASUS TUF/ROG через ядро            (проверено)
    asusctl.py           ASUS ROG через asusd               (не проверено)
    kernel_multicolor.py любой *:kbd_backlight с multi_intensity (uniwill, часть TUXEDO)   (экспериментально)
    system76.py          system76_acpi, файл color          (экспериментально)
    openrgb.py           через сервер OpenRGB               (после проверки протокола)
```

Правила: один файл — один способ управления; страница, служба темы и редактор о конкретном бренде не знают;
общие бэкенды (без встроенных эффектов) умеют только статичный цвет; каждый новый бэкенд помечен
«экспериментальный», пока не проверен на реальном ноутбуке, и покрыт тестом на поддельном дереве `/sys`.
Запись в `multi_intensity` / `color` требует прав root: помощник `pg-kbd-rgb-helper` получает
для этого отдельные строго проверяемые команды (имя светодиода по шаблону, значения в пределах максимума).

## 5. Как добавить бэкенд (один файл)

1. Создать `modules/kbd_lighting/<имя>.py` с одним классом-наследником `RgbBackend`.
2. Заполнить признаки: `id`, `priority` (меньше — раньше пробуется), `experimental` (True, пока не проверено на реальном
   ноутбуке), `firmware_save` (умеет ли ноутбук запомнить вид сам), `can_unlock_direct_access` (действует ли правило udev).
3. Реализовать `detect(access)` (вернуть экземпляр, если железо есть), `effects()`, `apply(setting, save)`, `silent`.
4. Писать в файлы только через `access.write_led_attr(...)`: она сама решит, писать напрямую или через помощника root.
   Если нужен новый файл — добавить его имя и формат значения в `pg-kbd-rgb-helper` (проверка там строгая).
5. Тест на поддельном дереве `/sys` в `tests/test_backends.py`. Страница, служба темы и редактор менять **не нужно**:
   бэкенд находится сам.

Что уже есть: `asus_wmi` (проверен), `asusctl`, `kernel_multicolor`, `system76` (три последних — экспериментальные).
Без встроенных эффектов (multicolor, system76) доступен только статичный цвет; вид возвращает при входе служба
`pg-kbd-restore` (запоминание цвета самим ноутбуком там не предусмотрено).

## 6. Ссылки (прочитаны)

- https://docs.kernel.org/leds/leds-class-multicolor.html
- https://docs.kernel.org/leds/leds-class.html
- https://docs.kernel.org/admin-guide/laptops/uniwill-laptop.html
- https://docs.kernel.org/admin-guide/laptops/lg-laptop.html
- https://docs.kernel.org/admin-guide/laptops/samsung-galaxybook.html
- https://docs.kernel.org/admin-guide/laptops/alienware-wmi.html
- https://docs.kernel.org/admin-guide/laptops/thinkpad-acpi.html
- https://github.com/pop-os/system76-acpi-dkms/blob/master/system76_acpi.c
- https://github.com/tuxedocomputers/tuxedo-drivers
- https://github.com/johnfanv2/LenovoLegionLinux/blob/main/docs/usage.md
- https://github.com/openrazer/openrazer
- https://openrgb.org/sdk.html , https://openrgb.org/udev.html
- Не открылись (404): wiki SDK OpenRGB; `hirschmann/ite8291r3-ctl` (проект мог переехать).
