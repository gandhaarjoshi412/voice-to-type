import os
import sys
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QApplication, QLabel, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect,
    QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QColor, QFont, QIcon
import sounddevice as sd
from scipy.io import wavfile
import logging

logger = logging.getLogger(__name__)

class FinderResultItem(QWidget):
    play_audio_signal = pyqtSignal(str)

    def __init__(self, record):
        super().__init__()
        self.record = record
        
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Text and Context
        text_layout = QVBoxLayout()
        
        text_label = QLabel(record.get('text', ''))
        text_label.setWordWrap(True)
        text_label.setStyleSheet("color: white; font-size: 14px;")
        
        context_str = f"{record.get('timestamp', '')} | {record.get('app_name', 'Unknown')}"
        context_label = QLabel(context_str)
        context_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        
        text_layout.addWidget(text_label)
        text_layout.addWidget(context_label)
        
        layout.addLayout(text_layout)
        
        # Play Button (if audio exists)
        audio_path = record.get('audio_path', '')
        if audio_path and os.path.exists(audio_path):
            self.play_btn = QPushButton("▶ Play")
            self.play_btn.setFixedSize(60, 30)
            self.play_btn.setStyleSheet("""
                QPushButton {
                    background-color: #333333;
                    color: white;
                    border-radius: 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #555555;
                }
            """)
            self.play_btn.clicked.connect(self._on_play_clicked)
            layout.addWidget(self.play_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
        self.setLayout(layout)
        self.setStyleSheet("background: transparent;")

    def _on_play_clicked(self):
        self.play_audio_signal.emit(self.record.get('audio_path'))

class FinderWindow(QWidget):
    trigger_toggle = pyqtSignal()

    def __init__(self, storage_manager):
        super().__init__()
        self.storage_manager = storage_manager
        self.is_playing = False
        self._init_ui()
        self._load_results()
        self.trigger_toggle.connect(self.toggle_visibility)

    def _init_ui(self):
        # Frameless, translucent
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setFixedSize(600, 450)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Container frame for styling
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 35, 230);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
        """)
        
        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.container.setGraphicsEffect(shadow)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(15, 15, 15, 15)
        container_layout.setSpacing(10)
        
        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search transcribed text...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 10px;
                padding: 10px;
                font-size: 16px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(255, 255, 255, 100);
            }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        container_layout.addWidget(self.search_input)
        
        # Results list
        self.results_list = QListWidget()
        self.results_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
            }
            QListWidget::item {
                background-color: rgba(255, 255, 255, 5);
                border-radius: 8px;
                margin-bottom: 5px;
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 15);
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(0, 0, 0, 50);
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 50);
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 100);
            }
        """)
        self.results_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        container_layout.addWidget(self.results_list)
        
        main_layout.addWidget(self.container)
        self.setLayout(main_layout)
        
        # Debounce timer for search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._load_results)

    def _on_search_changed(self):
        self.search_timer.start(300)

    def _load_results(self):
        query = self.search_input.text().strip()
        records = self.storage_manager.search_records(query)
        
        self.results_list.clear()
        
        for record in records:
            item_widget = FinderResultItem(record)
            item_widget.play_audio_signal.connect(self._play_audio)
            
            list_item = QListWidgetItem(self.results_list)
            # Estimate size roughly based on text length
            list_item.setSizeHint(item_widget.sizeHint())
            self.results_list.addItem(list_item)
            self.results_list.setItemWidget(list_item, item_widget)

    def _play_audio(self, audio_path):
        if self.is_playing:
            sd.stop()
            self.is_playing = False
            return
            
        def play_thread():
            try:
                self.is_playing = True
                samplerate, data = wavfile.read(audio_path)
                sd.play(data, samplerate)
                sd.wait()
            except Exception as e:
                logger.error(f"Error playing audio: {e}")
            finally:
                self.is_playing = False

        threading.Thread(target=play_thread, daemon=True).start()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
            sd.stop() # stop audio if playing when hiding
            self.is_playing = False
        else:
            self._center_on_screen()
            self._load_results()
            self.search_input.clear()
            self.search_input.setFocus()
            self.show()

    def _center_on_screen(self):
        try:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2 - 100 # slightly above center
            self.move(x, y)
        except Exception:
            self.move(300, 300)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.toggle_visibility()
        else:
            super().keyPressEvent(event)
