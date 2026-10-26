import logging
import os
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
        if os.environ.get("WAYLAND_DISPLAY"):
            try:
                return subprocess.check_output(["wl-paste"], text=True)
            except Exception:
                pass
        try:
            return subprocess.check_output(["xclip", "-selection", "clipboard", "-o"], text=True)
        except Exception:
            try:
                return subprocess.check_output(["xsel", "--clipboard", "--output"], text=True)
            except Exception:
                return ""
                
    def set_clipboard_text(text: str) -> bool:
        if os.environ.get("WAYLAND_DISPLAY"):
            try:
                p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, text=True)
                p.communicate(input=text)
                if p.returncode == 0:
                    return True
            except Exception:
                pass
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


def _find_xdisplay() -> str:
    """Find an active XWayland display to use with xdotool."""
    import glob
    sockets = sorted(glob.glob("/tmp/.X11-unix/X*"))
    for sock in sockets:
        display = ":" + sock.replace("/tmp/.X11-unix/X", "")
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                env={**os.environ, "DISPLAY": display},
                capture_output=True, timeout=1
            )
            if result.returncode == 0:
                return display
        except Exception:
            continue
    return ":0"  # default fallback


class Typer:
    """
    Handles text injection into the active window using a fast clipboard paste method,
    falling back to simulated keystrokes if the clipboard copy/paste fails.
    """

    def type_text(self, text: str) -> bool:
        """
        Injects the text into the active window.
        On GNOME Wayland: wl-copy to clipboard, then ydotool key 29:1 47:1 47:0 29:0
        On other platforms: clipboard + Ctrl+V via pyautogui.
        """
        if not text:
            return True

        is_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))

        # ── Wayland (GNOME) path ──────────────────────────────────────────────
        if is_wayland and sys.platform != "darwin":
            print("[Typer] Using Wayland ydotool strategy.")
            if set_clipboard_text(text):
                time.sleep(0.25)
                try:
                    ydotool_env = os.environ.copy()
                    ydotool_env["YDOTOOL_SOCKET"] = "/tmp/.ydotool_socket"
                    # ydotool uses kernel-level scancodes. 29 = Left Ctrl, 47 = V
                    subprocess.run(
                        ["ydotool", "key", "-d", "20", "29:1", "47:1", "47:0", "29:0"],
                        env=ydotool_env, check=True, timeout=3
                    )
                    print("[Typer] Text pasted via wl-copy + ydotool (Ctrl+V).")
                    return True
                except Exception as e:
                    print(f"[Typer] ydotool paste failed: {e}. Trying ydotool type...")
                    try:
                        subprocess.run(
                            ["ydotool", "type", text],
                            env=ydotool_env, check=True, timeout=10
                        )
                        print("[Typer] Text typed via ydotool type.")
                        return True
                    except Exception as e2:
                        print(f"[Typer] ydotool type also failed: {e2}")
                        print("\n=== WAYLAND DAEMON REQUIRED ===")
                        print("On GNOME Wayland, you MUST run the ydotoold daemon for auto-typing.")
                        print("Run this command in a new terminal and leave it running:")
                        print("    sudo ydotoold -p /tmp/.ydotool_socket -P 0666")
                        print("===============================\n")
                        print(f"[Typer] Text copied to clipboard — press Ctrl+V to paste: {text[:40]}...")
                        return False
            else:
                print("[Typer] ERROR: wl-copy failed — cannot put text on clipboard.")
                return False

        # ── macOS / X11 Linux / Windows path ──────────────────────────────────
        try:
            orig_text = get_clipboard_text()

            if set_clipboard_text(text):
                import pyautogui
                time.sleep(0.1)
                if sys.platform == "darwin":
                    pyautogui.hotkey("command", "v")
                else:
                    pyautogui.hotkey("ctrl", "v")
                time.sleep(0.3)
                if orig_text is not None:
                    set_clipboard_text(orig_text)
                print("[Typer] Text pasted successfully via clipboard & pyautogui.")
                return True
            else:
                print("[Typer] Clipboard write failed. Falling back to typing simulation.")
        except Exception as e:
            print(f"[Typer] Clipboard paste failed: {e}. Falling back to typing simulation.")

        # Fallback: character-by-character typing
        try:
            import pyautogui
            pyautogui.write(text, interval=0.01)
            print("[Typer] Text typed successfully via simulated keystrokes.")
            return True
        except Exception as e:
            print(f"[Typer] Keystroke simulation fallback failed: {e}")
            return False
