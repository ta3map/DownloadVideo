#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yt_dlp
import os
import platform
import subprocess
import re
import time

# Импортируем logger только если он доступен (для совместимости с tkinter версией)
try:
    from logger import log_info, log_error, log_warning, log_debug
except ImportError:
    # Fallback если logger не доступен
    def log_info(msg): print(f"[INFO] {msg}")
    def log_error(msg): print(f"[ERROR] {msg}")
    def log_warning(msg): print(f"[WARNING] {msg}")
    def log_debug(msg): print(f"[DEBUG] {msg}")


def get_default_download_dir():
    """Определяет папку загрузки по умолчанию в зависимости от ОС"""
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ["USERPROFILE"], "Downloads")
    elif system == "Linux":
        # Проверяем, не Android ли это
        if "Android" in platform.platform():
            return "/storage/emulated/0/Download"
        # Для обычного Linux используем стандартную папку Downloads
        home = os.environ.get("HOME", os.path.expanduser("~"))
        downloads = os.path.join(home, "Downloads")
        # Создаем папку, если её нет
        os.makedirs(downloads, exist_ok=True)
        return downloads
    else:
        return os.getcwd()


def check_ffmpeg():
    """Проверяет наличие ffmpeg в системе"""
    try:
        subprocess.run(["ffmpeg", "-version"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True)
        return True
    except Exception:
        return False


class CustomLogger:
    """Кастомный логгер для yt-dlp с перехватом финального файла"""
    def __init__(self, final_file_callback=None):
        self.final_file = None
        self.final_file_callback = final_file_callback
        self.messages = []

    def debug(self, msg):
        """Обрабатывает debug сообщения и извлекает путь к финальному файлу"""
        self.messages.append(("DEBUG", msg))
        
        # 1) Случай мерджа (слияния) с финальным именем в кавычках
        merge_match = re.search(r'\[Merger\]\sMerging formats into\s"([^"]+)"', msg)
        if merge_match:
            self.final_file = merge_match.group(1)
            if self.final_file_callback:
                self.final_file_callback(self.final_file)

        # 2) Случай уже скачанного файла (без кавычек)
        already_match = re.search(r'\[download\]\s+(.*?)\s+has already been downloaded', msg)
        if already_match:
            self.final_file = already_match.group(1)
            if self.final_file_callback:
                self.final_file_callback(self.final_file)

    def warning(self, msg):
        self.messages.append(("WARNING", msg))

    def error(self, msg):
        self.messages.append(("ERROR", msg))


def get_video_info(url):
    """Получает информацию о видео без скачивания"""
    try:
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        return info
    except Exception as e:
        raise Exception(f"Ошибка получения информации о видео: {e}")


def download_thumbnail(url, thumbnail_folder, video_id=None, info=None):
    """
    Скачивает thumbnail для видео
    
    Args:
        url: URL видео
        thumbnail_folder: Папка для сохранения thumbnails
        video_id: ID видео для имени файла (опционально)
        info: Уже полученная информация о видео (опционально, для избежания повторного вызова)
    
    Returns:
        Путь к скачанному thumbnail или None
    """
    try:
        os.makedirs(thumbnail_folder, exist_ok=True)
        
        # Используем переданную информацию или получаем заново
        if info is None:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
        
        thumbnail_url = info.get('thumbnail')
        
        if not thumbnail_url:
            return None
        
        # Используем video_id или генерируем из URL
        if not video_id:
            video_id = info.get('id') or info.get('display_id') or str(hash(url))
        
        # Определяем расширение из URL или используем jpg по умолчанию
        ext = 'jpg'
        if '.' in thumbnail_url:
            ext = thumbnail_url.split('.')[-1].split('?')[0]
            if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                ext = 'jpg'
        
        thumbnail_filename = f"{video_id}.{ext}"
        thumbnail_path = os.path.join(thumbnail_folder, thumbnail_filename)
        
        # Скачиваем thumbnail
        import urllib.request
        urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
        
        log_info(f"Thumbnail downloaded: {thumbnail_path}")
        return thumbnail_path
    except Exception as e:
        log_error(f"Error downloading thumbnail for {url}: {e}")
        return None


def get_formats(url, thumbnail_folder=None):
    """
    Получает список доступных форматов для видео
    
    Args:
        url: URL видео
        thumbnail_folder: Папка для сохранения thumbnails (опционально)
    
    Returns:
        Словарь с title, formats и thumbnail_path (если thumbnail_folder указан)
    """
    try:
        info = get_video_info(url)
        video_title = info.get("title", "video")
        fetched_formats = info.get("formats", [])
        
        full_formats = []
        for fmt in fetched_formats:
            full_fmt = {
                "format_id": fmt.get("format_id"),
                "vcodec": fmt.get("vcodec", "none"),
                "acodec": fmt.get("acodec", "none"),
                "resolution": fmt.get("resolution", "audio"),
                "ext": fmt.get("ext", "unknown"),
                "format_note": fmt.get("format_note", ""),
                "format": fmt.get("format", "")
            }
            full_formats.append(full_fmt)
        
        result = {
            "title": video_title,
            "formats": full_formats
        }
        
        # Скачиваем thumbnail если указана папка
        if thumbnail_folder:
            try:
                video_id = info.get('id') or info.get('display_id') or str(hash(url))
                thumbnail_path = download_thumbnail(url, thumbnail_folder, video_id, info=info)
                result["thumbnail_path"] = thumbnail_path
            except Exception as e:
                log_error(f"Error downloading thumbnail in get_formats: {e}")
                result["thumbnail_path"] = None
        
        return result
    except Exception as e:
        log_error(f"Error getting formats for {url}: {e}")
        raise Exception(f"Ошибка получения форматов: {e}")


def create_progress_hook(progress_callback, paused_flag, cancelled_flag, final_file_callback):
    """Создает функцию progress_hook для yt-dlp"""
    def progress_hook(d):
        if isinstance(cancelled_flag, dict):
            if cancelled_flag.get("value", False):
                raise Exception("Download cancelled by user.")
        elif cancelled_flag.get():
            raise Exception("Download cancelled by user.")
        
        while True:
            if isinstance(paused_flag, dict):
                if not paused_flag.get("value", False):
                    break
            elif not paused_flag.get():
                break
            time.sleep(0.1)

        status = d.get('status', '').lower()
        if status == 'downloading':
            percent = d.get('_percent_str', '').strip()
            if progress_callback:
                # Извлекаем процент из строки
                m = re.search(r"([\d.]+)%", percent)
                if m:
                    progress_callback(float(m.group(1)))
        elif status == 'finished':
            filename = d.get('filename')
            if filename and final_file_callback:
                final_file_callback(filename)
            if progress_callback:
                progress_callback(100.0)
    
    return progress_hook


def download_video(url, format_id, download_folder, audio_only=False, 
                   progress_callback=None, logger=None, paused_flag=None, 
                   cancelled_flag=None, final_file_callback=None):
    """
    Скачивает видео с указанными параметрами
    
    Args:
        url: URL видео
        format_id: ID формата (None если audio_only)
        download_folder: Папка для сохранения
        audio_only: Только аудио (mp3)
        progress_callback: Функция для обновления прогресса (принимает процент)
        logger: CustomLogger для логирования
        paused_flag: dict с флагом паузы {'value': bool}
        cancelled_flag: dict с флагом отмены {'value': bool}
        final_file_callback: Функция для сохранения пути к финальному файлу
    """
    if paused_flag is None:
        paused_flag = {"value": False}
    if cancelled_flag is None:
        cancelled_flag = {"value": False}
    
    # Создаем progress hook
    progress_hook_func = create_progress_hook(
        progress_callback,
        paused_flag,
        cancelled_flag,
        final_file_callback
    )
    
    ffmpeg_available = check_ffmpeg()
    
    if audio_only:
        ydl_opts = {
            'outtmpl': os.path.join(download_folder, "%(title)s.%(ext)s"),
            'format': 'bestaudio',
            'logger': logger,
            'progress_hooks': [progress_hook_func],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'
            }]
        }
    else:
        ydl_opts = {
            'outtmpl': os.path.join(download_folder, "%(title)s.%(ext)s"),
            'format': format_id,
            'logger': logger,
            'progress_hooks': [progress_hook_func]
        }
        # Проверяем, нужна ли конвертация (видео без аудио)
        # Для этого нужно получить информацию о формате
        try:
            info = get_video_info(url)
            formats = info.get("formats", [])
            selected_format = next((f for f in formats if f.get("format_id") == format_id), None)
            if selected_format:
                needs_conversion = (
                    selected_format.get("vcodec", "none") != "none"
                    and selected_format.get("acodec", "none") == "none"
                )
                if ffmpeg_available and needs_conversion:
                    ydl_opts['format'] = f"{format_id}+bestaudio"
                    ydl_opts['merge_output_format'] = 'mp4'
        except Exception:
            pass
    
    try:
        log_info(f"Starting download: url={url}, format_id={format_id}, audio_only={audio_only}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        log_info(f"Download completed successfully: {url}")
        return True
    except Exception as e:
        if "cancelled" in str(e).lower():
            log_info(f"Download cancelled by user: {url}")
            raise Exception("Download cancelled by user.")
        log_error(f"Download error for {url}: {e}")
        raise e

