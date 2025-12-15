#!/bin/bash
# Активируем виртуальное окружение
source venv/bin/activate

echo "Запуск Flask приложения..."
echo "Лог сохраняется в: app.log"
echo ""

# Запускаем Flask приложение с webview
python app.py

# Сохраняем код возврата
EXIT_CODE=$?

# Деактивируем окружение
deactivate

# Если была ошибка, выводим информацию
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "=========================================="
    echo "ОШИБКА! Код возврата: $EXIT_CODE"
    echo "Полный лог сохранен в: app.log"
    echo "Последние строки лога:"
    echo "=========================================="
    tail -20 app.log
    echo "=========================================="
    exit $EXIT_CODE
fi

