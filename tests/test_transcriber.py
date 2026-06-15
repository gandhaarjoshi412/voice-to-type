import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import sys

# Workaround for Windows/Anaconda SSL DLL loading mismatch
import ssl
orig_create_default_context = ssl.create_default_context
def dummy_create_default_context(*args, **kwargs):
    try:
        return orig_create_default_context(*args, **kwargs)
    except Exception:
        return MagicMock()
ssl.create_default_context = dummy_create_default_context

from src.core.transcriber import Transcriber
from groq import APIError

class TestTranscriber(unittest.TestCase):
    def setUp(self):
        self.api_key = "test_api_key"
        self.audio_path = "/tmp/test_audio.wav"
        with patch.dict(os.environ, {}, clear=True):
            with patch('src.core.transcriber.Groq') as mock_groq:
                self.transcriber = Transcriber(api_key=self.api_key)
                self.mock_groq_client = mock_groq.return_value

    def test_init_no_api_key(self):
        """Test that ValueError is raised when no API key is provided and env var is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as cm:
                Transcriber(api_key=None)
            self.assertEqual(str(cm.exception), "Groq API key must be provided or set as GROQ_API_KEY environment variable.")

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake audio data")
    def test_transcribe_success(self, mock_file, mock_exists):
        """Test successful transcription."""
        mock_exists.return_value = True
        
        # Mock the Groq client's transcription create method
        expected_text = "Hello, this is a test transcription."
        self.transcriber.client.audio.transcriptions.create = MagicMock(return_value=expected_text)
        
        result = self.transcriber.transcribe(self.audio_path)
        
        self.assertEqual(result, expected_text)
        self.transcriber.client.audio.transcriptions.create.assert_called_once()
        # Verify correct model is used
        args, kwargs = self.transcriber.client.audio.transcriptions.create.call_args
        self.assertEqual(kwargs['model'], "whisper-large-v3-turbo")
        self.assertEqual(kwargs['response_format'], "text")

    @patch("os.path.exists")
    def test_transcribe_file_not_found(self, mock_exists):
        """Test transcription failure when audio file does not exist."""
        mock_exists.return_value = False
        
        with self.assertRaises(FileNotFoundError):
            self.transcriber.transcribe("non_existent_file.wav")

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake audio data")
    def test_transcribe_api_error(self, mock_file, mock_exists):
        """Test transcription failure due to Groq APIError."""
        mock_exists.return_value = True
        
        # Simulate an APIError
        self.transcriber.client.audio.transcriptions.create = MagicMock(side_effect=APIError("API Error occurred", MagicMock(), body={}))
        
        with self.assertRaises(APIError):
            self.transcriber.transcribe(self.audio_path)

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake audio data")
    def test_transcribe_unexpected_error(self, mock_file, mock_exists):
        """Test transcription failure due to an unexpected exception."""
        mock_exists.return_value = True
        
        # Simulate an unexpected exception
        self.transcriber.client.audio.transcriptions.create = MagicMock(side_effect=RuntimeError("Unexpected system error"))
        
        with self.assertRaises(Exception) as cm:
            self.transcriber.transcribe(self.audio_path)
        self.assertIn("An unexpected error occurred during transcription", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
