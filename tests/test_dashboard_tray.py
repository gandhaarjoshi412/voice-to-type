import unittest
import os
import tempfile
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from src.core.storage import StorageManager
from src.ui.tray import create_tray_icon, VoiceTypeTray
from src.ui.dashboard import AnalyticsDashboard
from src.ui.overlay import GlassOverlay
from src.ui.finder import FinderWindow

# Ensure a QApplication exists for widget testing
app = QApplication.instance() or QApplication(sys.argv)

class TestDashboardAndTray(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(data_dir=self.temp_dir.name)
        # Populate dummy data
        self.storage.add_record(
            text="Hello world test dictation for dashboard",
            audio_path="",
            window_title="VS Code",
            app_name="code.exe",
            duration=3.2
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_tray_icon(self):
        """Test rendering high-DPI QIcon for both idle and recording states."""
        icon_idle = create_tray_icon(is_recording=False)
        self.assertIsInstance(icon_idle, QIcon)
        self.assertFalse(icon_idle.isNull())

        icon_rec = create_tray_icon(is_recording=True)
        self.assertIsInstance(icon_rec, QIcon)
        self.assertFalse(icon_rec.isNull())

    def test_tray_initialization_and_state(self):
        """Test VoiceTypeTray creation, tooltips, and state updates."""
        tray = VoiceTypeTray(self.storage)
        self.assertFalse(tray.is_recording)
        self.assertIn("Ready", tray.tray_icon.toolTip())

        # Switch to recording state
        tray.set_recording_state(True)
        self.assertTrue(tray.is_recording)
        self.assertIn("Recording", tray.tray_icon.toolTip())

        # Switch back to idle state
        tray.set_recording_state(False)
        self.assertFalse(tray.is_recording)
        self.assertIn("Ready", tray.tray_icon.toolTip())

    def test_dashboard_initialization_and_refresh(self):
        """Test AnalyticsDashboard metrics presentation and refresh."""
        dashboard = AnalyticsDashboard(self.storage)
        dashboard.refresh_data()

        # KPI metrics reflect our dummy record ("Hello world test dictation for dashboard" = 6 words)
        self.assertEqual(dashboard.lbl_total_words.text(), "6")
        self.assertIn("1 dictation", dashboard.lbl_sessions_val.text().lower())
        self.assertEqual(dashboard.lbl_voice_longest.text(), "6")

        # Check state transition
        dashboard.set_recording_state(True)
        self.assertIn("Recording", dashboard.status_pill.text())
        dashboard.set_recording_state(False)
        self.assertIn("Ready", dashboard.status_pill.text())

    def test_wispr_flow_overlay_states(self):
        """Test GlassOverlay (Wispr Flow Bar) recording, transcribing, and stop states."""
        overlay = GlassOverlay(theme="paper")
        self.assertEqual(overlay.state, "IDLE")

        overlay.start_recording()
        self.assertEqual(overlay.state, "RECORDING")
        overlay._on_amplitude(0.05)
        self.assertAlmostEqual(overlay._amplitude, 0.80, places=2)

        overlay.start_transcribing("VS Code")
        self.assertEqual(overlay.state, "TRANSCRIBING")
        self.assertEqual(overlay._context_app, "VS Code")

        overlay.stop_recording()
        self.assertEqual(overlay.state, "IDLE")

    def test_wispr_flow_finder_search_and_filters(self):
        """Test FinderWindow (Wispr Flow Transcript History) search and filter pills."""
        finder = FinderWindow(self.storage)
        finder.perform_search()
        self.assertEqual(finder._active_filter, "all")
        self.assertIn("1 result", finder.count_label.text())

        finder._set_filter("today")
        self.assertEqual(finder._active_filter, "today")
        self.assertIn("1 result", finder.count_label.text())

        finder._set_filter("audio")
        self.assertEqual(finder._active_filter, "audio")
        self.assertIn("0 results", finder.count_label.text())

if __name__ == '__main__':
    unittest.main()
