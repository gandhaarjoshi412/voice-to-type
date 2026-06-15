import logging
import sys
import time
import subprocess

logger = logging.getLogger(__name__)

# ── Clipboard Helpers ──
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # ── CRITICAL: Set correct return types for pointer-returning functions. ──
    # ctypes defaults all return types to c_int (32-bit signed). On 64-bit
    # Windows, handles and pointers are 64-bit — without these declarations
    # the upper 32 bits are silently truncated, producing a garbage address
    # that causes an "access violation reading 0x..." crash.
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]

    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]

    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    kernel32.GlobalFree.restype = ctypes.c_void_p
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]

    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [wintypes.UINT]

    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]

    user32.OpenClipboard.restype = wintypes.BOOL
    user32.OpenClipboard.argtypes = [wintypes.HWND]

    user32.CloseClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []

    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []

    def get_clipboard_text() -> str:
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def set_clipboard_text(text: str) -> bool:
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            # length + 1 for null terminator, 2 bytes per char for Unicode
            size = (len(text) + 1) * 2
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not h_mem:
                return False
            ptr = kernel32.GlobalLock(h_mem)
            if not ptr:
                kernel32.GlobalFree(h_mem)
                return False
            try:
                # Use create_unicode_buffer to pin the source buffer in memory
                # during the memmove — ctypes.c_wchar_p(text) is a temporary
                # that can be GC'd mid-copy, causing an access violation.
                buf = ctypes.create_unicode_buffer(text)
                ctypes.memmove(ptr, buf, size)
            finally:
                kernel32.GlobalUnlock(h_mem)
            # SetClipboardData transfers ownership of h_mem to the OS on success.
            # Do NOT call GlobalFree afterwards on success.
            if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                kernel32.GlobalFree(h_mem)
                return False
            return True
        finally:
            user32.CloseClipboard()

elif sys.platform == "darwin":
    def get_clipboard_text() -> str:
        try:
            return subprocess.check_output(["pbpaste"], text=True)
        except Exception:
            return ""
            
    def set_clipboard_text(text: str) -> bool:
        try:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text)
            return p.returncode == 0
        except Exception:
            return False

else:  # Linux
    def get_clipboard_text() -> str:
        try:
            return subprocess.check_output(["xclip", "-selection", "clipboard", "-o"], text=True)
        except Exception:
            try:
                return subprocess.check_output(["xsel", "--clipboard", "--output"], text=True)
            except Exception:
                return ""
                
    def set_clipboard_text(text: str) -> bool:
        try:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text)
            if p.returncode == 0:
                return True
        except Exception:
            pass
        try:
            p = subprocess.Popen(["xsel", "--clipboard", "--input"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text)
            return p.returncode == 0
        except Exception:
            return False


class Typer:
    """
    Handles text injection into the active window using a fast clipboard paste method,
    falling back to simulated keystrokes if the clipboard copy/paste fails.
    """

    def type_text(self, text: str) -> bool:
        """
        Injects the text into the active window.
        Attempts to paste from clipboard, falling back to pyautogui typing if unsuccessful.
        
        Args:
            text (str): The text to inject.
            
        Returns:
            bool: True if text was injected successfully, False otherwise.
        """
        if not text:
            logger.debug("No text provided to inject.")
            return True

        # Try clipboard paste first for speed and accuracy
        try:
            # 1. Save original clipboard text
            orig_text = get_clipboard_text()
            
            # 2. Write new text to clipboard
            if set_clipboard_text(text):
                # Simulate paste key combination
                import pyautogui
                if sys.platform == "darwin":
                    pyautogui.hotkey("command", "v")
                else:
                    pyautogui.hotkey("ctrl", "v")
                
                # Yield execution thread briefly for OS to process the paste event
                # Increased to 0.3s to prevent race condition where target app pastes original clipboard contents
                time.sleep(0.3)
                
                # 4. Restore original clipboard text
                if orig_text is not None:
                    set_clipboard_text(orig_text)
                
                logger.info("Text pasted successfully via clipboard.")
                return True
            else:
                logger.warning("Clipboard write failed. Falling back to typing simulation.")
        except Exception as e:
            logger.error(f"Clipboard paste operation failed: {e}. Falling back to typing simulation.")

        # Fallback to simulated character-by-character typing
        try:
            import pyautogui
            pyautogui.write(text, interval=0.01)
            logger.info("Text typed successfully via simulated keystrokes.")
            return True
        except Exception as e:
            logger.error(f"Keystroke simulation fallback failed: {e}")
            return False
