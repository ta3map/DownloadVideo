#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

DB_PATH = 'downloads.db'

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                title TEXT,
                format_id TEXT,
                audio_only INTEGER,
                status TEXT,
                file_path TEXT,
                thumbnail_path TEXT,
                format_label TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Добавляем колонку thumbnail_path если её нет (для существующих БД)
        try:
            cursor.execute('ALTER TABLE download_history ADD COLUMN thumbnail_path TEXT')
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
        
        # Добавляем колонку format_label если её нет (для существующих БД)
        try:
            cursor.execute('ALTER TABLE download_history ADD COLUMN format_label TEXT')
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS download_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                title TEXT,
                format_id TEXT,
                audio_only INTEGER,
                download_folder TEXT,
                status TEXT DEFAULT 'pending',
                task_id TEXT,
                thumbnail_path TEXT,
                format_label TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Добавляем колонку thumbnail_path если её нет (для существующих БД)
        try:
            cursor.execute('ALTER TABLE download_queue ADD COLUMN thumbnail_path TEXT')
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
        
        # Добавляем колонку format_label если её нет (для существующих БД)
        try:
            cursor.execute('ALTER TABLE download_queue ADD COLUMN format_label TEXT')
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ui_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        self.conn.commit()
    
    def add_to_history(self, url, title, format_id, audio_only, status, file_path, thumbnail_path=None, format_label=None):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO download_history (url, title, format_id, audio_only, status, file_path, thumbnail_path, format_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (url, title, format_id, 1 if audio_only else 0, status, file_path, thumbnail_path, format_label))
        self.conn.commit()
        return cursor.lastrowid
    
    def add_to_queue(self, url, title, format_id, audio_only, download_folder, thumbnail_path=None, format_label=None):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO download_queue (url, title, format_id, audio_only, download_folder, thumbnail_path, format_label)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (url, title, format_id, 1 if audio_only else 0, download_folder, thumbnail_path, format_label))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_queue(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM download_queue ORDER BY id')
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    def get_queue_item(self, queue_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM download_queue WHERE id = ?', (queue_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
    
    def get_pending_queue(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM download_queue WHERE status = ? ORDER BY id', ('pending',))
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    def update_queue_item(self, queue_id, **kwargs):
        cursor = self.conn.cursor()
        updates = []
        values = []
        for key, value in kwargs.items():
            updates.append(f'{key} = ?')
            values.append(value)
        values.append(queue_id)
        cursor.execute(f'UPDATE download_queue SET {", ".join(updates)} WHERE id = ?', values)
        self.conn.commit()
    
    def clear_queue(self):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM download_queue')
        self.conn.commit()
    
    def get_history(self, limit=50):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM download_history ORDER BY created_at DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    def get_history_item(self, history_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM download_history WHERE id = ?', (history_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
    
    def save_ui_state(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO ui_state (key, value) VALUES (?, ?)', (key, value))
        self.conn.commit()
    
    def get_all_ui_state(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT key, value FROM ui_state')
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    
    def count_active_downloads(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM download_queue WHERE status = ?', ('downloading',))
        return cursor.fetchone()[0]
    
    def delete_queue_item(self, queue_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM download_queue WHERE id = ?', (queue_id,))
        self.conn.commit()
    
    def delete_history_item(self, history_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM download_history WHERE id = ?', (history_id,))
        self.conn.commit()

