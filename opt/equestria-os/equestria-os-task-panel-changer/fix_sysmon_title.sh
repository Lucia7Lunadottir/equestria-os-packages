#!/bin/bash
# Миграция заголовка виджета памяти (системный монитор на панели).
#
# KDE записывает заголовок виджета в конфиг ОДИН РАЗ при его создании —
# сырой строкой на языке, активном в тот момент, — и при смене языка
# системы не переводит его. Скрипт при каждом логине ищет такой
# запечённый заголовок (на любом из поддерживаемых языков) и заменяет
# его на локализуемый блок Title/Title[xx], который KConfig выбирает
# по текущему языку сам. После замены совпадений нет — скрипт при
# следующих логинах мгновенно выходит на первом grep.

CFG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
[ -f "$CFG" ] || exit 0

TITLES=(
    "Memory Usage"
    "Speicherauslastung"
    "Uso de la memoria"
    "Utilisation de la mémoire"
    "メモリ使用量"
    "Użycie pamięci"
    "Utilização da memória"
    "Использование памяти"
    "Використання пам'яті"
    "内存使用"
)

need_fix=0
for t in "${TITLES[@]}"; do
    if grep -qF "title=$t" "$CFG"; then
        need_fix=1
        break
    fi
done
[ "$need_fix" -eq 0 ] && exit 0

REPLACEMENT='Title=Memory Usage\nTitle[de]=Speicherauslastung\nTitle[es]=Uso de la memoria\nTitle[fr]=Utilisation de la mémoire\nTitle[ja]=メモリ使用量\nTitle[pl]=Użycie pamięci\nTitle[pt]=Utilização da memória\nTitle[ru]=Использование памяти\nTitle[uk]=Використання пам'"'"'яті\nTitle[zh_CN]=内存使用'

apply_fix() {
    local t
    for t in "${TITLES[@]}"; do
        sed -i "s|^title=$t\$|$REPLACEMENT|" "$CFG"
    done
}

# Даём сессии полностью подняться, затем перезапускаем plasmashell,
# правя конфиг строго между остановкой и запуском (иначе оболочка
# перезапишет файл своей копией из памяти).
sleep 10

if command -v systemctl >/dev/null 2>&1 \
        && systemctl --user is-active --quiet plasma-plasmashell.service; then
    systemctl --user stop plasma-plasmashell.service 2>/dev/null
    sleep 1.5
    apply_fix
    systemctl --user start plasma-plasmashell.service 2>/dev/null
else
    kquitapp6 plasmashell 2>/dev/null
    sleep 1.5
    apply_fix
    nohup plasmashell >/dev/null 2>&1 &
    disown
fi

exit 0
