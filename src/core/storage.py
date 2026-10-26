import sqlite3
import os
import time
from contextlib import closing
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

    def _connect(self):
        return closing(sqlite3.connect(self.db_path))

    def _init_db(self):
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        text TEXT NOT NULL,
                        audio_path TEXT,
                        window_title TEXT,
                        app_name TEXT,
                        duration REAL DEFAULT 0.0,
                        word_count INTEGER DEFAULT 0
                    )
                """)
                # Handle schema migration for existing databases
                cursor.execute("PRAGMA table_info(history)")
                existing_cols = [col[1] for col in cursor.fetchall()]
                if "duration" not in existing_cols:
                    cursor.execute("ALTER TABLE history ADD COLUMN duration REAL DEFAULT 0.0")
                if "word_count" not in existing_cols:
                    cursor.execute("ALTER TABLE history ADD COLUMN word_count INTEGER DEFAULT 0")
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing database: {e}")

    def add_record(self, text: str, audio_path: str = "", window_title: str = "Unknown", app_name: str = "Unknown", duration: float = 0.0):
        if not text:
            return
            
        try:
            clean_text = text.strip()
            word_count = len(clean_text.split()) if clean_text else 0
            
            # If duration not provided, try to calculate from wav file or estimate from words
            if duration <= 0.0 and audio_path and os.path.exists(audio_path):
                try:
                    from scipy.io import wavfile
                    sr, data = wavfile.read(audio_path)
                    duration = round(float(len(data)) / float(sr), 2)
                except Exception:
                    duration = round(float(word_count) / 150.0 * 60.0, 2)
            elif duration <= 0.0 and word_count > 0:
                duration = round(float(word_count) / 150.0 * 60.0, 2)

            with self._connect() as conn:
                cursor = conn.cursor()
                # Store local time for easier querying/display
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    INSERT INTO history (timestamp, text, audio_path, window_title, app_name, duration, word_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (now_str, clean_text, audio_path, window_title, app_name, float(duration), int(word_count)))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding record to DB: {e}")

    def search_records(self, query: str = ""):
        """
        Search records. If query is empty, return recent records.
        """
        try:
            with self._connect() as conn:
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
            with self._connect() as conn:
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

    def get_storage_usage(self):
        """Returns audio backup folder disk usage stats."""
        total_size = 0
        file_count = 0
        try:
            for filename in os.listdir(self.audio_dir):
                file_path = os.path.join(self.audio_dir, filename)
                if os.path.isfile(file_path):
                    total_size += os.path.getsize(file_path)
                    file_count += 1
        except Exception as e:
            logger.error(f"Error reading audio folder size: {e}")

        size_mb = round(total_size / (1024 * 1024), 2)
        limit_mb = 1024.0
        percent = min(100.0, round((size_mb / limit_mb) * 100, 1))
        return {
            "size_bytes": total_size,
            "size_mb": size_mb,
            "limit_mb": limit_mb,
            "percent": percent,
            "file_count": file_count
        }

    def get_streak_days(self):
        """Calculates consecutive active days with at least one transcription up to today."""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT date(timestamp) as day
                    FROM history
                    ORDER BY day DESC
                """)
                days = [row[0] for row in cursor.fetchall()]
                if not days:
                    return 0

                today_str = datetime.now().strftime("%Y-%m-%d")
                yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

                # If no activity today or yesterday, streak is broken
                if days[0] != today_str and days[0] != yesterday_str:
                    return 0

                streak = 0
                expected_date = datetime.strptime(days[0], "%Y-%m-%d").date()
                for d_str in days:
                    d = datetime.strptime(d_str, "%Y-%m-%d").date()
                    if d == expected_date:
                        streak += 1
                        expected_date -= timedelta(days=1)
                    else:
                        break
                return streak
        except Exception as e:
            logger.error(f"Error computing streak: {e}")
            return 0

    def get_analytics_summary(self):
        """
        WhisperFlow-style Productivity & Usage Analytics Summary.
        Calculates time saved, words spoken, speed multiplier, today stats, and active streak.
        """
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                
                # All-time aggregates
                cursor.execute("""
                    SELECT 
                        COUNT(*),
                        COALESCE(SUM(word_count), 0),
                        COALESCE(SUM(LENGTH(text)), 0),
                        COALESCE(SUM(duration), 0.0)
                    FROM history
                """)
                row = cursor.fetchone()
                total_sessions = row[0] or 0
                total_words = row[1] or 0
                total_chars = row[2] or 0
                total_duration_sec = float(row[3] or 0.0)

                # Today's aggregates
                today_str = datetime.now().strftime("%Y-%m-%d")
                cursor.execute("""
                    SELECT 
                        COUNT(*),
                        COALESCE(SUM(word_count), 0),
                        COALESCE(SUM(duration), 0.0)
                    FROM history
                    WHERE date(timestamp) = ?
                """, (today_str,))
                today_row = cursor.fetchone()
                today_sessions = today_row[0] or 0
                today_words = today_row[1] or 0
                today_duration_sec = float(today_row[2] or 0.0)

            # WhisperFlow Time-Saved Metrics
            # Baseline manual typing speed: 40 Words Per Minute
            typing_speed_wpm = 40.0
            manual_typing_time_sec = (total_words / typing_speed_wpm) * 60.0
            
            # Speaking time in seconds
            actual_speaking_sec = total_duration_sec if total_duration_sec > 0 else (total_words / 150.0) * 60.0
            time_saved_sec = max(0.0, manual_typing_time_sec - actual_speaking_sec)
            
            # Today's time saved
            today_typing_sec = (today_words / typing_speed_wpm) * 60.0
            today_speaking_sec = today_duration_sec if today_duration_sec > 0 else (today_words / 150.0) * 60.0
            today_time_saved_sec = max(0.0, today_typing_sec - today_speaking_sec)

            # Speed multiplier (e.g. 3.8x faster than manual typing)
            if actual_speaking_sec > 0 and manual_typing_time_sec > 0:
                speed_multiplier = round(manual_typing_time_sec / max(1.0, actual_speaking_sec), 1)
            else:
                speed_multiplier = 3.5

            # Average speaking pace (WPM)
            if total_duration_sec > 5.0 and total_words > 0:
                speaking_wpm = round((total_words / (total_duration_sec / 60.0)), 1)
            else:
                speaking_wpm = 145.0

            streak_days = self.get_streak_days()
            storage_stats = self.get_storage_usage()

            return {
                "total_words": total_words,
                "total_characters": total_chars,
                "total_sessions": total_sessions,
                "total_duration_sec": round(total_duration_sec, 1),
                "total_duration_min": round(total_duration_sec / 60.0, 1),
                "time_saved_sec": round(time_saved_sec, 1),
                "time_saved_min": round(time_saved_sec / 60.0, 1),
                "time_saved_hrs": round(time_saved_sec / 3600.0, 2),
                "speed_multiplier": speed_multiplier,
                "speaking_wpm": speaking_wpm,
                "today_words": today_words,
                "today_sessions": today_sessions,
                "today_duration_sec": round(today_duration_sec, 1),
                "today_time_saved_min": round(today_time_saved_sec / 60.0, 1),
                "streak_days": streak_days,
                "storage": storage_stats
            }
        except Exception as e:
            logger.error(f"Error computing analytics summary: {e}")
            return {
                "total_words": 0,
                "total_characters": 0,
                "total_sessions": 0,
                "total_duration_sec": 0.0,
                "total_duration_min": 0.0,
                "time_saved_sec": 0.0,
                "time_saved_min": 0.0,
                "time_saved_hrs": 0.0,
                "speed_multiplier": 3.5,
                "speaking_wpm": 145.0,
                "today_words": 0,
                "today_sessions": 0,
                "today_duration_sec": 0.0,
                "today_time_saved_min": 0.0,
                "streak_days": 0,
                "storage": {"size_mb": 0.0, "limit_mb": 1024.0, "percent": 0.0, "file_count": 0}
            }

    def get_daily_activity(self, days=7):
        """
        Returns activity data for the past `days` (words, sessions, duration)
        with contiguous calendar days even if 0.
        """
        result = []
        now = datetime.now()
        dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
        
        counts_by_date = {}
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                min_date = dates[0]
                cursor.execute("""
                    SELECT 
                        date(timestamp) as day,
                        COALESCE(SUM(word_count), 0),
                        COUNT(*),
                        COALESCE(SUM(duration), 0.0)
                    FROM history
                    WHERE date(timestamp) >= ?
                    GROUP BY day
                """, (min_date,))
                for row in cursor.fetchall():
                    counts_by_date[row[0]] = {
                        "words": row[1] or 0,
                        "sessions": row[2] or 0,
                        "duration": round(float(row[3] or 0.0), 1)
                    }
        except Exception as e:
            logger.error(f"Error fetching daily activity: {e}")

        for d_str in dates:
            d_obj = datetime.strptime(d_str, "%Y-%m-%d")
            day_name = d_obj.strftime("%a") # e.g. Mon, Tue
            stats = counts_by_date.get(d_str, {"words": 0, "sessions": 0, "duration": 0.0})
            result.append({
                "date": d_str,
                "day_label": day_name,
                "words": stats["words"],
                "sessions": stats["sessions"],
                "duration": stats["duration"]
            })
        return result

    def get_top_apps(self, limit=6):
        """
        Returns app distribution ranked by word count and session count.
        """
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        app_name,
                        COUNT(*) as sessions,
                        COALESCE(SUM(word_count), 0) as words
                    FROM history
                    GROUP BY app_name
                    ORDER BY words DESC, sessions DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()

                cursor.execute("SELECT COALESCE(SUM(word_count), 0) FROM history")
                total_words = cursor.fetchone()[0] or 1

                apps = []
                for row in rows:
                    raw_app = row[0] or "Unknown"
                    display_name = self._clean_app_name(raw_app)
                    sessions = row[1] or 0
                    words = row[2] or 0
                    percent = round((words / max(1, total_words)) * 100, 1)
                    apps.append({
                        "raw_app": raw_app,
                        "app_name": display_name,
                        "sessions": sessions,
                        "words": words,
                        "percent": percent
                    })
                return apps
        except Exception as e:
            logger.error(f"Error fetching top apps: {e}")
            return []

    def _clean_app_name(self, raw_app: str) -> str:
        """Beautifies application process names into friendly brand names."""
        if not raw_app or raw_app.lower() in ("unknown", "unknown app"):
            return "General App"
        app_lower = raw_app.lower()
        if "code" in app_lower or "cursor" in app_lower:
            return "VS Code / Cursor"
        if "chrome" in app_lower:
            return "Google Chrome"
        if "firefox" in app_lower:
            return "Firefox"
        if "slack" in app_lower:
            return "Slack"
        if "discord" in app_lower:
            return "Discord"
        if "terminal" in app_lower or "bash" in app_lower or "zsh" in app_lower or "cmd" in app_lower:
            return "Terminal"
        if "notepad" in app_lower or "sublime" in app_lower:
            return "Text Editor"
        if "outlook" in app_lower or "mail" in app_lower:
            return "Email Client"
        return raw_app.replace(".exe", "").capitalize()

    def get_recent_sessions(self, limit=20):
        """Returns the most recent dictation sessions."""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM history
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching recent sessions: {e}")
            return []

    def get_longest_streak(self):
        """Longest run of consecutive days with at least one dictation."""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT date(timestamp) FROM history ORDER BY 1 ASC")
                days = [datetime.strptime(r[0], "%Y-%m-%d").date() for r in cursor.fetchall() if r[0]]
            longest = run = 0
            prev = None
            for d in days:
                run = run + 1 if prev and (d - prev).days == 1 else 1
                longest = max(longest, run)
                prev = d
            return longest
        except Exception as e:
            logger.error(f"Error computing longest streak: {e}")
            return 0

    def get_voice_stats(self):
        """Per-dictation voice stats plus a 24-bucket hour-of-day word distribution."""
        stats = {"avg_words": 0, "longest_words": 0, "total_duration_sec": 0.0, "hourly": [0] * 24}
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COALESCE(AVG(word_count), 0), COALESCE(MAX(word_count), 0),
                           COALESCE(SUM(duration), 0.0)
                    FROM history
                """)
                row = cursor.fetchone()
                stats["avg_words"] = int(round(row[0] or 0))
                stats["longest_words"] = int(row[1] or 0)
                stats["total_duration_sec"] = float(row[2] or 0.0)
                cursor.execute("""
                    SELECT CAST(strftime('%H', timestamp) AS INTEGER), COALESCE(SUM(word_count), 0)
                    FROM history GROUP BY 1
                """)
                for hour, words in cursor.fetchall():
                    if hour is not None and 0 <= hour < 24:
                        stats["hourly"][hour] = int(words or 0)
        except Exception as e:
            logger.error(f"Error computing voice stats: {e}")
        return stats

