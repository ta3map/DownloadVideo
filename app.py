#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify, Response, send_file
import threading
import time
import json
import uuid
import os
import webview
from video_downloader import (
    get_formats, download_video, get_default_download_dir,
    CustomLogger, check_ffmpeg
)
from logger import log_frontend_error, log_info, log_error, log_warning, log_debug

app = Flask(__name__)

# Хранилище активных задач
tasks = {}
tasks_lock = threading.Lock()

# Папка загрузки по умолчанию
DOWNLOAD_FOLDER = get_default_download_dir()


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


@app.route('/api/download', methods=['POST'])
def start_download():
    """Запуск скачивания"""
    data = request.json
    url = data.get('url', '').strip()
    format_id = data.get('format_id')
    audio_only = data.get('audio_only', False)
    download_folder = data.get('download_folder', DOWNLOAD_FOLDER)
    
    if not url:
        return jsonify({'error': 'URL не указан'}), 400
    
    if not audio_only and not format_id:
        return jsonify({'error': 'Формат не выбран'}), 400
    
    # Создаем папку если её нет
    os.makedirs(download_folder, exist_ok=True)
    
    task_id = create_task()
    update_task(task_id, status='downloading', url=url, format_id=format_id,
                audio_only=audio_only, progress=0, paused=False, cancelled=False)
    
    # Флаги для управления скачиванием
    paused_flag = {'value': False}
    cancelled_flag = {'value': False}
    
    def set_paused(value):
        paused_flag['value'] = value
        update_task(task_id, paused=value, status='paused' if value else 'downloading')
    
    def set_cancelled(value):
        cancelled_flag['value'] = value
        update_task(task_id, cancelled=value, status='cancelled')
    
    # Колбэки
    def progress_callback(percent):
        update_task(task_id, progress=percent)
    
    def final_file_callback(filename):
        update_task(task_id, final_file=filename)
    
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
            else:
                log_error(f"Error downloading for task {task_id}: {e}")
                update_task(task_id, status='error', error=str(e))
    
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
    # Создаем webview окно
    try:
        webview.create_window(
            'Video Downloader',
            'http://127.0.0.1:5000',
            width=800,
            height=700,
            resizable=True
        )
        webview.start(debug=False)
    except Exception as e:
        log_error(f"Failed to start webview: {e}")
        raise

