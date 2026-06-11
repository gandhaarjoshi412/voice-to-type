import unittest
from unittest.mock import MagicMock, patch
import sys

# Create Fake classes to replace PyQt6 components
class FakeQWidget:
    def __init__(self, *args, **kwargs):
        self.show = MagicMock()
        self.hide = MagicMock()
        self.setStyleSheet = MagicMock()
        self.setWindowFlags = MagicMock()
        self.setAttribute = MagicMock()
        self.setFixedSize = MagicMock()
        self.move = MagicMock()
        self.setLayout = MagicMock()

class FakeQLabel(FakeQWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setText = MagicMock()
        self.setAlignment = MagicMock()

class FakeQVBoxLayout:
    def __init__(self, *args, **kwargs):
        self.addWidget = MagicMock()

class FakePyQtSignal:
    def __init__(self, *args, **kwargs):
        self.emit = MagicMock()
        self.connect = MagicMock()

class TestGlassOverlay(unittest.TestCase):
    def setUp(self):
        # Create a mock for PyQt6 and its submodules
        self.mock_qtcore = MagicMock()
        self.mock_qtcore.pyqtSignal = FakePyQtSignal
        self.mock_qtcore.Qt = MagicMock()
        self.mock_qtcore.Qt.WindowType.FramelessWindowHint = 1
        self.mock_qtcore.Qt.WindowType.WindowStaysOnTopHint = 2
        self.mock_qtcore.Qt.WindowType.Tool = 3
        self.mock_qtcore.Qt.WidgetAttribute.WA_TranslucentBackground = 4
        self.mock_qtcore.Qt.AlignmentFlag.AlignCenter = 5

        self.mock_qtwidgets = MagicMock()
        self.mock_qtwidgets.QWidget = FakeQWidget
        self.mock_qtwidgets.QLabel = FakeQLabel
        self.mock_qtwidgets.QVBoxLayout = FakeQVBoxLayout

        self.mock_qtgui = MagicMock()

        # Start patching sys.modules
        self.patcher = patch.dict('sys.modules', {
            'PyQt6': MagicMock(),
            'PyQt6.QtWidgets': self.mock_qtwidgets,
            'PyQt6.QtCore': self.mock_qtcore,
            'PyQt6.QtGui': self.mock_qtgui
        })
        self.patcher.start()

        # Force re-import of overlay.py under the mock context
        sys.modules.pop("src.ui.overlay", None)
        from src.ui.overlay import GlassOverlay
        
        self.overlay = GlassOverlay()

    def tearDown(self):
        self.patcher.stop()

    def test_initial_state(self):
        self.assertEqual(self.overlay.state, "IDLE")

    def test_start_recording(self):
        self.overlay.start_recording()
        
        self.assertEqual(self.overlay.state, "RECORDING")
        self.overlay.label.setText.assert_called_with("● Recording...")
        self.overlay.show.assert_called_once()
        self.overlay.state_changed.emit.assert_called_with("RECORDING")

    def test_stop_recording(self):
        # Set to recording first
        self.overlay.start_recording()
        
        self.overlay.stop_recording()
        
        self.assertEqual(self.overlay.state, "IDLE")
        self.overlay.label.setText.assert_called_with("Idle")
        self.overlay.hide.assert_called_once()
        self.overlay.state_changed.emit.assert_called_with("IDLE")

if __name__ == "__main__":
    unittest.main()
