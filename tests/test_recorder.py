import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from scipy.io import wavfile
import os
from src.core.recorder import Recorder

class TestRecorder(unittest.TestCase):
    def setUp(self):
        self.recorder = Recorder(samplerate=44100)
        self.output_path = "test_recording.wav"

    def tearDown(self):
        if os.path.exists(self.output_path):
            os.remove(self.output_path)

    @patch('sounddevice.query_devices')
    @patch('sounddevice.InputStream')
    @patch('sounddevice.default')
    def test_start_recording_success(self, mock_default, mock_input_stream, mock_query):
        """Test that start_recording successfully configures and starts the stream."""
        mock_query.return_value = [{'index': 0, 'max_input_channels': 1}]
        mock_default.device = [0]
        
        mock_stream = MagicMock()
        mock_input_stream.return_value = mock_stream
        
        self.recorder.start_recording()
        
        self.assertTrue(self.recorder.is_recording)
        mock_input_stream.assert_called_once()
        mock_stream.start.assert_called_once()
        
        # Cleanup
        self.recorder.is_recording = False
        self.recorder._stream = None

    @patch('sounddevice.query_devices')
    def test_start_recording_no_devices(self, mock_query):
        """Test that start_recording raises RuntimeError when no audio devices are found."""
        mock_query.return_value = []
        
        with self.assertRaises(RuntimeError) as cm:
            self.recorder.start_recording()
            
        self.assertEqual(str(cm.exception), "No audio devices found.")
        self.assertFalse(self.recorder.is_recording)

    @patch('sounddevice.query_devices')
    def test_start_recording_no_input_devices(self, mock_query):
        """Test that start_recording raises RuntimeError when no input devices are found."""
        mock_query.return_value = [{'index': 0, 'max_input_channels': 0}]
        
        with patch('sounddevice.default') as mock_default:
            mock_default.device = [None]
            with self.assertRaises(RuntimeError) as cm:
                self.recorder.start_recording()
                
            self.assertEqual(str(cm.exception), "No audio input device found.")
            self.assertFalse(self.recorder.is_recording)

    @patch('src.core.recorder.wavfile.write')
    def test_stop_recording_success(self, mock_wav_write):
        """Test that stop_recording closes the stream and writes recorded data to a WAV file."""
        mock_stream = MagicMock()
        self.recorder._stream = mock_stream
        self.recorder.is_recording = True
        
        # Place a dummy frame in the queue
        dummy_frame = np.zeros((1024, 1), dtype=np.float32)
        self.recorder.audio_queue.put(dummy_frame)
        
        self.recorder.stop_recording(self.output_path)
        
        self.assertFalse(self.recorder.is_recording)
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        self.assertIsNone(self.recorder._stream)
        
        mock_wav_write.assert_called_once()
        args, kwargs = mock_wav_write.call_args
        self.assertEqual(args[0], self.output_path)
        self.assertEqual(args[1], self.recorder.samplerate)
        # Verify it concatenated queue contents
        np.testing.assert_array_equal(args[2], dummy_frame)

if __name__ == '__main__':
    unittest.main()
