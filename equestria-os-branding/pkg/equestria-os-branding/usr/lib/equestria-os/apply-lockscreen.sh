#!/bin/bash
# Equestria OS: тонкая подстройка lockscreen поверх plasma-desktop.
# Раньше сюда копировались целые QML-файлы старой версии, и после апдейта
# Plasma они затирали новые (экран блокировки ломался). Теперь файлы
# plasma-desktop остаются родными, а мы только дописываем одну строку —
# белый цвет текста. Скрипт идемпотентен и безопасен: если структура
# файла изменилась, он ничего не делает.

UI="/usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml"
[ -f "$UI" ] || exit 0
grep -q 'Equestria OS: белый текст' "$UI" && exit 0

sed -i '0,/^    Kirigami\.Theme\.colorSet: Kirigami\.Theme\.Complementary$/s//&\n    Kirigami.Theme.textColor: "#ffffff" \/\/ Equestria OS: белый текст/' "$UI"
exit 0
