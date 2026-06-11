import unittest
from unittest.mock import patch, MagicMock
import sys
from src.core.typer import Typer

class TestTyper(unittest.TestCase):
    def setUp(self):
        self.typer = Typer()

    def test_type_text_success(self):
        """Test that type_text calls pyautogui.write with correct arguments on success."""
        text = "Hello World"
        
        # Mock pyautogui in sys.modules to handle the local import
        mock_pyautogui = MagicMock()
        with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
            result = self.typer.type_text(text)
            
            self.assertTrue(result)
            mock_pyautogui.write.assert_called_once_with(text, interval=0.01)

    def test_type_text_empty(self):
        """Test that type_text returns True and does nothing when text is empty."""
        # Mock pyautogui just in case, though it shouldn't be called
        mock_pyautogui = MagicMock()
        with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
            result = self.typer.type_text("")
            
            self.assertTrue(result)
            mock_pyautogui.write.assert_not_called()

    def test_type_text_failure(self):
        """Test that type_text returns False when pyautogui.write raises an exception."""
        mock_pyautogui = MagicMock()
        mock_pyautogui.write.side_effect = Exception("PyAutoGUI Error")
        
        with patch.dict('sys.modules', {'pyautogui': mock_pyautogui}):
            text = "Error Test"
            result = self.typer.type_text(text)
            
            self.assertFalse(result)
            mock_pyautogui.write.assert_called_once_with(text, interval=0.01)

if __name__ == '__main__':
    unittest.main()
