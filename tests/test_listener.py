import unittest
import os
import tempfile
import time
from unittest.mock import MagicMock
from src.service.listener import HotkeyListener

class TestHotkeyListener(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for the test named pipe
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pipe_path = os.path.join(self.temp_dir.name, "test_pipe")
        self.mock_callback = MagicMock()
        self.mock_search_callback = MagicMock()
        self.mock_dashboard_callback = MagicMock()
        self.mock_quit_callback = MagicMock()
        self.listener = HotkeyListener(pipe_path=self.pipe_path)

    def tearDown(self):
        self.listener.stop()
        self.temp_dir.cleanup()

    def test_start_creates_pipe(self):
        """Test that start() correctly creates the pipe file."""
        self.assertFalse(os.path.exists(self.pipe_path))
        self.listener.start(
            callback=self.mock_callback,
            search_callback=self.mock_search_callback,
            dashboard_callback=self.mock_dashboard_callback,
            quit_callback=self.mock_quit_callback
        )
        self.assertTrue(os.path.exists(self.pipe_path))
        self.assertTrue(self.listener.running)

    def test_trigger_callback(self):
        """Test that writing 'TRIGGER' to the pipe executes the callback."""
        self.listener.start(
            callback=self.mock_callback,
            search_callback=self.mock_search_callback,
            dashboard_callback=self.mock_dashboard_callback,
            quit_callback=self.mock_quit_callback
        )

        # Write to pipe (blocks until read loop opens it)
        with open(self.pipe_path, 'w') as f:
            f.write("TRIGGER")

        # Allow minor propagation delay
        time.sleep(0.1)
        self.mock_callback.assert_called_once()
        self.mock_search_callback.assert_not_called()
        self.mock_dashboard_callback.assert_not_called()
        self.mock_quit_callback.assert_not_called()

    def test_search_callback(self):
        """Test that writing 'SEARCH' to the pipe executes the search callback."""
        self.listener.start(
            callback=self.mock_callback,
            search_callback=self.mock_search_callback,
            dashboard_callback=self.mock_dashboard_callback,
            quit_callback=self.mock_quit_callback
        )

        with open(self.pipe_path, 'w') as f:
            f.write("SEARCH")

        time.sleep(0.1)
        self.mock_search_callback.assert_called_once()
        self.mock_callback.assert_not_called()
        self.mock_dashboard_callback.assert_not_called()
        self.mock_quit_callback.assert_not_called()

    def test_dashboard_callback(self):
        """Test that writing 'DASHBOARD' to the pipe executes the dashboard callback."""
        self.listener.start(
            callback=self.mock_callback,
            search_callback=self.mock_search_callback,
            dashboard_callback=self.mock_dashboard_callback,
            quit_callback=self.mock_quit_callback
        )

        with open(self.pipe_path, 'w') as f:
            f.write("DASHBOARD")

        time.sleep(0.1)
        self.mock_dashboard_callback.assert_called_once()
        self.mock_callback.assert_not_called()
        self.mock_search_callback.assert_not_called()
        self.mock_quit_callback.assert_not_called()

    def test_quit_callback_and_graceful_stop(self):
        """Test that writing 'QUIT' triggers the quit callback and terminates the listener thread."""
        self.listener.start(
            callback=self.mock_callback,
            search_callback=self.mock_search_callback,
            quit_callback=self.mock_quit_callback
        )

        with open(self.pipe_path, 'w') as f:
            f.write("QUIT")

        time.sleep(0.1)
        self.mock_quit_callback.assert_called_once()
        self.assertFalse(self.listener.running)
        self.assertFalse(os.path.exists(self.pipe_path))

    def test_stop_deletes_pipe(self):
        """Test that calling stop() manually removes the pipe file."""
        self.listener.start(
            callback=self.mock_callback,
            search_callback=self.mock_search_callback,
            quit_callback=self.mock_quit_callback
        )
        self.assertTrue(os.path.exists(self.pipe_path))
        self.listener.stop()
        self.assertFalse(os.path.exists(self.pipe_path))
        self.assertFalse(self.listener.running)

if __name__ == '__main__':
    unittest.main()
