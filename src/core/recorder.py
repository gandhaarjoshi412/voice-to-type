import sounddevice as sd
from scipy.io import wavfile
import numpy as np
import logging
import queue

logger = logging.getLogger(__name__)

class Recorder:
    """
    A class to handle mono audio recording continuously until stopped.
    Emits real-time RMS amplitude via an optional on_amplitude callback.
    """

    def __init__(self, samplerate=44100):
        self.samplerate = samplerate
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self._stream = None
        self.recorded_frames = []
        self._on_amplitude = None   # callable(float) — called per audio block

    def _audio_callback(self, indata, frames, time, status):
        """Called per audio block by sounddevice (audio thread)."""
        if status:
            logger.warning(f"Audio callback status: {status}")
        chunk = indata.copy()
        self.audio_queue.put(chunk)
        # Compute RMS and fire amplitude callback
        if self._on_amplitude is not None:
            try:
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                self._on_amplitude(rms)
            except Exception:
                pass

    def start_recording(self, on_amplitude=None):
        """
        Starts the audio recording stream.
        :param on_amplitude: optional callable(float) fired per audio chunk with RMS value.
        """
        if self.is_recording:
            logger.warning("Already recording.")
            return

        self._on_amplitude = on_amplitude
        self.is_recording = True
        self.recorded_frames = []
        # Clear queue
        while not self.audio_queue.empty():
            self.audio_queue.get()

        try:
            # Check for available input devices
            devices = sd.query_devices()
            if not devices:
                raise RuntimeError("No audio devices found.")
            
            # Try to find a default input device
            default_device = sd.default.device[0]
            if default_device is None:
                # If no default is set, check if any device has input channels
                input_devices = [d for d in devices if d['max_input_channels'] > 0]
                if not input_devices:
                    raise RuntimeError("No audio input device found.")
                device_id = input_devices[0]['index']
            else:
                device_id = default_device

            logger.info(f"Started recording using device {device_id}...")
            
            self._stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=1,
                device=device_id,
                dtype='float32',
                callback=self._audio_callback
            )
            self._stream.start()

        except Exception as e:
            self.is_recording = False
            logger.error(f"An error occurred starting recording: {e}")
            raise e

    def stop_recording(self, output_path: str):
        """
        Stops the recording and saves the accumulated audio to a WAV file.
        """
        if not self.is_recording:
            return

        self.is_recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            
        logger.info("Recording stopped. Saving file...")
        
        # Collect all frames from the queue
        while not self.audio_queue.empty():
            self.recorded_frames.append(self.audio_queue.get())
            
        if not self.recorded_frames:
            logger.warning("No audio data recorded.")
            return

        # Concatenate all chunks and save
        try:
            recording = np.concatenate(self.recorded_frames, axis=0)
            wavfile.write(output_path, self.samplerate, recording)
            logger.info(f"Recording saved to {output_path}")
        except Exception as e:
            logger.error(f"Error saving recording: {e}")
            raise e
