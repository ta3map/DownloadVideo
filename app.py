#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify
import threading
import time
import json
import uuid
import os
import sys
from io import StringIO
os.environ['WEBVIEW_BACKEND'] = 'qt'
import webview
from video_downloader import (
    get_formats, download_video, get_default_download_dir,
    CustomLogger, check_ffmpeg
)
from logger import log_frontend_error, log_info, log_error, log_warning, log_debug
from database import Database

app = Flask(__name__)

# Хранилище активных задач (только для форматов)
tasks = {}
tasks_lock = threading.Lock()

# База данных
db = Database()

# Папка загрузки по умолчанию
DOWNLOAD_FOLDER = get_default_download_dir()

# Активные загрузки из очереди
active_tasks = {}
active_tasks_lock = threading.Lock()


def get_task(task_id):
    """Безопасное получение задачи"""
    with tasks_lock:
        return tasks.get(task_id)


def update_task(task_id, **kwargs):
    """Безопасное обновление задачи"""
    with tasks_lock:
        if task_id in tasks:
            tasks[task_id].update(kwargs)


def create_task():
    """Создает новую задачу и возвращает её ID"""
    task_id = str(uuid.uuid4())
    with tasks_lock:
        tasks[task_id] = {
            'status': 'idle',  # idle, fetching, downloading, paused, cancelled, finished, error
            'progress': 0,
            'final_file': None,
            'url': '',
            'format_id': None,
            'audio_only': False,
            'paused': False,
            'cancelled': False,
            'error': None,
            'thread': None
        }
    return task_id


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/api/fetch-formats', methods=['POST'])
def fetch_formats():
    """Получение списка форматов для URL"""
    data = request.json
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL не указан'}), 400
    
    task_id = create_task()
    update_task(task_id, status='fetching', url=url)
    
    def worker():
        try:
            result = get_formats(url)
            update_task(task_id, status='idle', formats=result['formats'], title=result['title'])
        except Exception as e:
            log_error(f"Error fetching formats for task {task_id}: {e}")
            update_task(task_id, status='error', error=str(e))
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    update_task(task_id, thread=thread)
    
    return jsonify({'task_id': task_id})


@app.route('/api/get-formats/<task_id>', methods=['GET'])
def get_formats_result(task_id):
    """Получение результата получения форматов"""
    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    if task['status'] == 'error':
        return jsonify({'error': task.get('error', 'Неизвестная ошибка')}), 500
    
    if task['status'] == 'idle' and 'formats' in task:
        return jsonify({
            'formats': task['formats'],
            'title': task.get('title', '')
        })
    
    return jsonify({'status': task['status']})


def start_queue_download(queue_id, queue_item):
    """Запуск загрузки из очереди"""
    url = queue_item['url']
    format_id = queue_item['format_id']
    audio_only = bool(queue_item['audio_only'])
    download_folder = queue_item['download_folder']
    title = queue_item.get('title', '')
    
    if not title:
        result = get_formats(url)
        title = result.get('title', '')
    
    task_id = str(uuid.uuid4())
    db.update_queue_item(queue_id, status='downloading', task_id=task_id)
    
    paused_flag = {'value': False}
    cancelled_flag = {'value': False}
    final_file = ['']
    
    with active_tasks_lock:
        active_tasks[task_id] = {
            'queue_id': queue_id,
            'url': url,
            'title': title,
            'format_id': format_id,
            'audio_only': audio_only,
            'progress': 0,
            'paused': False,
            'paused_flag': paused_flag,
            'cancelled_flag': cancelled_flag
        }
    
    def progress_callback(percent):
        with active_tasks_lock:
            active_tasks[task_id]['progress'] = percent
    
    def final_file_callback(filename):
        final_file[0] = filename
    
    logger = CustomLogger(final_file_callback=final_file_callback)
    
    def worker():
        try:
            download_video(
                url=url,
                format_id=format_id,
                download_folder=download_folder,
                audio_only=audio_only,
                progress_callback=progress_callback,
                logger=logger,
                paused_flag=paused_flag,
                cancelled_flag=cancelled_flag,
                final_file_callback=final_file_callback
            )
            with active_tasks_lock:
                del active_tasks[task_id]
            db.add_to_history(url, title, format_id, audio_only, 'finished', final_file[0])
            db.update_queue_item(queue_id, status='finished')
            start_next_queue_item()
        except Exception as e:
            with active_tasks_lock:
                if task_id in active_tasks:
                    del active_tasks[task_id]
            status = 'cancelled' if 'cancelled' in str(e).lower() else 'error'
            db.add_to_history(url, title, format_id, audio_only, status, '')
            db.update_queue_item(queue_id, status=status)
            start_next_queue_item()
    
    threading.Thread(target=worker, daemon=True).start()

def start_next_queue_item():
    """Запуск следующего элемента из очереди если есть место"""
    if db.count_active_downloads() >= 3:
        return
    
    pending = db.get_pending_queue()
    if pending:
        item = pending[0]
        start_queue_download(item['id'], item)

@app.route('/api/config', methods=['GET'])
def get_config():
    """Получение конфигурации"""
    return jsonify({
        'download_folder': DOWNLOAD_FOLDER,
        'ffmpeg_available': check_ffmpeg()
    })


@app.route('/api/log-error', methods=['POST'])
def log_frontend_error_endpoint():
    """Логирование ошибок с фронтенда"""
    data = request.json
    log_frontend_error(data.get('type', 'error'), data.get('message', ''), 
                      data.get('stack', ''), data.get('timestamp', ''))
    return jsonify({'status': 'logged'})

@app.route('/api/queue/add', methods=['POST'])
def queue_add():
    """Добавление в очередь"""
    data = request.json
    url = data.get('url', '').strip()
    title = data.get('title', '')
    format_id = data.get('format_id')
    audio_only = data.get('audio_only', False)
    download_folder = data.get('download_folder', DOWNLOAD_FOLDER)
    
    if not url:
        return jsonify({'error': 'URL не указан'}), 400
    
    queue_id = db.add_to_queue(url, title, format_id, audio_only, download_folder)
    return jsonify({'queue_id': queue_id})

@app.route('/api/queue/list', methods=['GET'])
def queue_list():
    """Список очереди"""
    queue = db.get_queue()
    with active_tasks_lock:
        for item in queue:
            if item['task_id'] and item['task_id'] in active_tasks:
                task = active_tasks[item['task_id']]
                item['progress'] = task['progress']
                item['paused'] = task['paused']
    return jsonify({'queue': queue})

@app.route('/api/queue/start', methods=['POST'])
def queue_start():
    """Запуск загрузки очереди"""
    while db.count_active_downloads() < 3:
        pending = db.get_pending_queue()
        if not pending:
            break
        item = pending[0]
        start_queue_download(item['id'], item)
    return jsonify({'status': 'started'})

@app.route('/api/queue/pause', methods=['POST'])
def queue_pause():
    """Пауза всех загрузок"""
    with active_tasks_lock:
        for task_id, task in active_tasks.items():
            task['paused_flag']['value'] = True
            task['paused'] = True
            queue_id = task['queue_id']
            db.update_queue_item(queue_id, status='paused')
    return jsonify({'status': 'paused'})

@app.route('/api/queue/resume', methods=['POST'])
def queue_resume():
    """Возобновление всех загрузок"""
    with active_tasks_lock:
        for task_id, task in active_tasks.items():
            if task['paused']:
                task['paused_flag']['value'] = False
                task['paused'] = False
                queue_id = task['queue_id']
                db.update_queue_item(queue_id, status='downloading')
    return jsonify({'status': 'resumed'})

@app.route('/api/queue/stop', methods=['POST'])
def queue_stop():
    """Остановка всех загрузок"""
    with active_tasks_lock:
        for task_id, task in list(active_tasks.items()):
            task['cancelled_flag']['value'] = True
            queue_id = task['queue_id']
            db.update_queue_item(queue_id, status='cancelled')
            del active_tasks[task_id]
    db.clear_queue()
    return jsonify({'status': 'stopped'})

@app.route('/api/history', methods=['GET'])
def get_history():
    """Получение истории скачиваний"""
    history = db.get_history()
    return jsonify({'history': history})

@app.route('/api/ui-state', methods=['GET', 'POST'])
def ui_state():
    """Сохранение и загрузка UI состояния"""
    if request.method == 'POST':
        data = request.json
        for key, value in data.items():
            db.save_ui_state(key, value)
        return jsonify({'status': 'saved'})
    else:
        state = db.get_all_ui_state()
        return jsonify(state)

def start_flask():
    """Запуск Flask в отдельном потоке"""
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)


if __name__ == '__main__':
    log_info("=" * 80)
    log_info("Video Downloader - Starting application")
    log_info("=" * 80)
    
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=start_flask, daemon=True).start()
    
    # Ждем немного, чтобы Flask успел запуститься
    time.sleep(1)
    
    log_info("Creating webview window")
    # Подавляем ошибку GTK (webview все равно попытается проверить все бэкенды)
    old_stderr = sys.stderr
    sys.stderr = StringIO()
    try:
        webview.create_window(
            'Video Downloader',
            'http://127.0.0.1:5000',
            width=800,
            height=700,
            resizable=True
        )
    finally:
        sys.stderr = old_stderr
    
    try:
        webview.start(debug=False)
    except Exception as e:
        log_error(f"Failed to start webview: {e}")
        raise

