#!/bin/bash
# Equestria OS — полная сборка и публикация репозитория
# Запускает сборку бинарников → makepkg → repo-add → git push
# Просто запусти и жди!

if [ ! -t 0 ]; then
    konsole -e bash "$0"
    exit
fi

BASE_DIR="/mnt/NewBaseD/FromSystem/Git Projects/equestria-packages"
REPO_DIR="$BASE_DIR/docs/x86_64"
DB_NAME="equestria-os.db.tar.gz"

# Все Python-проекты (те у кого есть PyInstaller бинарники)
PYTHON_PROJECTS=(
    "equestria-os-disk-manager"
    "equestria-os-swap-manager"
    "equestria-os-relocator"
    "equestria-os-tutorial"
    "equestria-os-git-askpass"
    "equestria-os-package-manager"
    "equestria-os-save-point"
    "equestria-os-services-manager"
    "equestria-os-software-center"
    "equestria-os-welcome-hub"
    "equestria-os-character-theme"
    "equstria-os-task-panel-changer"
    "equestria-os-builder"
    "proton-exe-starter"
    "equestria-os-rename-helper"
)

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   🐎 Equestria OS — Сборка и публикация              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Шаг 1: Сборка PyInstaller бинарников ──────────────────────────
echo "⚙️  Шаг 1/4 — Сборка бинарников..."
python "$BASE_DIR/build-binaries.py"

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Ошибка при сборке бинарников! Проверь вывод выше."
    read -rp "Нажми Enter чтобы выйти..."
    exit 1
fi

# ── Шаг 2: makepkg для Python-проектов ────────────────────────────
echo ""
echo "📦 Шаг 2/4 — Упаковка .pkg.tar.zst..."

FAILED=()
for proj in "${PYTHON_PROJECTS[@]}"; do
    proj_dir="$BASE_DIR/$proj"
    [ -f "$proj_dir/PKGBUILD" ] || continue

    pkgname=$(grep '^pkgname=' "$proj_dir/PKGBUILD" | cut -d= -f2)
    pkgver=$(grep '^pkgver=' "$proj_dir/PKGBUILD" | cut -d= -f2)
    pkgrel=$(grep '^pkgrel=' "$proj_dir/PKGBUILD" | cut -d= -f2)
    arch=$(grep '^arch=' "$proj_dir/PKGBUILD" | grep -o "'[^']*'" | head -1 | tr -d "'")
    echo "  → $pkgname-$pkgver-$pkgrel"

    cd "$proj_dir" || continue
    makepkg -f --nodeps --nocheck --noprogressbar --skippgpcheck 2>&1 \
        | grep -E "ERROR|WARN.*PKGBUILD|Finished|error:" \
        | grep -v "WARNING: Skipping"

    # Check result
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

# ── Шаг 3: Копирование пакетов и repo-add ─────────────────────────
echo ""
echo "🗃️  Шаг 3/4 — Обновление репозитория pacman..."

# Копируем все свежие .pkg.tar.zst (и Python, и остальные)
for dir in "$BASE_DIR"/*/; do
    [[ "$dir" == *"/docs/"* ]] && continue
    cp -u "$dir"*.pkg.tar.zst "$REPO_DIR/" 2>/dev/null
done

# Пересобираем базу данных с нуля
cd "$REPO_DIR" || exit 1
rm -f equestria.db equestria.db.tar.gz equestria.files equestria.files.tar.gz
repo-add "$DB_NAME" *.pkg.tar.zst

# ── Шаг 4: Публикация на GitHub ───────────────────────────────────
echo ""
echo "☁️  Шаг 4/4 — Отправка на GitHub..."

cd "$BASE_DIR" || exit 1
git add docs/x86_64/
git commit -m "Equestria OS repository auto-update: $(date +'%Y-%m-%d %H:%M')"
git push origin main

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✨ Готово! Репозиторий обновлён.                   ║"
echo "║   Через пару минут пакеты доступны для pacman -Syu   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
read -rp "Нажми Enter чтобы закрыть..."
