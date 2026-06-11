import logging
from pynput import keyboard
import threading

logger = logging.getLogger(__name__)

class HotkeyListener:
    """
    A class to listen for global hotkeys and execute corresponding callback functions.
    """
    def __init__(self, hotkeys: dict = None):
        """
        Initialize the HotkeyListener.

        :param hotkeys: A dictionary where keys are hotkey strings (e.g., '<ctrl>+<shift>+v')
                        and values are callable functions to execute when the hotkey is pressed.
        """
        self.hotkeys = hotkeys or {}
        self.listener = None
        self._thread = None

    def start(self, callback=None):
        """
        Starts the hotkey listener in a background thread.
        """
        if self.listener:
            logger.warning("HotkeyListener is already running.")
            return

        try:
            if callback:
                import os
                # Special keys recognised by pynput that require angle-bracket notation
                SPECIAL_KEYS = {
                    "ctrl", "alt", "shift", "cmd", "super", "win",
                    "enter", "space", "tab", "backspace", "delete", "escape",
                    "up", "down", "left", "right", "home", "end",
                    "page_up", "page_down", "insert", "caps_lock", "num_lock",
                    "scroll_lock", "print_screen", "pause", "menu",
                    "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12",
                }
                raw_hotkey = os.environ.get("HOTKEY", "ctrl+alt+v")
                if not ("<" in raw_hotkey and ">" in raw_hotkey):
                    parts = raw_hotkey.split("+")
                    # Only wrap keys that are special modifiers; leave bare characters as-is
                    formatted_parts = []
                    for part in parts:
                        key = part.strip().lower()
                        if key in SPECIAL_KEYS:
                            formatted_parts.append(f"<{key}>")
                        else:
                            formatted_parts.append(key)
                    formatted_hotkey = "+".join(formatted_parts)
                else:
                    formatted_hotkey = raw_hotkey
                self.hotkeys[formatted_hotkey] = callback
                logger.info(f"Hotkey registered: {formatted_hotkey}")

            # GlobalHotKeys is a convenience wrapper for keyboard.Listener
            self.listener = keyboard.GlobalHotKeys(self.hotkeys)
            
            # Start the listener in a separate thread so it doesn't block the main application
            self._thread = threading.Thread(target=self.listener.start, daemon=True)
            self._thread.start()
            logger.info("HotkeyListener started successfully.")
        except Exception as e:
            logger.error(f"Failed to start HotkeyListener: {e}")
            self.listener = None
            self._thread = None
            raise e

    def stop(self):
        """
        Stops the hotkey listener.
        """
        if self.listener:
            self.listener.stop()
            self.listener = None
            logger.info("HotkeyListener stopped.")
        else:
            logger.warning("HotkeyListener is not running.")
