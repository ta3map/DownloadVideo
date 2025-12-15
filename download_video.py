#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk
import threading
import yt_dlp
import os
import platform
import subprocess
import time
import re
import json
import tempfile
import tkinter as tk

def get_config_path():
    return os.path.join(tempfile.gettempdir(), "video_downloader_config.json")

def load_config():
    try:
        config_path = get_config_path()
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        expected_keys = (
            "video_url", "download_folder", "formats",
            "last_selected_format_index", "last_progress", "audio_only"
        )
        if not all(key in config for key in expected_keys):
            raise Exception("Некорректная структура файла конфигурации")
        if not isinstance(config["formats"], list):
            raise Exception("Поле 'formats' должно быть списком")
        if config["formats"]:
            if not all(isinstance(item, dict) for item in config["formats"]):
                config["formats"] = []
        return config
    except Exception:
        default_config = {
            "video_url": "",
            "download_folder": get_default_download_dir(),
            "formats": [],
            "last_selected_format_index": -1,
            "last_progress": 0,
            "audio_only": False
        }
        save_config(default_config)
        return default_config

def save_config(config_override=None):
    config_path = get_config_path()
    try:
        if config_override is None:
            if format_options:
                formats_to_save = format_options  # список словарей
            else:
                formats_to_save = list(format_list.get(0, tk.END))
            config = {
                "video_url": url_var.get() if 'url_var' in globals() else "",
                "download_folder": folder_path.get() if 'folder_path' in globals() else get_default_download_dir(),
                "formats": formats_to_save,
                "last_selected_format_index": format_list.curselection()[0] if format_list.curselection() else -1,
                "last_progress": float(progress_bar['value']) if progress_bar is not None else 0,
                "audio_only": audio_only_var.get() if 'audio_only_var' in globals() else False
            }
        else:
            config = config_override
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    except Exception as e:
        write_log(f"Ошибка сохранения конфигурации: {e}")

def get_default_download_dir():
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

# --- Глобальные переменные ---
video_title = None
final_file = None
paused = False
cancelled = False
progress_bar = None
disabled_controls = []
format_options = []

def write_log(message):
    log_text.after(0, lambda: (
        log_text.insert(tk.END, message + "\n"),
        log_text.see(tk.END)
    ))

def update_progress(percent_str):
    try:
        m = re.search(r"([\d.]+)%", percent_str)
        if m and progress_bar:
            value = float(m.group(1))
            progress_bar['value'] = value
    except Exception as e:
        write_log(f"Ошибка обновления прогресса: {e}")

class CustomLogger:
    def debug(self, msg):
        """
        Ловим все debug-сообщения yt-dlp.
        1) Если видим строку вида [Merger] Merging formats into "...",
           значит идёт «склейка» (merging) в финальный файл — сохраняем его.
        2) Если видим строку вида [download] /.../filename.ext has already been downloaded,
           перехватываем путь к уже скачанному файлу.
        """
        global final_file
        write_log("DEBUG: " + msg)

        # 1) Случай мерджа (слияния) с финальным именем в кавычках
        merge_match = re.search(r'\[Merger\]\sMerging formats into\s"([^"]+)"', msg)
        if merge_match:
            final_file = merge_match.group(1)
            write_log(f"DEBUG: final_file (from Merger) = {final_file}")

        # 2) Случай уже скачанного файла (без кавычек)
        #    Пример строки: [download] /home/user/Some File.mp4 has already been downloaded
        already_match = re.search(r'\[download\]\s+(.*?)\s+has already been downloaded', msg)
        if already_match:
            final_file = already_match.group(1)
            write_log(f"DEBUG: final_file (already downloaded) = {final_file}")

    def warning(self, msg):
        write_log("WARNING: " + msg)

    def error(self, msg):
        write_log("ERROR: " + msg)


def progress_hook(d):
    global paused, cancelled, final_file
    if cancelled:
        raise Exception("Download cancelled by user.")
    while paused:
        time.sleep(0.1)

    status = d.get('status', '').lower()
    if status == 'downloading':
        percent = d.get('_percent_str', '').strip()
        update_progress(percent)
    elif status == 'finished':
        # Если не было слияния, то этот файл уже считается финальным
        # (например, в режиме audio_only или формат с видео+аудио в одном потоке).
        if not final_file:
            final_file = d.get('filename')
        write_log(f"Download finished: {final_file or 'Unknown file'}")
        update_progress("100%")

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True)
        return True
    except Exception:
        return False

def select_folder():
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        folder_path.set(folder_selected)
        save_config()

def toggle_pause():
    global paused
    paused = not paused
    if paused:
        pause_button.config(text="Продолжить")
        write_log("Download paused.")
    else:
        pause_button.config(text="Пауза")
        write_log("Download resumed.")

def stop_download():
    global cancelled
    cancelled = True
    write_log("Stopping download...")

def disable_controls():
    for widget in disabled_controls:
        widget.config(state=tk.DISABLED)

def enable_controls():
    for widget in disabled_controls:
        widget.config(state=tk.NORMAL)

def fetch_formats():
    global video_title, format_options
    if audio_only_var.get():
        write_log("Audio only selected. Skipping format fetch.")
        return
    url = url_var.get()
    if not url:
        messagebox.showerror("Ошибка", "Введите URL видео!")
        return
    write_log(f"Fetching formats for: {url}")
    save_config()

    def worker():
        global video_title, format_options
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "logger": CustomLogger()}) as ydl:
                info = ydl.extract_info(url, download=False)
            video_title = info.get("title", "video")
            fetched_formats = info.get("formats", [])
            full_formats = []
            stored_formats = []
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
                label = (f"{full_fmt['resolution']} | {full_fmt['ext']} "
                         f"| {full_fmt['format_note']} "
                         + ("+ffmpeg" if "+" in full_fmt["format"] else ""))
                stored_formats.append(label)
                full_formats.append(full_fmt)

            format_list.delete(0, tk.END)
            for label in stored_formats:
                format_list.insert(tk.END, label)
            format_options = full_formats

            write_log("Formats fetched successfully.")

            cur_conf = load_config()
            cur_conf["formats"] = full_formats
            save_config(cur_conf)

            try:
                conf = load_config()
                idx = conf.get("last_selected_format_index", -1)
                if 0 <= idx < len(stored_formats):
                    format_list.selection_set(idx)
            except Exception:
                pass

        except Exception as e:
            write_log(f"Error fetching formats: {e}")

    threading.Thread(target=worker, daemon=True).start()

def restore_formats_from_config():
    global format_options
    conf = load_config()
    stored = conf.get("formats", [])
    if stored:
        format_list.delete(0, tk.END)
        format_options = stored
        for fmt in stored:
            label = (f"{fmt.get('resolution', 'audio')} | {fmt.get('ext', 'unknown')} "
                     f"| {fmt.get('format_note', '')} "
                     + ("+ffmpeg" if "+" in fmt.get("format", "") else ""))
            format_list.insert(tk.END, label)
        idx = conf.get("last_selected_format_index", -1)
        if 0 <= idx < len(stored):
            format_list.selection_set(idx)

def open_result_folder(event=None):
    global final_file
    if not final_file:
        messagebox.showerror("Ошибка", "Файл ещё не скачан или путь не определён.")
        return
    folder_to_open = os.path.dirname(final_file)
    system = platform.system()
    if system == "Windows":
        subprocess.Popen(["explorer", folder_to_open])
    elif system == "Darwin":
        subprocess.Popen(["open", folder_to_open])
    else:
        subprocess.Popen(["xdg-open", folder_to_open])

def play_downloaded_file():
    global final_file
    if not final_file:
        messagebox.showerror("Ошибка", "Файл ещё не скачан или путь не определён.")
        return
    system = platform.system()
    if system == "Windows":
        os.startfile(final_file)
    elif system == "Darwin":
        subprocess.Popen(["open", final_file])
    else:
        subprocess.Popen(["xdg-open", final_file])

def download_selected_format():
    global final_file, paused, cancelled
    paused = False
    cancelled = False
    disable_controls()
    pause_button.config(state=tk.NORMAL, text="Пауза")
    stop_button.config(state=tk.NORMAL)
    open_folder_button.config(state=tk.DISABLED)
    play_button.config(state=tk.DISABLED)

    url = url_var.get()
    folder = folder_path.get()

    # Обнуляем final_file перед новой загрузкой
    final_file = None

    if audio_only_var.get():
        selected_format = None
    else:
        if format_list.size() == 0:
            restore_formats_from_config()
            if format_list.size() == 0:
                messagebox.showerror("Error", "Сначала получите форматы!")
                enable_controls()
                return
        selection = format_list.curselection()
        if not selection:
            conf = load_config()
            last_index = conf.get("last_selected_format_index", -1)
            if 0 <= last_index < format_list.size():
                selection = (last_index,)
                format_list.selection_set(last_index)
            else:
                messagebox.showerror("Error", "Выберите формат для загрузки!")
                enable_controls()
                return
        selected_format = format_options[selection[0]]

    write_log("Starting download...")
    save_config()

    ffmpeg_available = check_ffmpeg()

    if audio_only_var.get():
        ydl_opts = {
            'outtmpl': os.path.join(folder, "%(title)s.%(ext)s"),
            'format': 'bestaudio',
            'logger': CustomLogger(),
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'
            }]
        }
    else:
        ydl_opts = {
            'outtmpl': os.path.join(folder, "%(title)s.%(ext)s"),
            'format': selected_format["format_id"],
            'logger': CustomLogger(),
            'progress_hooks': [progress_hook]
        }
        needs_conversion = (
            selected_format.get("vcodec", "none") != "none"
            and selected_format.get("acodec", "none") == "none"
        )
        if ffmpeg_available and needs_conversion:
            ydl_opts['format'] = f"{selected_format['format_id']}+bestaudio"
            ydl_opts['merge_output_format'] = 'mp4'

    def worker():
        global final_file
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            write_log("Download completed successfully!")
            open_folder_button.config(state=tk.NORMAL)
            play_button.config(state=tk.NORMAL)

        except Exception as e:
            write_log(f"Error: {e}")
        enable_controls()
        pause_button.config(state=tk.DISABLED)
        stop_button.config(state=tk.DISABLED)
        progress_bar['value'] = 0
        cur_conf = load_config()
        if format_list.curselection():
            cur_conf["last_selected_format_index"] = format_list.curselection()[0]
        cur_conf["last_progress"] = float(progress_bar['value'])
        save_config(cur_conf)

    threading.Thread(target=worker, daemon=True).start()

def insert_link(path):
    link_text = f"Open folder containing file: {os.path.basename(path)}"
    start_index = log_text.index(tk.END)
    log_text.insert(tk.END, link_text + "\n")
    end_index = log_text.index(tk.END)
    log_text.tag_add("link", start_index, end_index)
    log_text.tag_config("link", foreground="blue", underline=True)
    log_text.tag_bind("link", "<Button-1>", lambda e: open_result_folder())

def attach_context_menu(widget):
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_command(label="Select All", command=lambda: (
        widget.select_range(0, tk.END) if isinstance(widget, tk.Entry)
        else widget.tag_add("sel", "1.0", "end")
    ))

    def show_menu(event):
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    widget.bind("<Button-3>", show_menu)
    for key in ("c", "C", "v", "V", "x", "X", "a", "A"):
        widget.bind(f"<Control-{key}>", lambda e:
            widget.event_generate("<<Copy>>") if key.lower() == "c"
            else widget.event_generate("<<Paste>>") if key.lower() == "v"
            else widget.event_generate("<<Cut>>") if key.lower() == "x"
            else widget.event_generate("<<SelectAll>>")
        )

# --- Создание основного окна ---
root = tk.Tk()
root.title("Video Downloader")
root.geometry("600x700")
root.resizable(False, False)

config = load_config()

url_var = tk.StringVar(value=config.get("video_url", ""))
folder_path = tk.StringVar(value=config.get("download_folder", get_default_download_dir()))
format_options = []

audio_only_var = tk.BooleanVar(value=config.get("audio_only", False))

tk.Label(root, text="Введите URL видео:").pack(pady=5)
url_entry = tk.Entry(root, width=50, textvariable=url_var)
url_entry.pack(pady=5)
attach_context_menu(url_entry)
disabled_controls.append(url_entry)

tk.Label(root, text="Выберите папку загрузки:").pack(pady=5)
folder_entry = tk.Entry(root, width=50, textvariable=folder_path, state="readonly")
folder_entry.pack(pady=5)
attach_context_menu(folder_entry)
disabled_controls.append(folder_entry)

folder_button = tk.Button(root, text="Выбрать папку загрузки", command=select_folder)
folder_button.pack(pady=5)
disabled_controls.append(folder_button)

def update_audio_only_state():
    if audio_only_var.get():
        fetch_button.config(state=tk.DISABLED)
        format_list.config(state=tk.DISABLED)
    else:
        fetch_button.config(state=tk.NORMAL)
        format_list.config(state=tk.NORMAL)
    save_config()

audio_only_check = tk.Checkbutton(
    root, text="Audio only (mp3)", variable=audio_only_var,
    command=update_audio_only_state
)
audio_only_check.pack(pady=5)

fetch_button = tk.Button(root, text="Получить форматы", command=fetch_formats)
fetch_button.pack(pady=10)
disabled_controls.append(fetch_button)

tk.Label(root, text="Доступные форматы:").pack(pady=5)
format_list = tk.Listbox(root, width=80, height=10, selectmode=tk.SINGLE)
format_list.pack(pady=5)
disabled_controls.append(format_list)

if config.get("formats"):
    for item in config["formats"]:
        if isinstance(item, dict):
            label = (f"{item.get('resolution', 'audio')} | {item.get('ext', 'unknown')} "
                     f"| {item.get('format_note', '')} "
                     + ("+ffmpeg" if "+" in item.get("format", "") else ""))
            format_options.append(item)
            format_list.insert(tk.END, label)
        else:
            format_list.insert(tk.END, str(item))

    if 0 <= config.get("last_selected_format_index", -1) < format_list.size():
        try:
            format_list.selection_set(config["last_selected_format_index"])
        except Exception:
            pass

if audio_only_var.get():
    fetch_button.config(state=tk.DISABLED)
    format_list.config(state=tk.DISABLED)

download_frame = tk.Frame(root)
download_frame.pack(pady=10)

download_button = tk.Button(
    download_frame, text="Скачать выбранный формат",
    command=download_selected_format
)
download_button.pack(side=tk.LEFT, padx=5)
disabled_controls.append(download_button)

open_folder_button = tk.Button(
    download_frame, text="Открыть папку",
    command=open_result_folder,
    state=tk.DISABLED
)
open_folder_button.pack(side=tk.LEFT, padx=5)

play_button = tk.Button(
    download_frame, text="Воспроизвести",
    command=play_downloaded_file,
    state=tk.DISABLED
)
play_button.pack(side=tk.LEFT, padx=5)

control_frame = tk.Frame(root)
control_frame.pack(pady=5)

pause_button = tk.Button(control_frame, text="Пауза", command=toggle_pause, state=tk.DISABLED)
pause_button.pack(side=tk.LEFT, padx=5)
stop_button = tk.Button(control_frame, text="Остановить", command=stop_download, state=tk.DISABLED)
stop_button.pack(side=tk.LEFT, padx=5)

progress_bar = ttk.Progressbar(
    root, orient="horizontal", length=500,
    mode="determinate", maximum=100
)
progress_bar.pack(pady=5)
if "last_progress" in config:
    try:
        progress_bar['value'] = float(config["last_progress"])
    except Exception:
        progress_bar['value'] = 0

log_text = scrolledtext.ScrolledText(root, width=70, height=10,
                                     state="normal", bg="black",
                                     fg="white", insertbackground="white")
log_text.pack(pady=10)
attach_context_menu(log_text)

root.mainloop()

