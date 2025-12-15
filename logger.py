#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler

LOG_FILE = 'app.log'
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

# Создаем logger
logger = logging.getLogger('VideoDownloader')
logger.setLevel(logging.DEBUG)

# Очищаем файл при первом запуске
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w') as f:
        f.write('')  # Очищаем файл

# Создаем форматтер
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Файловый handler с ротацией
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=MAX_BYTES,
    backupCount=BACKUP_COUNT,
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Консольный handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Добавляем handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)


def clean_ansi_codes(text):
    """Удаляет ANSI escape коды из текста"""
    if not text:
        return text
    # Удаляем ANSI escape последовательности
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', str(text))


def log_frontend_error(error_type, message, stack='', timestamp=''):
    """Логирование ошибок с фронтенда"""
    message = clean_ansi_codes(message)
    stack = clean_ansi_codes(stack)
    log_msg = f"[FRONTEND] {error_type}: {message}"
    if stack:
        log_msg += f"\nStack trace:\n{stack}"
    logger.error(log_msg)


def log_info(message):
    """Логирование информационных сообщений"""
    logger.info(clean_ansi_codes(message))


def log_error(message):
    """Логирование ошибок"""
    logger.error(clean_ansi_codes(message))


def log_warning(message):
    """Логирование предупреждений"""
    logger.warning(clean_ansi_codes(message))


def log_debug(message):
    """Логирование отладочных сообщений"""
    logger.debug(clean_ansi_codes(message))

