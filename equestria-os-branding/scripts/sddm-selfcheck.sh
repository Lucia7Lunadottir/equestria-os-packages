#!/bin/bash
# Equestria OS: самопроверка SDDM-темы после обновлений.
# Загружает нашу тему в тестовом режиме без экрана (offscreen). Если QML не
# загрузился (как после перехода Plasma 6.7 -> 6.8, когда SDDM молча уходил
# на встроенную тему), включает запасной Breeze через drop-in. Когда тема
# снова исправна, drop-in удаляется.
# Использование: sddm-selfcheck.sh [каталог_темы]

THEME_NAME="equestria-os-breeze"
THEME_DIR="${1:-/usr/share/sddm/themes/$THEME_NAME}"
FALLBACK_CONF="/etc/sddm.conf.d/zz-equestria-fallback.conf"
BAD='is not a type|is not installed|Fallback to embedded|ReferenceError|TypeError|Cannot assign|Type .* unavailable|Cannot open: file://'

command -v sddm-greeter-qt6 >/dev/null || exit 0
[ -f "$THEME_DIR/Main.qml" ] || { problems="нет Main.qml"; }

if [ -z "$problems" ]; then
    out=$(QT_FORCE_STDERR_LOGGING=1 QT_QPA_PLATFORM=offscreen \
          timeout 6 sddm-greeter-qt6 --test-mode --theme "$THEME_DIR" 2>&1)
    problems=$(printf '%s\n' "$out" | grep -E "$BAD" | head -5)
fi

if [ -n "$problems" ]; then
    msg="Тема SDDM $THEME_NAME не загружается, включён запасной Breeze: $(printf '%s' "$problems" | head -1)"
    logger -t equestria-os-sddm "$msg"
    echo "equestria-os-sddm: $msg" >&2
    if [ "$THEME_DIR" = "/usr/share/sddm/themes/$THEME_NAME" ]; then
        install -d /etc/sddm.conf.d
        printf '# Создано equestria-os-sddm-selfcheck: тема не прошла проверку\n[Theme]\nCurrent=breeze\n' > "$FALLBACK_CONF"
    fi
    exit 0
fi

# Тема исправна: запасной вариант больше не нужен
[ "$THEME_DIR" = "/usr/share/sddm/themes/$THEME_NAME" ] && rm -f "$FALLBACK_CONF"
exit 0
