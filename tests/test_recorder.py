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
    @patch('sounddevice.rec')
    @patch('sounddevice.wait')
    @patch('sounddevice.default')
    def test_record_success(self, mock_default, mock_wait, mock_rec, mock_query):
        # Setup mocks
        mock_query.return_value = [{'index': 0, 'max_input_channels': 1}]
        mock_default.device = [0]
        
        duration = 1.0
        expected_samples = int(duration * self.recorder.samplerate)
        # Create a dummy mono signal (1D array)
        dummy_data = np.random.uniform(-1, 1, expected_samples).astype('float32')
        mock_rec.return_value = dummy_data

        # Execute
        self.recorder.record(self.output_path, duration)

        # Verify file creation and properties
        self.assertTrue(os.path.exists(self.output_path))
        
        sample_rate, data = wavfile.read(self.output_path)
        
        # Verify sample rate
        self.assertEqual(sample_rate, self.recorder.samplerate)
        
        # Verify mono (data should be 1D)
        self.assertEqual(len(data.shape), 1)
        
        # Verify duration (approximate)
        self.assertAlmostEqual(len(data) / sample_rate, duration, delta=0.1)

    @patch('sounddevice.query_devices')
    def test_record_no_devices(self, mock_query):
        # Mock no devices available
        mock_query.return_value = []
        
        with self.assertRaises(RuntimeError) as cm:
            self.recorder.record(self.output_path, 1.0)
        
        self.assertEqual(str(cm.exception), "No audio devices found.")

    @patch('sounddevice.query_devices')
    def test_record_no_input_devices(self, mock_query):
        # Mock devices available but none have input channels
        mock_query.return_value = [{'index': 0, 'max_input_channels': 0}]
        
        # We also need to mock sd.default.device to be None to trigger the input_devices check
        with patch('sounddevice.default') as mock_default:
            mock_default.device = [None]
            with self.assertRaises(RuntimeError) as cm:
                self.recorder.record(self.output_path, 1.0)
            
            self.assertEqual(str(cm.exception), "No audio input device found.")

if __name__ == '__main__':
    unittest.main()
