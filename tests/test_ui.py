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
        self.setGraphicsEffect = MagicMock()
        self.update = MagicMock()
        self.width = MagicMock(return_value=300)
        self.height = MagicMock(return_value=100)

class FakeQGraphicsOpacityEffect(MagicMock):
    def setOpacity(self, value):
        pass

class FakeQPropertyAnimation(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.setDuration = MagicMock()
        self.setStartValue = MagicMock()
        self.setEndValue = MagicMock()
        self.setEasingCurve = MagicMock()
        self.start = MagicMock()
        self.stop = MagicMock()
        # Mock the finished signal connection
        self.finished = MagicMock()

class FakeQTimer(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.start = MagicMock()
        self.stop = MagicMock()
        self.timeout = MagicMock()

class FakePyQtSignal:
    def __init__(self, *args, **kwargs):
        self.emit = MagicMock()
        self.connect = MagicMock()

class TestGlassOverlay(unittest.TestCase):
    def setUp(self):
        # Create a mock for PyQt6 and its submodules
        self.mock_qtcore = MagicMock()
        self.mock_qtcore.pyqtSignal = FakePyQtSignal
        self.mock_qtcore.QTimer = FakeQTimer
        self.mock_qtcore.QPropertyAnimation = FakeQPropertyAnimation
        self.mock_qtcore.Qt = MagicMock()
        self.mock_qtcore.Qt.WindowType.FramelessWindowHint = 1
        self.mock_qtcore.Qt.WindowType.WindowStaysOnTopHint = 2
        self.mock_qtcore.Qt.WindowType.Tool = 3
        self.mock_qtcore.Qt.WidgetAttribute.WA_TranslucentBackground = 4
        self.mock_qtcore.Qt.AlignmentFlag.AlignCenter = 5

        self.mock_qtwidgets = MagicMock()
        self.mock_qtwidgets.QWidget = FakeQWidget
        self.mock_qtwidgets.QGraphicsOpacityEffect = FakeQGraphicsOpacityEffect
        # Mock QApplication so we can request primaryScreen geometry
        mock_app = MagicMock()
        mock_screen_geometry = MagicMock()
        mock_screen_geometry.width.return_value = 1920
        mock_screen_geometry.height.return_value = 1080
        mock_app.primaryScreen.return_value.geometry.return_value = mock_screen_geometry
        self.mock_qtwidgets.QApplication = mock_app

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
        self.overlay.show.assert_called_once()
        self.overlay.state_changed.emit.assert_called_with("RECORDING")

    def test_stop_recording(self):
        self.overlay.start_recording()
        self.overlay.stop_recording()
        
        self.assertEqual(self.overlay.state, "IDLE")
        self.overlay.state_changed.emit.assert_called_with("IDLE")

if __name__ == "__main__":
    unittest.main()
