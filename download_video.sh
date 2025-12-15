#!/bin/bash
# Активируем виртуальное окружение
source /home/ta3map/Documents/DownloadVideo/DVenv/bin/activate

# Запускаем питоновский скрипт
python3 /home/ta3map/Documents/DownloadVideo/download_video.py

# (Опционально) Деактивируем окружение после выполнения скрипта
deactivate

