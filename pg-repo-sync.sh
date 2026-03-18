#!/bin/bash

if [ ! -t 0 ]; then
    konsole -e bash "$0"
    exit
fi

echo "🐎 Запуск автоматического обновления репозитория Equestria OS..."

BASE_DIR="$HOME/equestria-packages"
REPO_DIR="$BASE_DIR/docs/x86_64"
DB_NAME="equestria.db.tar.gz"

cd "$BASE_DIR" || exit

# 1. Собираем свежие пакеты из соседних папок (игнорируя папку docs)
echo "📦 Поиск и копирование новых пакетов..."
for dir in "$BASE_DIR"/*/; do
    if [[ "$dir" != *"/docs/"* ]]; then
        # Копируем только новые или обновленные файлы (-u)
        cp -u "$dir"*.pkg.tar.zst "$REPO_DIR/" 2>/dev/null
    fi
done

# 2. Обновляем базу данных (витрину)
echo "🗃️ Обновление базы данных Pacman..."
cd "$REPO_DIR" || exit

# Удаляем старые индексы, чтобы repo-add собрал всё начисто
rm -f equestria.db equestria.db.tar.gz equestria.files equestria.files.tar.gz

# Добавляем все пакеты в базу
repo-add "$DB_NAME" *.pkg.tar.zst

# 3. Отправка на GitHub
echo "☁️ Отправка обновления на GitHub..."
cd "$BASE_DIR" || exit
git add docs/x86_64/
git commit -m "Equestria OS repository auto-update: $(date +'%Y-%m-%d %H:%M')"
git push origin main

echo "✨ Готово! Репозиторий обновлен. Через пару минут пакеты будут доступны для pacman -Syu."
