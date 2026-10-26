import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

class HotkeyListener:
    """
    A class that sets up a Named Pipe (FIFO) to listen for control triggers
    and execute corresponding callback functions, replacing raw global keyboard hooks.
    """
    def __init__(self, pipe_path: str = "/tmp/antigravity_pipe"):
        self.pipe_path = os.path.abspath(pipe_path)
        self.running = False
        self._thread = None
        self.callback = None
        self.search_callback = None
        self.dashboard_callback = None
        self.quit_callback = None

    def start(self, callback=None, search_callback=None, quit_callback=None, dashboard_callback=None):
        """
        Starts the pipe listener in a background thread.
        """
        if self.running:
            logger.warning("Pipe listener is already running.")
            return

        self.callback = callback
        self.search_callback = search_callback
        self.dashboard_callback = dashboard_callback
        self.quit_callback = quit_callback
        self.running = True

        # Clean up any stale pipe
        if os.path.exists(self.pipe_path):
            try:
                os.remove(self.pipe_path)
                logger.info(f"Removed stale pipe at {self.pipe_path}")
            except Exception as e:
                logger.error(f"Failed to remove stale pipe {self.pipe_path}: {e}")
                raise e

        # Create new Named Pipe (FIFO)
        try:
            os.mkfifo(self.pipe_path)
            # Ensure the pipe is writable by trigger scripts run under other user contexts if needed
            os.chmod(self.pipe_path, 0o666)
            logger.info(f"Created named pipe (FIFO) at {self.pipe_path}")
        except Exception as e:
            logger.error(f"Failed to create named pipe at {self.pipe_path}: {e}")
            self.running = False
            raise e

        # Start the background thread for blocking reads
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("Pipe listener thread started successfully.")

    def _listen_loop(self):
        """
        Main loop running in a background thread. Blocks waiting to read from the pipe.
        """
        while self.running:
            try:
                # opening the pipe for reading blocks until a writer opens it
                # We open in read mode ('r'). We wrap it in a try-except to handle exits
                if not os.path.exists(self.pipe_path):
                    if not self.running:
                        break
                    # If pipe was deleted but we are still running, recreate it
                    try:
                        os.mkfifo(self.pipe_path)
                        os.chmod(self.pipe_path, 0o666)
                    except Exception:
                        pass
                    time.sleep(0.5)
                    continue

                with open(self.pipe_path, 'r') as fifo:
                    data = fifo.read().strip()

                if not data:
                    # Writer closed the pipe without writing or sent EOF
                    # Sleep briefly to avoid busy loop if writer keeps opening/closing quickly
                    time.sleep(0.1)
                    continue

                logger.info(f"Received command from pipe: {data}")

                if data == "TRIGGER":
                    if self.callback:
                        self.callback()
                elif data == "SEARCH":
                    if self.search_callback:
                        self.search_callback()
                elif data == "DASHBOARD":
                    if self.dashboard_callback:
                        self.dashboard_callback()
                elif data == "QUIT":
                    if self.quit_callback:
                        self.quit_callback()
                    # Break loop on quit
                    break
            except Exception as e:
                if self.running:
                    logger.error(f"Error in pipe listener loop: {e}")
                    time.sleep(0.5)

        # Ensure cleanup if we exited the loop
        self.stop()

    def stop(self):
        """
        Stops the listener loop and deletes the pipe file.
        """
        if not self.running:
            return

        self.running = False
        logger.info("Stopping pipe listener...")

        # Delete the pipe file
        if os.path.exists(self.pipe_path):
            try:
                os.remove(self.pipe_path)
                logger.info(f"Deleted pipe file at {self.pipe_path}")
            except Exception as e:
                logger.error(f"Failed to delete pipe file {self.pipe_path}: {e}")
