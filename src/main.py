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

# Load environment variables
load_dotenv()

class VoiceToTypeService:
    def __init__(self):
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.typer = Typer()
        self.overlay = GlassOverlay()
        self.listener = HotkeyListener()
        self.is_recording = False

    def _toggle_recording(self):
        if not self.is_recording:
            # Start recording
            self.is_recording = True
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
        Stops the recording, transcribes, and types the text.
        """
        temp_audio_path = os.path.join(tempfile.gettempdir(), "vtt_temp_audio.wav")
        
        try:
            # Stop the recording and save to temp file
            self.recorder.stop_recording(temp_audio_path)
            
            # Transcribe the recorded audio
            transcribed_text = self.transcriber.transcribe(temp_audio_path)
            
            # Type the transcribed text
            if transcribed_text:
                self.typer.type_text(transcribed_text)
                
        except Exception as e:
            print(f"Error during pipeline execution: {e}")
        finally:
            # Cleanup temp file
            if os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except Exception as e:
                    print(f"Error removing temp file: {e}")

    def run(self):
        """
        Starts the hotkey listener with a callback to toggle recording.
        """
        self.listener.start(callback=self._toggle_recording)

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
