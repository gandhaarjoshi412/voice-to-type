import io
import sounddevice as sd
from scipy.io import wavfile
import numpy as np
import logging
import queue
import threading

logger = logging.getLogger(__name__)

class Recorder:
    """
    A class to handle mono audio recording continuously until stopped.
    Emits real-time RMS amplitude via an optional on_amplitude callback,
    and supports real-time speech chunk slicing on natural pauses.
    """

    SPEECH_RMS_THRESHOLD = 0.014
    MIN_CHUNK_SPEECH_SEC = 1.6
    PAUSE_SILENCE_SEC    = 0.45
    MAX_CHUNK_SEC        = 6.0

    def __init__(self, samplerate=44100):
        self.samplerate = samplerate
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self._stream = None
        self.recorded_frames = []
        self._on_amplitude = None      # callable(float) — called per audio block
        self._on_speech_chunk = None   # callable(bytes) — called when a live phrase chunk is ready
        self._live_lock = threading.Lock()
        self._live_frames = []
        self._speech_samples = 0
        self._silence_samples = 0
        self._has_speech_in_chunk = False

    @staticmethod
    def _frames_to_wav16k_bytes(frames, src_sr: int) -> bytes:
        """Convert a list of float32 numpy blocks into an in-memory 16kHz PCM16 WAV."""
        if not frames:
            return b""
        recording = np.concatenate(frames, axis=0)
        if recording.ndim > 1:
            recording = recording[:, 0]
        target_sr = 16000
        if src_sr != target_sr and len(recording) > 0:
            num_samples = max(1, int(len(recording) * target_sr / src_sr))
            indices = np.linspace(0, len(recording) - 1, num_samples).astype(np.int32)
            recording = recording[indices]
        pcm16 = np.clip(recording * 32767.0, -32768, 32767).astype(np.int16)
        buf = io.BytesIO()
        wavfile.write(buf, target_sr, pcm16)
        return buf.getvalue()

    def _audio_callback(self, indata, frames, time, status):
        """Called per audio block by sounddevice (audio thread)."""
        if status:
            logger.warning(f"Audio callback status: {status}")
        chunk = indata.copy()
        self.audio_queue.put(chunk)
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        # Fire amplitude callback
        if self._on_amplitude is not None:
            try:
                self._on_amplitude(rms)
            except Exception:
                pass

        # Real-time phrase segmentation on natural pauses
        if self._on_speech_chunk is not None:
            n_samples = len(chunk)
            chunk_to_emit = None
            with self._live_lock:
                self._live_frames.append(chunk)
                if rms >= self.SPEECH_RMS_THRESHOLD:
                    self._has_speech_in_chunk = True
                    self._speech_samples += n_samples
                    self._silence_samples = 0
                else:
                    if self._has_speech_in_chunk:
                        self._silence_samples += n_samples

                total_chunk_samples = sum(len(f) for f in self._live_frames)
                enough_speech = self._speech_samples >= int(self.MIN_CHUNK_SPEECH_SEC * self.samplerate)
                pause_reached = self._silence_samples >= int(self.PAUSE_SILENCE_SEC * self.samplerate)
                max_reached = (
                    self._has_speech_in_chunk
                    and total_chunk_samples >= int(self.MAX_CHUNK_SEC * self.samplerate)
                    and rms < self.SPEECH_RMS_THRESHOLD * 1.5
                )

                if (enough_speech and pause_reached) or max_reached:
                    chunk_to_emit = list(self._live_frames)
                    self._live_frames = []
                    self._speech_samples = 0
                    self._silence_samples = 0
                    self._has_speech_in_chunk = False

            if chunk_to_emit:
                try:
                    wav_bytes = self._frames_to_wav16k_bytes(chunk_to_emit, self.samplerate)
                    if wav_bytes:
                        self._on_speech_chunk(wav_bytes)
                except Exception as e:
                    logger.debug(f"Live chunk emit error: {e}")

    def start_recording(self, on_amplitude=None, on_speech_chunk=None):
        """
        Starts the audio recording stream.
        :param on_amplitude: optional callable(float) fired per audio chunk with RMS value.
        :param on_speech_chunk: optional callable(bytes) fired with 16kHz WAV bytes on speech pauses.
        """
        if self.is_recording:
            logger.warning("Already recording.")
            return

        self._on_amplitude = on_amplitude
        self._on_speech_chunk = on_speech_chunk
        self.is_recording = True
        self.recorded_frames = []
        with self._live_lock:
            self._live_frames = []
            self._speech_samples = 0
            self._silence_samples = 0
            self._has_speech_in_chunk = False
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

    def pop_remaining_live_wav(self) -> bytes:
        """
        Returns any unflushed live frames accumulated since the last pause chunk as 16kHz WAV bytes,
        only if speech was detected in them.
        """
        with self._live_lock:
            frames = list(self._live_frames)
            has_speech = self._has_speech_in_chunk
            self._live_frames = []
            self._speech_samples = 0
            self._silence_samples = 0
            self._has_speech_in_chunk = False
        if not frames or not has_speech:
            return b""
        return self._frames_to_wav16k_bytes(frames, self.samplerate)

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
            return 0.0

        # Concatenate all chunks and save
        try:
            recording = np.concatenate(self.recorded_frames, axis=0)
            wavfile.write(output_path, self.samplerate, recording)
            duration = round(float(len(recording)) / float(self.samplerate), 2)
            logger.info(f"Recording saved to {output_path} (duration: {duration:.2f}s)")
            return duration
        except Exception as e:
            logger.error(f"Error saving recording: {e}")
            raise e
