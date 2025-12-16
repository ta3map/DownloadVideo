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


def get_video_id(info=None, url=None):
    """Извлекает video_id из info или генерирует из URL"""
    if info:
        return info.get('id') or info.get('display_id') or (str(hash(url)) if url else None)
    if url:
        return str(hash(url))
    return None


def open_file_path(file_path):
    """Открывает файл в системном приложении"""
    system = platform.system()
    if system == 'Windows':
        os.startfile(file_path)
    elif system == 'Darwin':
        subprocess.Popen(['open', file_path])
    else:
        subprocess.Popen(['xdg-open', file_path])


def open_folder_path(folder_path):
    """Открывает папку в системном файловом менеджере"""
    system = platform.system()
    if system == 'Windows':
        os.startfile(folder_path)
    elif system == 'Darwin':
        subprocess.Popen(['open', folder_path])
    else:
        subprocess.Popen(['xdg-open', folder_path])


def safe_delete_thumbnail(thumbnail_path):
    """Безопасно удаляет thumbnail файл если он существует"""
    if thumbnail_path and os.path.exists(thumbnail_path) and os.path.isfile(thumbnail_path):
        try:
            os.remove(thumbnail_path)
        except Exception as e:
            log_error(f"Error deleting thumbnail {thumbnail_path}: {e}")


def get_flag_value(flag):
    """Получает значение флага (поддерживает dict и callable)"""
    if isinstance(flag, dict):
        return flag.get("value", False)
    elif callable(flag):
        return flag.get()
    return False


def set_flag_value(flag, value):
    """Устанавливает значение флага"""
    if isinstance(flag, dict):
        flag["value"] = value
    elif callable(flag):
        flag.set(value)


def format_format_label(fmt):
    """
    Форматирует строку формата для отображения (как в списке форматов)
    
    Args:
        fmt: Словарь с информацией о формате (height, ext, format_note, format)
    
    Returns:
        Отформатированная строка формата
    """
    # Формируем понятную метку разрешения
    resolution_label = ''
    height = fmt.get('height')
    if height and height > 0:
        if height >= 2160:
            resolution_label = '4K (2160p)'
        elif height >= 1440:
            resolution_label = '1440p'
        elif height >= 1080:
            resolution_label = '1080p'
        elif height >= 720:
            resolution_label = '720p'
        elif height >= 480:
            resolution_label = '480p'
        elif height >= 360:
            resolution_label = '360p'
        elif height >= 240:
            resolution_label = '240p'
        elif height >= 144:
            resolution_label = '144p'
        else:
            resolution_label = f'{height}p'
    else:
        resolution_label = fmt.get('resolution', 'unknown')
    
    # Формируем полную метку
    parts = [resolution_label]
    if fmt.get('ext') and fmt['ext'] != 'unknown':
        parts.append(fmt['ext'].upper())
    if fmt.get('format_note'):
        parts.append(fmt['format_note'])
    
    # Проверяем наличие ffmpeg (формат может быть строкой вида "123+456" или числом)
    format_str = fmt.get('format')
    if format_str:
        # Преобразуем в строку если нужно
        if not isinstance(format_str, str):
            format_str = str(format_str)
        if '+' in format_str:
            parts.append('+ffmpeg')
    
    return ' | '.join(parts)


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
            video_id = get_video_id(info, url)
        
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
    Получает список доступных форматов для видео с фильтрацией
    
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
        
        # Стандартные разрешения (в пикселях по высоте)
        # Включаем стандартные и некоторые распространенные промежуточные
        STANDARD_HEIGHTS = [144, 240, 270, 360, 480, 720, 1080, 1440, 2160]
        
        # Фильтруем и обрабатываем форматы
        video_formats = []
        for fmt in fetched_formats:
            vcodec = fmt.get("vcodec", "none")
            acodec = fmt.get("acodec", "none")
            
            # Пропускаем аудио-только форматы
            if vcodec == "none" or vcodec is None:
                continue
            
            # Получаем высоту видео
            height = fmt.get("height")
            if not height:
                # Пытаемся извлечь из resolution
                resolution = fmt.get("resolution", "")
                if resolution and "x" in resolution:
                    try:
                        height = int(resolution.split("x")[1])
                    except:
                        continue
                else:
                    continue
            
            # Пропускаем нестандартные разрешения (или добавляем их в конец)
            # Но сначала собираем все форматы, потом отфильтруем
            
            format_info = {
                "format_id": fmt.get("format_id"),
                "vcodec": vcodec,
                "acodec": acodec,
                "height": height,
                "width": fmt.get("width"),
                "fps": fmt.get("fps"),
                "ext": fmt.get("ext", "unknown"),
                "format_note": fmt.get("format_note", ""),
                "format": fmt.get("format", ""),
                "filesize": fmt.get("filesize"),
                "tbr": fmt.get("tbr"),  # Total bitrate
                "vbr": fmt.get("vbr"),  # Video bitrate
                "abr": fmt.get("abr"),  # Audio bitrate
            }
            
            # Формируем resolution строку
            if format_info["width"] and format_info["height"]:
                format_info["resolution"] = f"{format_info['width']}x{format_info['height']}"
            else:
                format_info["resolution"] = f"{height}p"
            
            # Добавляем отформатированную метку используя функцию format_format_label
            format_info["label"] = format_format_label(format_info)
            
            video_formats.append(format_info)
        
        # Группируем по разрешению и выбираем лучший формат для каждого
        formats_by_height = {}
        for fmt in video_formats:
            height = fmt["height"]
            
            # Если это стандартное разрешение или близкое к стандартному
            # Находим ближайшее стандартное разрешение
            if STANDARD_HEIGHTS:
                closest_standard = min(STANDARD_HEIGHTS, key=lambda x: abs(x - height))
                # Допуск 15 пикселей для группировки близких разрешений
                # Это позволяет группировать похожие разрешения (например, 1080 и 1088)
                if abs(closest_standard - height) <= 15:
                    height_key = closest_standard
                else:
                    # Для нестандартных разрешений используем оригинальную высоту
                    # но только если они не слишком далеки от стандартных
                    if height < 50 or height > 4320:  # Слишком маленькие или большие пропускаем
                        continue
                    height_key = height
            else:
                height_key = height
            
            if height_key not in formats_by_height:
                formats_by_height[height_key] = []
            formats_by_height[height_key].append(fmt)
        
        # Выбираем лучший формат для каждого разрешения
        filtered_formats = []
        for height_key in sorted(formats_by_height.keys()):
            candidates = formats_by_height[height_key]
            
            # Сортируем кандидатов по приоритету:
            # 1. Форматы с аудио (если есть)
            # 2. Лучший битрейт
            # 3. Предпочтительные кодеки (H.264 > VP9 > AV1)
            # 4. Предпочтительные контейнеры (mp4 > webm)
            
            def format_score(fmt):
                score = 0
                
                # Бонус за наличие аудио
                if fmt.get("acodec") and fmt.get("acodec") != "none":
                    score += 1000
                
                # Бонус за битрейт
                tbr = fmt.get("tbr") or fmt.get("vbr") or 0
                score += tbr
                
                # Бонус за предпочтительные кодеки
                vcodec = fmt.get("vcodec", "").lower()
                if "h264" in vcodec or "avc" in vcodec:
                    score += 100
                elif "vp9" in vcodec:
                    score += 50
                elif "av1" in vcodec:
                    score += 25
                
                # Бонус за предпочтительные контейнеры
                ext = fmt.get("ext", "").lower()
                if ext == "mp4":
                    score += 10
                elif ext == "webm":
                    score += 5
                
                return score
            
            # Выбираем лучший формат
            best_format = max(candidates, key=format_score)
            
            # Формируем финальный формат для отображения
            final_fmt = {
                "format_id": best_format["format_id"],
                "vcodec": best_format["vcodec"],
                "acodec": best_format["acodec"],
                "resolution": best_format["resolution"],
                "height": best_format["height"],
                "ext": best_format["ext"],
                "format_note": best_format.get("format_note", ""),
                "format": best_format.get("format", ""),
                "label": best_format.get("label", "")  # Копируем уже созданный label
            }
            
            # Добавляем информацию о необходимости мерджа
            needs_merge = (best_format.get("acodec") == "none" or 
                          best_format.get("acodec") is None)
            if needs_merge:
                final_fmt["format_note"] = (final_fmt.get("format_note", "") + 
                                           (" +audio" if final_fmt.get("format_note") else "+audio"))
            
            filtered_formats.append(final_fmt)
        
        # Сортируем по высоте (от меньшего к большему)
        filtered_formats.sort(key=lambda x: x.get("height", 0))
        
        result = {
            "title": video_title,
            "formats": filtered_formats
        }
        
        # Скачиваем thumbnail если указана папка
        if thumbnail_folder:
            try:
                video_id = get_video_id(info, url)
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
        if get_flag_value(cancelled_flag):
            raise Exception("Download cancelled by user.")
        
        while get_flag_value(paused_flag):
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

