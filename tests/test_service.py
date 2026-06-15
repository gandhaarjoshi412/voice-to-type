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

# Mock external imports at module level before importing src.main
sys.modules['pynput'] = MagicMock()
sys.modules['pynput.keyboard'] = MagicMock()
sys.modules['PyQt6'] = MagicMock()
sys.modules['PyQt6.QtWidgets'] = MagicMock()
sys.modules['PyQt6.QtCore'] = MagicMock()
sys.modules['PyQt6.QtGui'] = MagicMock()

from src.main import VoiceToTypeService

class TestVoiceToTypeService(unittest.TestCase):
    def setUp(self):
        # Patch the components within src.main to avoid using real implementations
        self.patcher_recorder = patch('src.main.Recorder')
        self.patcher_transcriber = patch('src.main.Transcriber')
        self.patcher_typer = patch('src.main.Typer')
        self.patcher_overlay = patch('src.main.GlassOverlay')
        self.patcher_listener = patch('src.main.HotkeyListener')

        self.mock_recorder_cls = self.patcher_recorder.start()
        self.mock_transcriber_cls = self.patcher_transcriber.start()
        self.mock_typer_cls = self.patcher_typer.start()
        self.mock_overlay_cls = self.patcher_overlay.start()
        self.mock_listener_cls = self.patcher_listener.start()

        # Get the return values of the mock classes
        self.mock_recorder = self.mock_recorder_cls.return_value
        self.mock_transcriber = self.mock_transcriber_cls.return_value
        self.mock_typer = self.mock_typer_cls.return_value
        self.mock_overlay = self.mock_overlay_cls.return_value
        self.mock_listener = self.mock_listener_cls.return_value

        self.service = VoiceToTypeService()

    def tearDown(self):
        self.patcher_recorder.stop()
        self.patcher_transcriber.stop()
        self.patcher_typer.stop()
        self.patcher_overlay.stop()
        self.patcher_listener.stop()

    def test_run_starts_listener(self):
        """Test that run() starts the listener with a callback."""
        self.service.run()
        self.mock_listener.start.assert_called_once()
        args, kwargs = self.mock_listener.start.call_args
        self.assertIn('callback', kwargs)
        self.assertTrue(callable(kwargs['callback']))

    def test_stop_shuts_down_service(self):
        """Test that stop() shuts down the listener and overlay."""
        self.service.stop()
        self.mock_listener.stop.assert_called_once()
        self.mock_overlay.trigger_stop.emit.assert_called_once()

if __name__ == '__main__':
    unittest.main()
