#!/bin/bash
# Переходим в директорию, где лежит сам скрипт
cd "$(dirname "$0")"
# Запускаем python для rename_app.py в этой же папке
python3 rename_app.py
