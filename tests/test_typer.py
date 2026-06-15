import unittest
from unittest.mock import patch, MagicMock
import sys
from src.core.typer import Typer

class TestTyper(unittest.TestCase):
    def setUp(self):
        self.typer = Typer()

    @patch('src.core.typer.get_clipboard_text')
    @patch('src.core.typer.set_clipboard_text')
    def test_type_text_clipboard_success(self, mock_set, mock_get):
        """Test that type_text attempts clipboard paste and succeeds."""
        mock_get.return_value = "Original Clip"
        mock_set.return_value = True
        
        mock_pyautogui = MagicMock()
        with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
            text = "Hello World"
            result = self.typer.type_text(text)
            
            self.assertTrue(result)
            mock_get.assert_called_once()
            # Called first with text to paste, then with original clip
            mock_set.assert_any_call(text)
            mock_set.assert_any_call("Original Clip")
            
            if sys.platform == "darwin":
                mock_pyautogui.hotkey.assert_called_once_with("command", "v")
            else:
                mock_pyautogui.hotkey.assert_called_once_with("ctrl", "v")
            
            # write should not be called in success flow
            mock_pyautogui.write.assert_not_called()

    @patch('src.core.typer.get_clipboard_text')
    @patch('src.core.typer.set_clipboard_text')
    def test_type_text_clipboard_failure_fallback(self, mock_set, mock_get):
        """Test that type_text falls back to keystroke typing if clipboard write fails."""
        mock_get.return_value = "Original Clip"
        mock_set.return_value = False  # clipboard write fails
        
        mock_pyautogui = MagicMock()
        with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
            text = "Fallback Text"
            result = self.typer.type_text(text)
            
            self.assertTrue(result)
            mock_pyautogui.write.assert_called_once_with(text, interval=0.01)
            mock_pyautogui.hotkey.assert_not_called()

    def test_type_text_empty(self):
        """Test that type_text returns True and does nothing when text is empty."""
        mock_pyautogui = MagicMock()
        with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
            result = self.typer.type_text("")
            self.assertTrue(result)
            mock_pyautogui.write.assert_not_called()
            mock_pyautogui.hotkey.assert_not_called()

if __name__ == '__main__':
    unittest.main()
