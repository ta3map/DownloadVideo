#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify, Response, send_file
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
        try:
            result = get_formats(url)
            title = result.get('title', '')
        except:
            pass
    
    task_id = str(uuid.uuid4())
    db.update_queue_item(queue_id, status='downloading', task_id=task_id)
    
    with active_tasks_lock:
        active_tasks[task_id] = {
            'queue_id': queue_id,
            'url': url,
            'title': title,
            'format_id': format_id,
            'audio_only': audio_only,
            'progress': 0,
            'paused': False,
            'cancelled': False,
            'final_file': None,
            'error': None,
            'paused_flag': {'value': False},
            'cancelled_flag': {'value': False}
        }
    
    def progress_callback(percent):
        with active_tasks_lock:
            if task_id in active_tasks:
                active_tasks[task_id]['progress'] = percent
    
    def final_file_callback(filename):
        with active_tasks_lock:
            if task_id in active_tasks:
                active_tasks[task_id]['final_file'] = filename
    
    paused_flag = active_tasks[task_id]['paused_flag']
    cancelled_flag = active_tasks[task_id]['cancelled_flag']
    logger = CustomLogger(final_file_callback=final_file_callback)
    
    def worker():
        final_file = ''
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
                if task_id in active_tasks:
                    final_file = active_tasks[task_id].get('final_file', '')
                    if not title:
                        title = active_tasks[task_id].get('title', '')
                    del active_tasks[task_id]
            db.add_to_history(url, title, format_id, audio_only, 'finished', final_file)
            db.update_queue_item(queue_id, status='finished')
            start_next_queue_item()
        except Exception as e:
            error_msg = str(e)
            with active_tasks_lock:
                if task_id in active_tasks:
                    if not title:
                        title = active_tasks[task_id].get('title', '')
                    del active_tasks[task_id]
            if 'cancelled' in error_msg.lower():
                db.add_to_history(url, title, format_id, audio_only, 'cancelled', '')
                db.update_queue_item(queue_id, status='cancelled')
            else:
                db.add_to_history(url, title, format_id, audio_only, 'error', '')
                db.update_queue_item(queue_id, status='error')
            start_next_queue_item()
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    with active_tasks_lock:
        active_tasks[task_id]['thread'] = thread

def start_next_queue_item():
    """Запуск следующего элемента из очереди если есть место"""
    if db.count_active_downloads() >= 3:
        return
    
    pending = db.get_pending_queue()
    if pending:
        item = pending[0]
        start_queue_download(item['id'], item)

@app.route('/api/download', methods=['POST'])
def start_download():
    """Запуск скачивания (старый способ, для совместимости)"""
    data = request.json
    url = data.get('url', '').strip()
    format_id = data.get('format_id')
    audio_only = data.get('audio_only', False)
    download_folder = data.get('download_folder', DOWNLOAD_FOLDER)
    
    if not url:
        return jsonify({'error': 'URL не указан'}), 400
    
    if not audio_only and not format_id:
        return jsonify({'error': 'Формат не выбран'}), 400
    
    os.makedirs(download_folder, exist_ok=True)
    
    task_id = create_task()
    update_task(task_id, status='downloading', url=url, format_id=format_id,
                audio_only=audio_only, progress=0, paused=False, cancelled=False)
    
    paused_flag = {'value': False}
    cancelled_flag = {'value': False}
    
    def progress_callback(percent):
        update_task(task_id, progress=percent)
    
    def final_file_callback(filename):
        update_task(task_id, final_file=filename)
        if filename:
            try:
                info = get_formats(url)
                title = info.get('title', '')
            except:
                title = ''
            db.add_to_history(url, title, format_id, audio_only, 'finished', filename)
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
            update_task(task_id, status='finished', progress=100)
        except Exception as e:
            if 'cancelled' in str(e).lower():
                log_info(f"Download cancelled for task {task_id}")
                update_task(task_id, status='cancelled')
                try:
                    info = get_formats(url)
                    title = info.get('title', '')
                except:
                    title = ''
                db.add_to_history(url, title, format_id, audio_only, 'cancelled', '')
            else:
                log_error(f"Error downloading for task {task_id}: {e}")
                update_task(task_id, status='error', error=str(e))
                try:
                    info = get_formats(url)
                    title = info.get('title', '')
                except:
                    title = ''
                db.add_to_history(url, title, format_id, audio_only, 'error', '')
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    update_task(task_id, thread=thread, paused_flag=paused_flag, cancelled_flag=cancelled_flag)
    
    return jsonify({'task_id': task_id})


@app.route('/api/pause/<task_id>', methods=['POST'])
def pause_download(task_id):
    """Пауза скачивания"""
    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    paused_flag = task.get('paused_flag')
    if paused_flag:
        paused_flag['value'] = True
        update_task(task_id, paused=True, status='paused')
        return jsonify({'status': 'paused'})
    
    return jsonify({'error': 'Не удалось поставить на паузу'}), 400


@app.route('/api/resume/<task_id>', methods=['POST'])
def resume_download(task_id):
    """Возобновление скачивания"""
    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    paused_flag = task.get('paused_flag')
    if paused_flag:
        paused_flag['value'] = False
        update_task(task_id, paused=False, status='downloading')
        return jsonify({'status': 'downloading'})
    
    return jsonify({'error': 'Не удалось возобновить'}), 400


@app.route('/api/stop/<task_id>', methods=['POST'])
def stop_download(task_id):
    """Остановка скачивания"""
    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    cancelled_flag = task.get('cancelled_flag')
    if cancelled_flag:
        cancelled_flag['value'] = True
        update_task(task_id, cancelled=True, status='cancelled')
        return jsonify({'status': 'cancelled'})
    
    return jsonify({'error': 'Не удалось остановить'}), 400


@app.route('/api/progress/<task_id>')
def progress_stream(task_id):
    """SSE поток для обновления прогресса"""
    def generate():
        while True:
            task = get_task(task_id)
            if not task:
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                break
            
            data = {
                'progress': task.get('progress', 0),
                'status': task.get('status', 'idle'),
                'final_file': task.get('final_file'),
                'error': task.get('error')
            }
            
            yield f"data: {json.dumps(data)}\n\n"
            
            # Если задача завершена, прекращаем поток
            if task['status'] in ['finished', 'error', 'cancelled']:
                break
            
            time.sleep(0.5)
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/downloads', methods=['GET'])
def list_downloads():
    """Список скачанных файлов"""
    try:
        files = []
        if os.path.exists(DOWNLOAD_FOLDER):
            for filename in os.listdir(DOWNLOAD_FOLDER):
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                if os.path.isfile(filepath):
                    files.append({
                        'name': filename,
                        'size': os.path.getsize(filepath),
                        'path': filepath
                    })
        return jsonify({'files': files})
    except Exception as e:
        log_error(f"Error listing downloads: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/download-file/<path:filename>', methods=['GET'])
def download_file(filename):
    """Скачивание файла через браузер"""
    try:
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.exists(filepath) and os.path.isfile(filepath):
            return send_file(filepath, as_attachment=True)
        return jsonify({'error': 'Файл не найден'}), 404
    except Exception as e:
        log_error(f"Error listing downloads: {e}")
        return jsonify({'error': str(e)}), 500


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
    try:
        data = request.json
        error_type = data.get('type', 'error')
        message = data.get('message', '')
        stack = data.get('stack', '')
        timestamp = data.get('timestamp', '')
        
        log_frontend_error(error_type, message, stack, timestamp)
        
        return jsonify({'status': 'logged'})
    except Exception as e:
        log_error(f"Error logging frontend error: {e}")
        return jsonify({'error': str(e)}), 500

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
    for item in queue:
        if item['task_id']:
            with active_tasks_lock:
                task = active_tasks.get(item['task_id'])
                if task:
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

@app.route('/api/queue/progress')
def queue_progress_stream():
    """SSE поток для обновления прогресса очереди"""
    def generate():
        while True:
            with active_tasks_lock:
                tasks_data = {}
                for task_id, task in active_tasks.items():
                    tasks_data[task_id] = {
                        'queue_id': task['queue_id'],
                        'progress': task['progress'],
                        'paused': task['paused']
                    }
            yield f"data: {json.dumps(tasks_data)}\n\n"
            time.sleep(0.5)
    
    return Response(generate(), mimetype='text/event-stream')


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

