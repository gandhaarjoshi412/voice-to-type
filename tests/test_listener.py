import unittest
from unittest.mock import MagicMock, patch
import sys

class TestHotkeyListener(unittest.TestCase):
    def setUp(self):
        # Create a fresh mock pynput
        self.mock_pynput = MagicMock()
        
        # Start patching sys.modules
        self.patcher = patch.dict('sys.modules', {
            'pynput': self.mock_pynput,
            'pynput.keyboard': self.mock_pynput.keyboard
        })
        self.patcher.start()
        
        # Force fresh import of the listener module
        sys.modules.pop("src.service.listener", None)
        from src.service.listener import HotkeyListener
        
        self.mock_callback = MagicMock()
        self.hotkeys = {'<ctrl>+<shift>+v': self.mock_callback}
        self.listener = HotkeyListener(self.hotkeys)

    def tearDown(self):
        self.patcher.stop()

    @patch('src.service.listener.keyboard.GlobalHotKeys')
    @patch('src.service.listener.threading.Thread')
    def test_start_success(self, mock_thread, mock_global_hotkeys):
        """Test that start() correctly initializes and starts the listener thread."""
        # Setup mocks
        mock_listener_instance = mock_global_hotkeys.return_value
        
        self.listener.start()
        
        # Verify GlobalHotKeys was called with correct hotkeys
        mock_global_hotkeys.assert_called_once_with(self.hotkeys)
        
        # Verify Thread was started with the listener's start method
        mock_thread.assert_called_once()
        args, kwargs = mock_thread.call_args
        self.assertEqual(kwargs['target'], mock_listener_instance.start)
        self.assertTrue(kwargs['daemon'])
        
        # Verify thread was actually started
        mock_thread.return_value.start.assert_called_once()

    @patch('src.service.listener.keyboard.GlobalHotKeys')
    def test_start_failure(self, mock_global_hotkeys):
        """Test that start() handles exceptions during initialization."""
        mock_global_hotkeys.side_effect = Exception("Initialization failed")
        
        with self.assertRaises(Exception) as context:
            self.listener.start()
        
        self.assertTrue("Initialization failed" in str(context.exception))
        self.assertIsNone(self.listener.listener)

    @patch('src.service.listener.keyboard.GlobalHotKeys')
    @patch('src.service.listener.threading.Thread')
    def test_stop(self, mock_thread, mock_global_hotkeys):
        """Test that stop() correctly stops the listener."""
        mock_listener_instance = mock_global_hotkeys.return_value
        self.listener.start()
        
        self.listener.stop()
        
        mock_listener_instance.stop.assert_called_once()
        self.assertIsNone(self.listener.listener)

    @patch('src.service.listener.keyboard.GlobalHotKeys')
    @patch('src.service.listener.threading.Thread')
    def test_callback_execution(self, mock_thread, mock_global_hotkeys):
        """
        Test that the callback is executed when the hotkey is triggered.
        """
        self.listener.start()
        
        # Get the hotkeys passed to GlobalHotKeys
        called_hotkeys = mock_global_hotkeys.call_args[0][0]
        
        # Simulate the trigger by calling the callback associated with the hotkey
        hotkey = '<ctrl>+<shift>+v'
        called_hotkeys[hotkey]()
        
        self.mock_callback.assert_called_once()

if __name__ == '__main__':
    unittest.main()
