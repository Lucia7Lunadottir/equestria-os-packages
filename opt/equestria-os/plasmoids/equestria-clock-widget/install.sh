#!/bin/sh
# Установка виджета из исходников для проверки (обычно ставится пакетом equestria-clock-widget).
set -e
cd "$(dirname "$0")"
tmp=$(mktemp -d)
cp -r equestria-clock-widget/. "$tmp/"
for po in po/*.po; do
    lang=$(basename "$po" .po)
    mkdir -p "$tmp/contents/locale/$lang/LC_MESSAGES"
    msgfmt -o "$tmp/contents/locale/$lang/LC_MESSAGES/plasma_applet_org.equestria.clockwidget.mo" "$po"
done
kpackagetool6 -t Plasma/Applet -u "$tmp" 2>/dev/null || kpackagetool6 -t Plasma/Applet -i "$tmp"
rm -rf "$tmp"
echo "Готово. Правый щелчок по панели → Добавить виджеты → Часы Equestria"
