import unittest
from unittest.mock import MagicMock, patch
import sys

class TestVoiceToTypeService(unittest.TestCase):
    def setUp(self):
        # Create mocks for external modules
        self.pyqt6_mock = MagicMock()
        self.pynput_mock = MagicMock()

        # Start patching sys.modules
        self.sys_modules_patcher = patch.dict('sys.modules', {
            'PyQt6': self.pyqt6_mock,
            'PyQt6.QtWidgets': MagicMock(),
            'PyQt6.QtCore': MagicMock(),
            'PyQt6.QtGui': MagicMock(),
            'pynput': self.pynput_mock,
            'pynput.keyboard': MagicMock()
        })
        self.sys_modules_patcher.start()

        # Clean imports and import VoiceToTypeService
        sys.modules.pop("src.main", None)
        sys.modules.pop("src.ui.overlay", None)
        sys.modules.pop("src.service.listener", None)
        sys.modules.pop("src.core.recorder", None)
        sys.modules.pop("src.core.transcriber", None)
        sys.modules.pop("src.core.typer", None)
        from src.main import VoiceToTypeService

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

        self.service = VoiceToTypeService(duration=2)

    def tearDown(self):
        self.patcher_recorder.stop()
        self.patcher_transcriber.stop()
        self.patcher_typer.stop()
        self.patcher_overlay.stop()
        self.patcher_listener.stop()
        self.sys_modules_patcher.stop()

    def test_execute_pipeline_success(self):
        """Test the successful end-to-end flow of the pipeline."""
        test_text = "Hello world"
        self.mock_transcriber.transcribe.return_value = test_text

        # Manually trigger the pipeline logic
        self.service._execute_pipeline()

        # Verify sequence: Overlay Start -> Record -> Overlay Stop -> Transcribe -> Type
        self.mock_overlay.trigger_start.emit.assert_called_once()
        self.mock_recorder.record.assert_called_once()
        self.mock_overlay.trigger_stop.emit.assert_called_once()
        self.mock_transcriber.transcribe.assert_called_once()
        self.mock_typer.type_text.assert_called_once_with(test_text)

    def test_execute_pipeline_transcription_failure(self):
        """Test that overlay is stopped even if transcription fails."""
        self.mock_transcriber.transcribe.side_effect = Exception("Transcription Error")

        self.service._execute_pipeline()

        # Overlay should still be stopped
        self.mock_overlay.trigger_start.emit.assert_called_once()
        self.mock_overlay.trigger_stop.emit.assert_called_once()
        # Typer should not be called
        self.mock_typer.type_text.assert_not_called()

    def test_execute_pipeline_recording_failure(self):
        """Test that overlay is stopped even if recording fails."""
        self.mock_recorder.record.side_effect = Exception("Recording Error")

        self.service._execute_pipeline()

        # Overlay should still be stopped
        self.mock_overlay.trigger_start.emit.assert_called_once()
        self.mock_overlay.trigger_stop.emit.assert_called_once()
        # Transcriber should not be called
        self.mock_transcriber.transcribe.assert_not_called()

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
