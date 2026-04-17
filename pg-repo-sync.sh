#!/bin/bash
# Equestria OS — быстрый бамп версий + публикация репозитория

if [ ! -t 0 ]; then
    konsole -e bash "$0"
    exit
fi

BASE_DIR="/mnt/NewBaseD/FromSystem/Git Projects/equestria-packages"
REPO_DIR="$BASE_DIR/docs/x86_64"
DB_NAME="equestria-os.db.tar.gz"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   🐎 Equestria OS — Обновление версий и публикация   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Шаг 1: Бамп pkgrel ────────────────────────────────────────────
echo "Пакеты с PKGBUILD:"
echo ""

PKGBUILDS=()
NAMES=()
i=1
for dir in "$BASE_DIR"/*/; do
    [[ "$dir" == *"/docs/"* ]] && continue
    pkgbuild="$dir/PKGBUILD"
    [ -f "$pkgbuild" ] || continue

    pkgname=$(grep '^pkgname=' "$pkgbuild" | cut -d= -f2)
    pkgver=$(grep '^pkgver=' "$pkgbuild" | cut -d= -f2)
    pkgrel=$(grep '^pkgrel=' "$pkgbuild" | cut -d= -f2)
    printf "  %2d) %-45s %s-%s\n" "$i" "$pkgname" "$pkgver" "$pkgrel"

    PKGBUILDS+=("$pkgbuild")
    NAMES+=("$pkgname")
    ((i++))
done

echo ""
echo "Введи номера пакетов через пробел чтобы поднять pkgrel,"
read -rp "или Enter чтобы пропустить: " bump_input

if [ -n "$bump_input" ]; then
    for idx in $bump_input; do
        pkgbuild="${PKGBUILDS[$((idx-1))]}"
        [ -f "$pkgbuild" ] || { echo "  ⚠️  Неверный номер: $idx"; continue; }

        pkgname="${NAMES[$((idx-1))]}"
        old_rel=$(grep '^pkgrel=' "$pkgbuild" | cut -d= -f2)
        new_rel=$((old_rel + 1))
        sed -i "s/^pkgrel=.*/pkgrel=$new_rel/" "$pkgbuild"
        echo "  ↑  $pkgname: pkgrel $old_rel → $new_rel"
    done
    echo ""
fi

# ── Шаг 2: makepkg ────────────────────────────────────────────────
echo "📦 Сборка пакетов..."
echo ""

FAILED=()
for dir in "$BASE_DIR"/*/; do
    [[ "$dir" == *"/docs/"* ]] && continue
    [ -f "$dir/PKGBUILD" ] || continue

    pkgname=$(grep '^pkgname=' "$dir/PKGBUILD" | cut -d= -f2)
    pkgver=$(grep '^pkgver=' "$dir/PKGBUILD" | cut -d= -f2)
    pkgrel=$(grep '^pkgrel=' "$dir/PKGBUILD" | cut -d= -f2)
    echo "  → $pkgname-$pkgver-$pkgrel"

    cd "$dir" || continue
    makepkg -f --nodeps --nocheck --noprogressbar --skippgpcheck 2>&1 \
        | grep -E "ERROR|error:" | grep -v "WARNING: Skipping"

    pkg_file=$(ls "${pkgname}-${pkgver}-${pkgrel}-"*.pkg.tar.zst 2>/dev/null | head -1)
    if [ -z "$pkg_file" ]; then
        echo "    ❌ Не удалось собрать $pkgname"
        FAILED+=("$pkgname")
    fi
done

if [ ${#FAILED[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  Не собрались: ${FAILED[*]}"
    read -rp "Продолжить несмотря на ошибки? (y/N): " cont
    [[ "$cont" =~ ^[Yy]$ ]] || exit 1
fi

# ── Шаг 3: repo-add ───────────────────────────────────────────────
echo ""
echo "🗃️  Обновление репозитория pacman..."

cp -u "$BASE_DIR"/*.pkg.tar.zst "$REPO_DIR/" 2>/dev/null
for dir in "$BASE_DIR"/*/; do
    [[ "$dir" == *"/docs/"* ]] && continue
    cp -u "$dir"*.pkg.tar.zst "$REPO_DIR/" 2>/dev/null
done

cd "$REPO_DIR" || exit 1
rm -f equestria.db equestria.db.tar.gz equestria.files equestria.files.tar.gz
repo-add "$DB_NAME" *.pkg.tar.zst

# ── Шаг 4: Публикация ─────────────────────────────────────────────
echo ""
echo "☁️  Отправка на GitHub..."

cd "$BASE_DIR" || exit 1
git add docs/x86_64/
git commit -m "Equestria OS repository auto-update: $(date +'%Y-%m-%d %H:%M')"
git push origin main

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✨ Готово! Репозиторий обновлён.                   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
read -rp "Нажми Enter чтобы закрыть..."
