import io
import os
import threading
import httpx
import numpy as np
from scipy.io import wavfile
from groq import Groq, APIError

class Transcriber:
    def __init__(self, api_key: str = None):
        """
        Initializes the Groq Transcriber with persistent IPv4 keep-alive pooling.
        
        Args:
            api_key (str, optional): Groq API key. If None, it will look for GROQ_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key must be provided or set as GROQ_API_KEY environment variable.")
        
        # Force IPv4 and persistent connection pooling to avoid 3-5s IPv6/TLS stalls
        try:
            self._http_client = httpx.Client(
                transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=1),
                timeout=httpx.Timeout(15.0, connect=8.0),
            )
            self.client = Groq(api_key=self.api_key, http_client=self._http_client, max_retries=1)
        except Exception:
            self._http_client = None
            self.client = Groq(api_key=self.api_key)

        self.model = "whisper-large-v3-turbo"
        self.fallback_model = "whisper-large-v3"

    def prewarm(self):
        """
        Pre-warms the HTTPS/TLS connection pool to api.groq.com in a background thread
        while the user is speaking so zero handshake latency occurs when recording stops.
        """
        if self._http_client is None:
            return

        def _warm():
            try:
                self._http_client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=5.0,
                )
            except Exception:
                pass

        threading.Thread(target=_warm, daemon=True).start()

    @staticmethod
    def _optimize_wav_bytes(audio_data: bytes) -> bytes:
        """
        Downsamples high-rate float32 WAV data in-memory to 16kHz PCM16 (Whisper's native format),
        reducing upload payload size by ~5.5x without losing transcription accuracy.
        """
        if len(audio_data) < 44 or not audio_data.startswith(b"RIFF"):
            return audio_data
        try:
            sr, data = wavfile.read(io.BytesIO(audio_data))
            target_sr = 16000
            if sr == target_sr and data.dtype == np.int16:
                return audio_data
            if data.ndim > 1:
                data = data[:, 0]
            if sr != target_sr and len(data) > 0:
                num_samples = max(1, int(len(data) * target_sr / sr))
                indices = np.linspace(0, len(data) - 1, num_samples).astype(np.int32)
                data = data[indices]
            if np.issubdtype(data.dtype, np.floating):
                pcm16 = np.clip(data * 32767.0, -32768, 32767).astype(np.int16)
            else:
                pcm16 = data.astype(np.int16)
            out = io.BytesIO()
            wavfile.write(out, target_sr, pcm16)
            return out.getvalue()
        except Exception:
            return audio_data

    def transcribe_bytes(self, audio_data: bytes, filename: str = "audio.wav", prompt: str = None) -> str:
        """
        Transcribes raw WAV bytes in memory (used for both file and real-time chunk transcription).
        """
        upload_bytes = self._optimize_wav_bytes(audio_data)
        params = {
            "file": (filename, upload_bytes),
            "model": self.model,
            "response_format": "text",
        }
        if prompt:
            params["prompt"] = prompt

        try:
            return self.client.audio.transcriptions.create(**params)
        except APIError:
            raise
        except Exception:
            params["model"] = self.fallback_model
            return self.client.audio.transcriptions.create(**params)

    def transcribe(self, audio_path: str, prompt: str = None) -> str:
        """
        Transcribes an audio file using Groq's Whisper model, with an optional context prompt.
        
        Args:
            audio_path (str): Path to the audio file.
            prompt (str, optional): An optional text prompt to guide the style, spelling,
                                   and syntax of the transcription.
            
        Returns:
            str: The transcribed text.
            
        Raises:
            FileNotFoundError: If the audio file does not exist.
            APIError: If the Groq API returns an error.
            Exception: For other unexpected errors.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            with open(audio_path, "rb") as file:
                audio_data = file.read()
            return self.transcribe_bytes(
                audio_data,
                filename=os.path.basename(audio_path),
                prompt=prompt,
            )
        except APIError as e:
            # Re-raise APIError to be handled by the caller
            raise e
        except Exception as e:
            # Wrap other exceptions if necessary or just let them propagate
            raise Exception(f"An unexpected error occurred during transcription: {str(e)}")
