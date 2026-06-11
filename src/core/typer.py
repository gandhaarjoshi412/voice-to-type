import logging

logger = logging.getLogger(__name__)

class Typer:
    """
    Handles text injection into the active window using PyAutoGUI.
    """

    def type_text(self, text: str) -> bool:
        """
        Types the provided text using pyautogui.write.
        
        Args:
            text (str): The text to be typed.
            
        Returns:
            bool: True if the text was successfully typed, False otherwise.
        """
        if not text:
            logger.debug("No text provided to type.")
            return True

        try:
            import pyautogui
            # Using a small interval to simulate natural typing and increase reliability
            pyautogui.write(text, interval=0.01)
            return True
        except Exception as e:
            logger.error(f"Failed to type text using PyAutoGUI: {e}")
            return False
