import unittest
import os
import tempfile
import sqlite3
from datetime import datetime, timedelta
from src.core.storage import StorageManager

class TestStorageAnalytics(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(data_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_includes_duration_and_word_count(self):
        """Test that history table includes duration and word_count columns."""
        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(history)")
            cols = [col[1] for col in cursor.fetchall()]
            self.assertIn("duration", cols)
            self.assertIn("word_count", cols)

    def test_add_record_calculates_word_count_and_duration(self):
        """Test adding records automatically populates word_count and estimated duration."""
        self.storage.add_record(
            text="The quick brown fox jumps over the lazy dog", # 9 words
            audio_path="",
            window_title="VS Code - project",
            app_name="code.exe",
            duration=3.5
        )
        records = self.storage.search_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["word_count"], 9)
        self.assertEqual(record["duration"], 3.5)
        self.assertEqual(record["app_name"], "code.exe")

    def test_analytics_summary_and_time_saved(self):
        """
        Test WhisperFlow time saved formula:
        Manual typing baseline = 40 WPM (200 words = 5 mins = 300 sec)
        Speaking time = 60 sec
        Time saved = 300 - 60 = 240 sec (4 mins)
        Speed multiplier = 300 / 60 = 5.0x
        """
        # 100 words text
        sample_text_100 = "word " * 100
        self.storage.add_record(
            text=sample_text_100,
            audio_path="",
            window_title="Cursor IDE",
            app_name="Cursor",
            duration=30.0
        )
        self.storage.add_record(
            text=sample_text_100,
            audio_path="",
            window_title="Slack #general",
            app_name="Slack",
            duration=30.0
        )

        summary = self.storage.get_analytics_summary()
        self.assertEqual(summary["total_words"], 200)
        self.assertEqual(summary["total_sessions"], 2)
        self.assertEqual(summary["total_duration_sec"], 60.0)
        self.assertEqual(summary["today_words"], 200)
        self.assertEqual(summary["today_sessions"], 2)

        # 200 words / 40 WPM * 60 = 300 sec manual typing time
        # Speaking time = 60 sec
        # Time saved = 240 sec = 4.0 mins
        self.assertAlmostEqual(summary["time_saved_sec"], 240.0, places=1)
        self.assertAlmostEqual(summary["time_saved_min"], 4.0, places=1)
        self.assertAlmostEqual(summary["speed_multiplier"], 5.0, places=1)
        # Average speaking pace: 200 words in 1 min = 200 WPM
        self.assertAlmostEqual(summary["speaking_wpm"], 200.0, places=1)

    def test_daily_activity_returns_seven_days(self):
        """Test get_daily_activity returns 7 entries ending today."""
        self.storage.add_record(
            text="Testing daily activity tracking",
            duration=2.0
        )
        daily = self.storage.get_daily_activity(days=7)
        self.assertEqual(len(daily), 7)
        today_entry = daily[-1]
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(today_entry["date"], today_str)
        self.assertGreaterEqual(today_entry["words"], 4)
        self.assertGreaterEqual(today_entry["sessions"], 1)

    def test_top_apps_aggregation(self):
        """Test top applications distribution and name beautification."""
        self.storage.add_record("hello vscode world", app_name="code.exe")
        self.storage.add_record("another vscode message", app_name="code.exe")
        self.storage.add_record("slack announcement here", app_name="slack")

        top_apps = self.storage.get_top_apps(limit=5)
        self.assertGreaterEqual(len(top_apps), 2)
        app_names = [a["app_name"] for a in top_apps]
        self.assertIn("VS Code / Cursor", app_names)
        self.assertIn("Slack", app_names)

    def test_streak_calculation(self):
        """Test consecutive active days streak calculation."""
        # Add record for today
        self.storage.add_record("Today voice dictation")
        streak = self.storage.get_streak_days()
        self.assertEqual(streak, 1)

    def test_storage_usage_calculation(self):
        """Test audio directory disk usage reporting."""
        # Create a small dummy file in audio_dir
        dummy_file = os.path.join(self.storage.audio_dir, "test.wav")
        with open(dummy_file, "wb") as f:
            f.write(b"0" * 1024 * 1024) # 1 MB

        usage = self.storage.get_storage_usage()
        self.assertEqual(usage["file_count"], 1)
        self.assertAlmostEqual(usage["size_mb"], 1.0, places=1)
        self.assertEqual(usage["limit_mb"], 1024.0)
        self.assertAlmostEqual(usage["percent"], 0.1, places=1)

if __name__ == '__main__':
    unittest.main()
