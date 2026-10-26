import sys
import os

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import queue
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
from src.ui.dashboard import AnalyticsDashboard
from src.ui.tray import VoiceTypeTray
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
            active_id = subprocess.check_output(['xdotool', 'getactivewindow'], text=True, stderr=subprocess.DEVNULL, timeout=0.5).strip()
            title = subprocess.check_output(['xdotool', 'getwindowname', active_id], text=True, stderr=subprocess.DEVNULL, timeout=0.5).strip()
            app_class = subprocess.check_output(['xprop', '-id', active_id, 'WM_CLASS'], text=True, stderr=subprocess.DEVNULL, timeout=0.5).strip()
            if "not found" in app_class.lower():
                app_name = "Unknown"
            else:
                app_name = app_class.split(',')[-1].replace('"', '').strip()
            return title or "Unknown", app_name or "Unknown"
        except Exception:
            return "Unknown", "Unknown"

def build_whisper_prompt(window_title: str, app_name: str) -> str:
    """
    Constructs a context-aware transcription prompt for Whisper based on the active window.
    Returns None when window/app context is unknown (e.g. under Wayland) to prevent prompt hallucinations.
    """
    app_lower = (app_name or "").lower()
    title_clean = (window_title or "").strip()
    
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
        
    # 5. Generic Fallback — only if we actually have a real window title and app name
    if not title_clean or title_clean.lower().startswith("unknown") or app_lower.startswith("unknown") or "not found" in app_lower:
        return None

    return (
        f"Dictating text into the window '{title_clean}' using the application {app_name}. "
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
        self.dashboard = AnalyticsDashboard(self.storage)
        self.tray = VoiceTypeTray(self.storage)
        self.is_recording = False
        self._active_window_title = "Unknown"
        self._active_app_name = "Unknown"
        default_rt = "0" if os.environ.get("WAYLAND_DISPLAY") else "1"
        self.realtime_streaming = os.environ.get("REALTIME_STREAMING", default_rt) != "0"
        self._live_chunk_queue = queue.Queue()
        self._live_transcribed_parts = []
        self._live_chunks_count = 0
        self._live_worker_thread = threading.Thread(target=self._live_chunk_worker, daemon=True)
        self._live_worker_thread.start()

        # Wire System Tray interactions
        self.tray.trigger_record.connect(self._toggle_recording)
        self.tray.trigger_dashboard.connect(self._toggle_dashboard)
        self.tray.trigger_finder.connect(self._toggle_finder)
        self.tray.trigger_quit.connect(self._quit)

        # Wire Dashboard interactions
        self.dashboard.trigger_record_toggle.connect(self._toggle_recording)
        self.dashboard.trigger_search_toggle.connect(self._toggle_finder)

        # Show tray icon
        self.tray.show()

    def _set_ui_recording_state(self, recording: bool):
        try:
            if hasattr(self.tray, "trigger_recording_state"):
                self.tray.trigger_recording_state.emit(recording)
            else:
                self.tray.set_recording_state(recording)
        except Exception:
            pass
        try:
            if hasattr(self.dashboard, "trigger_recording_state"):
                self.dashboard.trigger_recording_state.emit(recording)
            else:
                self.dashboard.set_recording_state(recording)
        except Exception:
            pass

    def _refresh_ui_analytics(self):
        try:
            if hasattr(self.dashboard, "trigger_refresh"):
                self.dashboard.trigger_refresh.emit()
            else:
                self.dashboard.refresh_data()
            if hasattr(self.tray, "trigger_update_storage"):
                self.tray.trigger_update_storage.emit()
            else:
                self.tray.update_storage_indicator()
        except Exception as ui_err:
            print(f"Note updating UI: {ui_err}")

    def _enqueue_live_chunk(self, wav_bytes: bytes):
        """Called by Recorder when a natural speech pause occurs during recording."""
        if not wav_bytes or not self.realtime_streaming:
            return
        self._live_chunks_count += 1
        self._live_chunk_queue.put((self._live_chunks_count, wav_bytes))

    def _live_chunk_worker(self):
        """Background worker that transcribes & types live speech chunks in order while speaking."""
        while True:
            item = self._live_chunk_queue.get()
            if item is None:
                self._live_chunk_queue.task_done()
                break
            chunk_idx, wav_bytes = item
            try:
                prompt = build_whisper_prompt(self._active_window_title, self._active_app_name)
                if hasattr(self.transcriber, "transcribe_bytes"):
                    text = self.transcriber.transcribe_bytes(
                        wav_bytes,
                        filename=f"live_chunk_{chunk_idx}.wav",
                        prompt=prompt,
                    )
                else:
                    text = ""
                clean = (text or "").strip()
                # Filter out common Whisper silence hallucinations on short chunks
                if clean and clean not in (".", "..", "...", "Thank you.", "Thanks for watching."):
                    prefix = " " if self._live_transcribed_parts else ""
                    self.typer.type_text(prefix + clean)
                    self._live_transcribed_parts.append(clean)
            except Exception as e:
                print(f"[LiveStream] Chunk {chunk_idx} transcription error: {e}")
            finally:
                self._live_chunk_queue.task_done()

    def _toggle_recording(self):
        if not self.is_recording:
            # Reset live streaming session state
            while not self._live_chunk_queue.empty():
                try:
                    self._live_chunk_queue.get_nowait()
                    self._live_chunk_queue.task_done()
                except Exception:
                    break
            self._live_transcribed_parts = []
            self._live_chunks_count = 0

            # Pre-warm HTTPS/TLS connection to Groq immediately while user starts speaking
            if hasattr(self.transcriber, "prewarm"):
                try:
                    self.transcriber.prewarm()
                except Exception:
                    pass

            # Capture active window info asynchronously so mic starts with zero latency
            def _capture_ctx():
                try:
                    self._active_window_title, self._active_app_name = get_active_window_info()
                except Exception:
                    self._active_window_title, self._active_app_name = "Unknown", "Unknown"

            threading.Thread(target=_capture_ctx, daemon=True).start()

            # Start recording immediately
            self.is_recording = True
            self.overlay.trigger_start.emit()
            self._set_ui_recording_state(True)
            try:
                # Wire real-time mic amplitude → overlay waveform + live speech pause chunking
                if self.realtime_streaming:
                    try:
                        self.recorder.start_recording(
                            on_amplitude=self.overlay.amplitude_update.emit,
                            on_speech_chunk=self._enqueue_live_chunk,
                        )
                    except TypeError:
                        self.recorder.start_recording(
                            on_amplitude=self.overlay.amplitude_update.emit
                        )
                else:
                    self.recorder.start_recording(
                        on_amplitude=self.overlay.amplitude_update.emit
                    )
            except Exception as e:
                print(f"Error starting recording: {e}")
                self.is_recording = False
                self.overlay.trigger_stop.emit()
                self._set_ui_recording_state(False)
        else:
            # Stop recording and IMMEDIATELY hide the overlay so Wayland/Mutter
            # restores keyboard focus to the active text box while transcription runs.
            self.is_recording = False
            self.overlay.trigger_stop.emit()
            self._set_ui_recording_state(False)
            threading.Thread(target=self._process_recording, daemon=True).start()

    def _process_recording(self):
        """
        Stops the recording, transcribes, and types the text with minimal latency.
        """
        t_start = time.time()
        print("Starting _process_recording thread...")
        audio_filename = f"audio_{int(t_start)}.wav"
        audio_path = os.path.join(self.storage.audio_dir, audio_filename)
        print(f"Saving audio to {audio_path}")
        
        try:
            # Stop the recording and save full audio to history audio directory
            duration = self.recorder.stop_recording(audio_path) or 0.0
            print(f"Recording stopped and saved in {time.time() - t_start:.2f}s. Duration: {duration}s")
            
            # Context-aware Whisper prompt
            prompt = build_whisper_prompt(self._active_window_title, self._active_app_name)

            if self._live_chunks_count > 0 and hasattr(self.recorder, "pop_remaining_live_wav"):
                # Wait for any in-flight live chunks that were emitted during recording
                self._live_chunk_queue.join()
                tail_wav = self.recorder.pop_remaining_live_wav()
                if tail_wav and hasattr(self.transcriber, "transcribe_bytes"):
                    tail_text = (self.transcriber.transcribe_bytes(
                        tail_wav, filename="tail.wav", prompt=prompt
                    ) or "").strip()
                    if tail_text and tail_text not in (".", "..", "...", "Thank you."):
                        prefix = " " if self._live_transcribed_parts else ""
                        self.typer.type_text(prefix + tail_text)
                        self._live_transcribed_parts.append(tail_text)
                transcribed_text = " ".join(self._live_transcribed_parts).strip()
            else:
                print(f"Sending audio to Whisper API (prompt={'set' if prompt else 'None'})...")
                t_api = time.time()
                transcribed_text = self.transcriber.transcribe(audio_path, prompt=prompt)
                print(f"Transcription result ({time.time() - t_api:.2f}s): {transcribed_text}")
                
                if transcribed_text and transcribed_text.strip() not in (".", "..", "..."):
                    print("Typing text...")
                    self.typer.type_text(transcribed_text)

            if transcribed_text and transcribed_text.strip() not in (".", "..", "..."):
                print("Saving record to DB with analytics metadata...")
                self.storage.add_record(
                    transcribed_text,
                    audio_path,
                    self._active_window_title,
                    self._active_app_name,
                    duration=duration
                )
                print(f"Process complete in {time.time() - t_start:.2f}s total.")
                self._refresh_ui_analytics()
                
        except Exception as e:
            import traceback
            print(f"Error during pipeline execution: {e}")
            traceback.print_exc()
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception as cleanup_err:
                    print(f"Error removing failed audio file: {cleanup_err}")
        finally:
            self.overlay.trigger_stop.emit()
            try:
                self.storage.cleanup()
            except Exception:
                pass

    def _toggle_finder(self):
        self.finder.trigger_toggle.emit()

    def _toggle_dashboard(self):
        self.dashboard.trigger_toggle.emit()

    def run(self):
        """
        Starts the hotkey listener with callbacks for recording, finder, and dashboard.
        """
        self.listener.start(
            callback=self._toggle_recording,
            search_callback=self._toggle_finder,
            dashboard_callback=self._toggle_dashboard,
            quit_callback=self._quit
        )

    def _quit(self):
        """
        Gracefully stops the service and exits the QApplication event loop.
        """
        try:
            self.stop()
        except Exception as e:
            print(f"Error during stop: {e}")
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def stop(self):
        """
        Shuts down the listener, tray, and service.
        """
        self.listener.stop()
        try:
            self.tray.hide()
        except Exception:
            pass
        # Ensure overlay is hidden on stop thread-safely
        self.overlay.trigger_stop.emit()

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    # Prevent application from exiting when dashboard or finder windows are closed/minimized
    app.setQuitOnLastWindowClosed(False)
    
    service = VoiceToTypeService()
    try:
        print("VoiceToType Service started. Press the hotkey to record.")
        service.run()
        # Start Qt event loop to handle UI draw/events and signal handling
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\nStopping service...")
        service.stop()
