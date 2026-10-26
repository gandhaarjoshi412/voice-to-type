import os
import sys
import logging
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QPainterPath, QFont
)

logger = logging.getLogger(__name__)


def create_tray_icon(is_recording: bool = False, size: int = 64) -> QIcon:
    """
    Renders a crisp high-DPI system tray icon using QPainter.
    Normal mode: Elegant cyan/indigo microphone badge.
    Recording mode: Vibrant red pulsating recording badge.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    center = size / 2.0
    radius = size * 0.42

    if is_recording:
        # Outer red glow ring
        painter.setPen(QPen(QColor(239, 68, 68, 120), size * 0.08))
        painter.setBrush(QBrush(QColor(220, 38, 38, 230)))
        painter.drawEllipse(int(center - radius), int(center - radius), int(radius * 2), int(radius * 2))

        # Inner bright core
        inner_r = radius * 0.45
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
        painter.drawEllipse(int(center - inner_r), int(center - inner_r), int(inner_r * 2), int(inner_r * 2))
    else:
        # Dark circular background with subtle cyan border
        painter.setPen(QPen(QColor(0, 210, 255, 180), size * 0.06))
        painter.setBrush(QBrush(QColor(18, 20, 28, 240)))
        painter.drawEllipse(int(center - radius), int(center - radius), int(radius * 2), int(radius * 2))

        # Microphone capsule & stand (clean vector glyph)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 210, 255, 240)))

        # Mic capsule
        capsule_w = size * 0.22
        capsule_h = size * 0.36
        capsule_x = center - capsule_w / 2.0
        capsule_y = center - capsule_h / 2.0 - size * 0.04
        painter.drawRoundedRect(
            int(capsule_x), int(capsule_y),
            int(capsule_w), int(capsule_h),
            capsule_w / 2.0, capsule_w / 2.0
        )

        # Mic cradle arc
        arc_pen = QPen(QColor(255, 255, 255, 220), size * 0.055, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc_r = size * 0.20
        arc_rect_x = center - arc_r
        arc_rect_y = capsule_y + capsule_h * 0.25
        arc_path = QPainterPath()
        arc_path.arcMoveTo(arc_rect_x, arc_rect_y, arc_r * 2, arc_r * 1.5, 0)
        arc_path.arcTo(arc_rect_x, arc_rect_y, arc_r * 2, arc_r * 1.5, 0, -180)
        painter.drawPath(arc_path)

        # Stand stem
        stem_top_y = arc_rect_y + arc_r * 1.5 / 2.0
        stem_bottom_y = stem_top_y + size * 0.12
        painter.drawLine(int(center), int(stem_top_y), int(center), int(stem_bottom_y))

        # Stand base
        base_w = size * 0.16
        painter.drawLine(int(center - base_w / 2.0), int(stem_bottom_y), int(center + base_w / 2.0), int(stem_bottom_y))

    painter.end()
    return QIcon(pixmap)


class VoiceTypeTray(QObject):
    """
    System Tray Icon and Context Menu manager for Voice to Type.
    Provides persistent background presence, visual recording state,
    and direct access to the Dashboard, History Finder, and Recording toggles.
    """
    trigger_record = pyqtSignal()
    trigger_dashboard = pyqtSignal()
    trigger_finder = pyqtSignal()
    trigger_quit = pyqtSignal()
    trigger_recording_state = pyqtSignal(bool)
    trigger_update_storage = pyqtSignal()

    def __init__(self, storage_manager=None, parent=None):
        super().__init__(parent)
        self.storage_manager = storage_manager
        self.is_recording = False

        self.icon_normal = create_tray_icon(is_recording=False)
        self.icon_recording = create_tray_icon(is_recording=True)

        self.tray_icon = QSystemTrayIcon(self.icon_normal, parent)
        self.tray_icon.setToolTip("Voice to Type — Background Active (Ready)")

        self._build_context_menu()
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.trigger_recording_state.connect(self.set_recording_state)
        self.trigger_update_storage.connect(self.update_storage_indicator)

    def _build_context_menu(self):
        self.menu = QMenu()
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #1a1b23;
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 8px;
                padding: 6px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2e3244;
                color: #00d2ff;
            }
            QMenu::item:disabled {
                color: #64748b;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 12);
                margin: 4px 6px;
            }
        """)

        # Header Title (disabled, bold)
        self.header_action = self.menu.addAction("🎙️ Voice to Type")
        self.header_action.setEnabled(False)

        # Status text
        self.status_action = self.menu.addAction("● Status: Ready")
        self.status_action.setEnabled(False)

        self.menu.addSeparator()

        # Action items
        self.record_action = self.menu.addAction("🎙️ Toggle Recording")
        self.record_action.triggered.connect(self.trigger_record.emit)

        self.dashboard_action = self.menu.addAction("📊 Open Analytics Dashboard")
        self.dashboard_action.triggered.connect(self.trigger_dashboard.emit)

        self.finder_action = self.menu.addAction("🔍 Search Past Dictations")
        self.finder_action.triggered.connect(self.trigger_finder.emit)

        self.menu.addSeparator()

        # Storage indicator
        self.storage_action = self.menu.addAction("💾 Storage: Checking...")
        self.storage_action.setEnabled(False)
        self.update_storage_indicator()

        self.menu.addSeparator()

        # Quit
        self.quit_action = self.menu.addAction("✕ Quit Voice to Type")
        self.quit_action.triggered.connect(self.trigger_quit.emit)

        self.tray_icon.setContextMenu(self.menu)

    def show(self):
        """Displays the tray icon in the system tray."""
        self.tray_icon.show()

    def hide(self):
        """Hides the tray icon."""
        self.tray_icon.hide()

    def _on_tray_activated(self, reason):
        """
        Handles clicks on the tray icon.
        Left-click or double-click opens the Analytics Dashboard.
        """
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick
        ):
            self.trigger_dashboard.emit()

    def set_recording_state(self, is_recording: bool):
        """
        Updates tray icon, tooltip, and menu state to reflect current recording mode.
        """
        self.is_recording = is_recording
        if is_recording:
            self.tray_icon.setIcon(self.icon_recording)
            self.tray_icon.setToolTip("Voice to Type — 🔴 Recording Voice...")
            self.status_action.setText("🔴 Status: Recording...")
            self.record_action.setText("⏹ Stop Recording")
        else:
            self.tray_icon.setIcon(self.icon_normal)
            self.tray_icon.setToolTip("Voice to Type — Background Active (Ready)")
            self.status_action.setText("● Status: Ready")
            self.record_action.setText("🎙️ Toggle Recording")
            self.update_storage_indicator()

    def update_storage_indicator(self):
        """Refreshes the storage usage label in the context menu."""
        if self.storage_manager:
            try:
                storage = self.storage_manager.get_storage_usage()
                size_mb = storage.get("size_mb", 0.0)
                limit_mb = storage.get("limit_mb", 1024.0)
                pct = storage.get("percent", 0.0)
                self.storage_action.setText(f"💾 Audio Storage: {size_mb:.1f} MB / {limit_mb:.0f} MB ({pct:.0f}%)")
            except Exception:
                self.storage_action.setText("💾 Audio Storage: Active")

    def show_notification(self, title: str, message: str, is_error: bool = False):
        """
        Shows a native system notification bubble from the system tray.
        """
        icon_type = (
            QSystemTrayIcon.MessageIcon.Critical if is_error
            else QSystemTrayIcon.MessageIcon.Information
        )
        self.tray_icon.showMessage(title, message, icon_type, 3000)
