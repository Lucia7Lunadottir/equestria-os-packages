#!/bin/bash

# Переходим в папку со скриптом
cd "$(dirname "$0")" || exit 1

# Запускаем Konsole, который внутри себя выполнит desktop_editor_ui.py
python3 desktop_editor_ui.py
