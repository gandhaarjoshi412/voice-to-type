import sys
import os

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import threading
import tempfile
from dotenv import load_dotenv
from src.core.recorder import Recorder
from src.core.transcriber import Transcriber
from src.core.typer import Typer
from src.ui.overlay import GlassOverlay
from src.service.listener import HotkeyListener
from src.core.storage import StorageManager
from src.ui.finder import FinderWindow
import time

# Load environment variables
load_dotenv()

def get_active_window_info():
    """
    Returns a tuple of (window_title, app_name) representing the active window.
    Supports Windows via ctypes, with standard fallbacks for other platforms.
    """
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return "Unknown", "Unknown"
            
            # Get window title
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            title_buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, length + 1)
            window_title = title_buf.value
            
            # Get process/app name
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            # Open process
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            app_name = "Unknown"
            if h_process:
                try:
                    # Get executable path
                    size = wintypes.DWORD(1024)
                    buf = ctypes.create_unicode_buffer(1024)
                    if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size)):
                        import os
                        app_name = os.path.basename(buf.value)
                finally:
                    ctypes.windll.kernel32.CloseHandle(h_process)
            return window_title, app_name
        except Exception:
            return "Unknown Window", "Unknown App"
    elif sys.platform == "darwin":
        try:
            import subprocess
            cmd = 'tell application "System Events" to get name of first process whose frontmost is true'
            app_name = subprocess.check_output(['osascript', '-e', cmd], text=True).strip()
            cmd_title = 'tell application "System Events" to tell (first process whose frontmost is true) to get name of first window'
            title = subprocess.check_output(['osascript', '-e', cmd_title], text=True).strip()
            return title, app_name
        except Exception:
            return "Unknown Mac Window", "Unknown Mac App"
    else:
        try:
            import subprocess
            active_id = subprocess.check_output(['xdotool', 'getactivewindow'], text=True).strip()
            title = subprocess.check_output(['xdotool', 'getwindowname', active_id], text=True).strip()
            app_class = subprocess.check_output(['xprop', '-id', active_id, 'WM_CLASS'], text=True).strip()
            app_name = app_class.split(',')[-1].replace('"', '').strip()
            return title, app_name
        except Exception:
            return "Unknown Linux Window", "Unknown Linux App"

def build_whisper_prompt(window_title: str, app_name: str) -> str:
    """
    Constructs a context-aware transcription prompt for Whisper based on the active window.
    """
    app_lower = app_name.lower()
    
    # 1. Developer IDE / Editor Context
    if any(ide in app_lower for ide in ["code", "cursor", "windsurf", "notepad", "sublime", "visualstudio", "pycharm", "intellij", "eclipse", "clion"]):
        return (
            "Writing source code and software documentation. Use exact programming syntax, "
            "standard formatting, camelCase, snake_case, variable names, programming operators, "
            "and technical jargon. Preserve syntax structure, braces, and keyword capitalization."
        )
    
    # 2. Communication / Messaging Context
    elif any(chat in app_lower for chat in ["slack", "discord", "teams", "whatsapp", "telegram", "messenger", "skype"]):
        return (
            "Chatting with colleagues in a messaging application. Use a conversational, "
            "natural tone, standard chat punctuation, emojis if implied, short messages, "
            "and common professional and technical abbreviations."
        )
    
    # 3. Email / Professional Writing Context
    elif any(mail in app_lower for mail in ["outlook", "thunderbird", "gmail", "mail"]):
        return (
            "Drafting a professional email or formal letter. Ensure formal business tone, "
            "correct paragraph structure, proper capitalization of greetings, names, and formal closures."
        )
        
    # 4. Command Line / Terminal Context
    elif any(term in app_lower for term in ["cmd", "powershell", "bash", "zsh", "terminal", "wt"]):
        return (
            "Executing terminal CLI commands. Use raw commands, flags, arguments, exact directory paths, "
            "dashes, slashes, and syntax matching shell operations."
        )
        
    # 5. Generic Fallback
    return (
        f"Dictating text into the window '{window_title}' using the application {app_name}. "
        "Transcribe natural speech into clean, punctuated text matching the surrounding context."
    )


class VoiceToTypeService:
    def __init__(self):
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.typer = Typer()
        self.overlay = GlassOverlay()
        self.listener = HotkeyListener()
        self.storage = StorageManager()
        self.finder = FinderWindow(self.storage)
        self.is_recording = False
        self.recording_context = (None, None)

    def _toggle_recording(self):
        if not self.is_recording:
            # Start recording
            self.is_recording = True
            
            # Capture active window context BEFORE showing the overlay (prevents focus loss issues)
            window_title, app_name = get_active_window_info()
            self.recording_context = (window_title, app_name)
            print(f"Recording context captured: App='{app_name}', Title='{window_title}'")
            
            self.overlay.trigger_start.emit()
            try:
                # Wire real-time mic amplitude → overlay waveform
                self.recorder.start_recording(
                    on_amplitude=self.overlay.amplitude_update.emit
                )
            except Exception as e:
                print(f"Error starting recording: {e}")
                self.is_recording = False
                self.overlay.trigger_stop.emit()
        else:
            # Stop recording and process
            self.is_recording = False
            self.overlay.trigger_stop.emit()
            threading.Thread(target=self._process_recording).start()

    def _process_recording(self):
        """
        Stops the recording, transcribes (with context), saves to DB, and types the text.
        """
        print("Starting _process_recording thread...")
        audio_filename = f"audio_{int(time.time())}.wav"
        audio_path = os.path.join(self.storage.audio_dir, audio_filename)
        print(f"Saving audio to {audio_path}")
        
        try:
            # Stop the recording and save to history audio directory
            self.recorder.stop_recording(audio_path)
            print("Recording stopped and saved.")
            
            # Formulate the context-aware prompt for Whisper
            prompt = None
            window_title, app_name = None, None
            if self.recording_context and self.recording_context[0] is not None:
                window_title, app_name = self.recording_context
                prompt = build_whisper_prompt(window_title, app_name)
            
            print(f"Sending audio to Whisper API (prompt={prompt})...")
            # Transcribe the recorded audio with context
            transcribed_text = self.transcriber.transcribe(audio_path, prompt=prompt)
            print(f"Transcription result: {transcribed_text}")
            
            # Type the transcribed text and save to DB
            if transcribed_text:
                print("Typing text...")
                self.typer.type_text(transcribed_text)
                print("Saving record to DB...")
                self.storage.add_record(transcribed_text, audio_path, window_title or "Unknown", app_name or "Unknown")
                print("Process complete.")
                
        except Exception as e:
            import traceback
            print(f"Error during pipeline execution: {e}")
            traceback.print_exc()
            # If transcription failed, clean up the audio file immediately
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception as cleanup_err:
                    print(f"Error removing failed audio file: {cleanup_err}")
        finally:
            print("Running storage cleanup...")
            # Perform scheduled cleanup of old records and files
            self.storage.cleanup()
            print("Storage cleanup finished.")

    def _toggle_finder(self):
        self.finder.trigger_toggle.emit()

    def run(self):
        """
        Starts the hotkey listener with callbacks for recording and finder.
        """
        self.listener.start(callback=self._toggle_recording, search_callback=self._toggle_finder)

    def stop(self):
        """
        Shuts down the listener and service.
        """
        self.listener.stop()
        # Ensure overlay is hidden on stop thread-safely
        self.overlay.trigger_stop.emit()

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    service = VoiceToTypeService()
    try:
        print("VoiceToType Service started. Press the hotkey to record.")
        service.run()
        # Start Qt event loop to handle UI draw/events and signal handling
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\nStopping service...")
        service.stop()
