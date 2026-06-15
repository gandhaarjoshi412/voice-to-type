import sqlite3
import os
import time
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class StorageManager:
    def __init__(self, data_dir="data"):
        self.data_dir = os.path.abspath(data_dir)
        self.audio_dir = os.path.join(self.data_dir, "audio_backup")
        self.db_path = os.path.join(self.data_dir, "history.db")
        
        # Ensure directories exist
        os.makedirs(self.audio_dir, exist_ok=True)
        
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        text TEXT NOT NULL,
                        audio_path TEXT,
                        window_title TEXT,
                        app_name TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing database: {e}")

    def add_record(self, text: str, audio_path: str, window_title: str, app_name: str):
        if not text:
            return
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Store local time for easier querying/display
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    INSERT INTO history (timestamp, text, audio_path, window_title, app_name)
                    VALUES (?, ?, ?, ?, ?)
                """, (now_str, text, audio_path, window_title, app_name))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding record to DB: {e}")

    def search_records(self, query: str = ""):
        """
        Search records. If query is empty, return recent records.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if query:
                    # Simple LIKE search across text, window_title, app_name
                    search_term = f"%{query}%"
                    cursor.execute("""
                        SELECT * FROM history 
                        WHERE text LIKE ? OR window_title LIKE ? OR app_name LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT 100
                    """, (search_term, search_term, search_term))
                else:
                    cursor.execute("""
                        SELECT * FROM history 
                        ORDER BY timestamp DESC
                        LIMIT 50
                    """)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error searching records: {e}")
            return []

    def cleanup(self):
        """
        Performs all cleanup tasks:
        1. Delete text records older than 14 days.
        2. Delete audio files older than 7 days.
        3. Enforce 1GB audio folder size limit.
        """
        self._cleanup_db_records()
        self._cleanup_audio_files()
        self._enforce_audio_size_limit()

    def _cleanup_db_records(self):
        """Deletes DB records older than 14 days."""
        cutoff_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Before deleting, we don't necessarily need to delete the audio file here,
                # as audio files have their own 7-day cleanup logic.
                cursor.execute("DELETE FROM history WHERE timestamp < ?", (cutoff_date,))
                conn.commit()
        except Exception as e:
            logger.error(f"Error cleaning up DB records: {e}")

    def _cleanup_audio_files(self):
        """Deletes audio files older than 7 days."""
        now = time.time()
        seven_days_sec = 7 * 24 * 60 * 60
        
        try:
            for filename in os.listdir(self.audio_dir):
                file_path = os.path.join(self.audio_dir, filename)
                if os.path.isfile(file_path):
                    file_age = now - os.path.getmtime(file_path)
                    if file_age > seven_days_sec:
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            logger.error(f"Failed to delete old audio file {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error accessing audio directory for cleanup: {e}")

    def _enforce_audio_size_limit(self):
        """Ensures the audio_backup directory does not exceed 1GB (1024 * 1024 * 1024 bytes)."""
        max_size_bytes = 1024 * 1024 * 1024 # 1 GB
        try:
            files = []
            total_size = 0
            
            for filename in os.listdir(self.audio_dir):
                file_path = os.path.join(self.audio_dir, filename)
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    mtime = os.path.getmtime(file_path)
                    files.append({'path': file_path, 'size': size, 'mtime': mtime})
                    total_size += size
            
            # If over limit, sort by oldest first and delete until under limit
            if total_size > max_size_bytes:
                files.sort(key=lambda x: x['mtime'])
                for f in files:
                    if total_size <= max_size_bytes:
                        break
                    try:
                        os.remove(f['path'])
                        total_size -= f['size']
                    except Exception as e:
                        logger.error(f"Failed to delete audio file during size enforcement {f['path']}: {e}")
        except Exception as e:
            logger.error(f"Error enforcing audio size limit: {e}")
