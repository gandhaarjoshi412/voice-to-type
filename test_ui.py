import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from src.ui.overlay import GlassOverlay

if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = GlassOverlay()

    # Start recording immediately to trigger the fade-in
    QTimer.singleShot(1000, overlay.start_recording)

    # Stop after 5 seconds
    QTimer.singleShot(5000, app.quit)

    sys.exit(app.exec())

