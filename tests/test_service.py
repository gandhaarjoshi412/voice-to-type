import unittest
from unittest.mock import MagicMock, patch
import sys

# Workaround for Windows/Anaconda SSL DLL loading mismatch
import ssl
orig_create_default_context = ssl.create_default_context
def dummy_create_default_context(*args, **kwargs):
    try:
        return orig_create_default_context(*args, **kwargs)
    except Exception:
        return MagicMock()
ssl.create_default_context = dummy_create_default_context

# Mock external GUI/PyQt6 imports at module level before importing src.main
sys.modules['PyQt6'] = MagicMock()
sys.modules['PyQt6.QtWidgets'] = MagicMock()
sys.modules['PyQt6.QtCore'] = MagicMock()
sys.modules['PyQt6.QtGui'] = MagicMock()

from src.main import VoiceToTypeService

class TestVoiceToTypeService(unittest.TestCase):
    def setUp(self):
        # Patch components in src.main
        self.patcher_recorder = patch('src.main.Recorder')
        self.patcher_transcriber = patch('src.main.Transcriber')
        self.patcher_typer = patch('src.main.Typer')
        self.patcher_overlay = patch('src.main.GlassOverlay')
        self.patcher_listener = patch('src.main.HotkeyListener')
        self.patcher_finder = patch('src.main.FinderWindow')
        self.patcher_dashboard = patch('src.main.AnalyticsDashboard')
        self.patcher_tray = patch('src.main.VoiceTypeTray')

        self.mock_recorder_cls = self.patcher_recorder.start()
        self.mock_transcriber_cls = self.patcher_transcriber.start()
        self.mock_typer_cls = self.patcher_typer.start()
        self.mock_overlay_cls = self.patcher_overlay.start()
        self.mock_listener_cls = self.patcher_listener.start()
        self.mock_finder_cls = self.patcher_finder.start()
        self.mock_dashboard_cls = self.patcher_dashboard.start()
        self.mock_tray_cls = self.patcher_tray.start()

        # Get instances
        self.mock_recorder = self.mock_recorder_cls.return_value
        self.mock_transcriber = self.mock_transcriber_cls.return_value
        self.mock_typer = self.mock_typer_cls.return_value
        self.mock_overlay = self.mock_overlay_cls.return_value
        self.mock_listener = self.mock_listener_cls.return_value
        self.mock_finder = self.mock_finder_cls.return_value
        self.mock_dashboard = self.mock_dashboard_cls.return_value
        self.mock_tray = self.mock_tray_cls.return_value

        self.service = VoiceToTypeService()

    def tearDown(self):
        self.patcher_recorder.stop()
        self.patcher_transcriber.stop()
        self.patcher_typer.stop()
        self.patcher_overlay.stop()
        self.patcher_listener.stop()
        self.patcher_finder.stop()
        self.patcher_dashboard.stop()
        self.patcher_tray.stop()

    def test_run_starts_listener(self):
        """Test that run() starts the listener with correct callbacks."""
        self.service.run()
        self.mock_listener.start.assert_called_once()
        args, kwargs = self.mock_listener.start.call_args
        
        self.assertIn('callback', kwargs)
        self.assertTrue(callable(kwargs['callback']))
        
        self.assertIn('search_callback', kwargs)
        self.assertTrue(callable(kwargs['search_callback']))
        
        self.assertIn('dashboard_callback', kwargs)
        self.assertTrue(callable(kwargs['dashboard_callback']))
        
        self.assertIn('quit_callback', kwargs)
        self.assertTrue(callable(kwargs['quit_callback']))

    def test_stop_shuts_down_service(self):
        """Test that stop() shuts down the listener, tray, and overlay."""
        self.service.stop()
        self.mock_listener.stop.assert_called_once()
        self.mock_tray.hide.assert_called_once()
        self.mock_overlay.trigger_stop.emit.assert_called_once()

    @patch('PyQt6.QtWidgets.QApplication')
    def test_quit_callback_quits_app(self, mock_qapp_cls):
        """Test that _quit stops the service and shuts down the QApplication."""
        mock_qapp_instance = MagicMock()
        mock_qapp_cls.instance.return_value = mock_qapp_instance
        
        # Call _quit
        self.service._quit()
        
        # Check that stop was called
        self.mock_listener.stop.assert_called_once()
        self.mock_overlay.trigger_stop.emit.assert_called_once()
        
        # Check that QApplication.quit() was invoked
        mock_qapp_cls.instance.assert_called_once()
        mock_qapp_instance.quit.assert_called_once()

if __name__ == '__main__':
    unittest.main()
