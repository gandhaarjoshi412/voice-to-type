"""
Wispr Flow Transcript History Finder — Warm paper aesthetic matching the Insights Dashboard.

Features:
- Warm stone (#F6F4EF) chassis + crisp paper (#FCFBF9) inner panel
- macOS traffic-light controls, draggable titlebar, and "ESC to close" pill
- Focused forest-teal (#1F6B5E) search bar with custom painted magnifying glass & live count
- Interactive filter pills (All Dictations, Today, With Audio, plus top apps)
- Date-grouped transcript feed (TODAY, YESTERDAY, or formatted date headers)
- Rich transcript cards with app initial badge, timestamp, word count, duration,
  one-click Copy -> "✓ Copied" confirmation, and circular ▶ audio playback button
"""

import os
import sys
import threading
import logging
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QPushButton, QGraphicsDropShadowEffect, QFrame, QScrollArea,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen
import sounddevice as sd
from scipy.io import wavfile

logger = logging.getLogger(__name__)

# ── Palette (matches Insights Dashboard 1:1) ─────────────────────────────
BG       = "#F6F4EF"
PANEL    = "#FCFBF9"
CARD     = "#F3F1EC"
CARD_HOV = "#ECE9E1"
TRACK    = "#E4E0D7"
TEXT     = "#1B1B1A"
MUTED    = "#7B776E"
TEAL     = "#1F6B5E"
TEAL_2   = "#3F9C8B"
GREEN_BG = "#DDF0E6"
GREEN_FG = "#2D7A55"

FONT_STACK = '"Inter", "Cantarell", "SF Pro Text", "Segoe UI", sans-serif'

APP_COLORS = [TEAL, TEAL_2, "#C98B3C", "#B9604E", "#8A6FB0", "#6F8FA6"]


def _app_color(name: str) -> str:
    if not name:
        return TEAL
    return APP_COLORS[sum(ord(c) for c in name) % len(APP_COLORS)]


class SearchMagnifierIcon(QWidget):
    """Hand-painted vector magnifying glass icon."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 20)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(MUTED), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(8.5, 8.5), 5.5, 5.5)
        p.drawLine(QPointF(12.8, 12.8), QPointF(17.0, 17.0))


class FinderResultItem(QFrame):
    """
    Single transcript card in the Finder list with app badge, metadata,
    one-click Copy confirmation, and optional audio playback button.
    """
    play_audio_signal = pyqtSignal(str)

    def __init__(self, record: dict, clean_app_name: str = "General"):
        super().__init__()
        self.record = record
        self.clean_app = clean_app_name or "General"
        self.setObjectName("FinderRow")
        self.setStyleSheet(f"""
            QFrame#FinderRow {{
                background: {CARD};
                border-radius: 14px;
                border: 1px solid rgba(0, 0, 0, 0.03);
            }}
            QFrame#FinderRow:hover {{
                background: {CARD_HOV};
            }}
            QLabel {{ background: transparent; }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        # Left: Colored circular app initial badge
        color = _app_color(self.clean_app)
        badge = QLabel(self.clean_app[:1].upper())
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background:{color}; color:white; border-radius:15px; font-size:12px; font-weight:600;"
        )
        lay.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

        # Center: Metadata row + full transcript text
        col = QVBoxLayout()
        col.setSpacing(4)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        app_lbl = QLabel(self.clean_app)
        app_lbl.setStyleSheet(f"color:{TEXT}; font-size:12px; font-weight:600;")

        time_str = self._format_time(record.get("timestamp", ""))
        words = record.get("word_count") or len((record.get("text") or "").split())
        dur = float(record.get("duration") or 0.0)
        dur_part = f" ({dur:.1f}s)" if dur > 0 else ""
        meta_lbl = QLabel(f"·  {time_str}  ·  {words} word{'s' if words != 1 else ''}{dur_part}")
        meta_lbl.setStyleSheet(f"color:{MUTED}; font-size:11px;")

        meta_row.addWidget(app_lbl)
        meta_row.addWidget(meta_lbl)
        meta_row.addStretch()
        col.addLayout(meta_row)

        text_label = QLabel((record.get("text") or "").strip())
        text_label.setWordWrap(True)
        text_label.setStyleSheet(f"color:{TEXT}; font-size:13px;")
        col.addWidget(text_label)

        lay.addLayout(col, stretch=1)

        # Right: Copy button + Play button
        actions = QHBoxLayout()
        actions.setSpacing(6)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setFixedHeight(30)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_copy_btn(copied=False)
        self.copy_btn.clicked.connect(self._on_copy_clicked)
        actions.addWidget(self.copy_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        audio_path = record.get("audio_path", "")
        if audio_path and os.path.exists(audio_path):
            self.play_btn = QPushButton("▶")
            self.play_btn.setFixedSize(30, 30)
            self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.play_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {TEAL};
                    color: white;
                    border: none;
                    border-radius: 15px;
                    font-size: 10px;
                    padding-left: 2px;
                }}
                QPushButton:hover {{
                    background: {TEAL_2};
                }}
            """)
            self.play_btn.clicked.connect(self._on_play_clicked)
            actions.addWidget(self.play_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        lay.addLayout(actions)

    @staticmethod
    def _format_time(ts: str) -> str:
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%I:%M %p")
        except Exception:
            return ts

    def _style_copy_btn(self, copied: bool):
        if copied:
            self.copy_btn.setText("✓ Copied")
            self.copy_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {GREEN_BG};
                    color: {GREEN_FG};
                    border: none;
                    border-radius: 9px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 0 11px;
                }}
            """)
        else:
            self.copy_btn.setText("Copy")
            self.copy_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #E8E4DC;
                    color: {TEXT};
                    border: none;
                    border-radius: 9px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 0 11px;
                }}
                QPushButton:hover {{
                    background: #DDD8CE;
                }}
            """)

    def _on_copy_clicked(self):
        try:
            cb = QApplication.clipboard()
            if cb is not None:
                cb.setText(self.record.get("text", ""))
        except Exception:
            pass
        self._style_copy_btn(copied=True)
        QTimer.singleShot(1400, lambda: self._style_copy_btn(copied=False))

    def _on_play_clicked(self):
        self.play_audio_signal.emit(self.record.get("audio_path", ""))


class FinderWindow(QWidget):
    """
    Wispr Flow Transcript History Finder window.
    """
    trigger_toggle = pyqtSignal()
    HEADER_H = 48

    def __init__(self, storage_manager):
        super().__init__()
        self.storage_manager = storage_manager
        self.is_playing = False
        self._active_filter = "all"
        self._drag_position = None

        self._init_ui()
        self._load_results()
        self.trigger_toggle.connect(self.toggle_visibility)

    def _init_ui(self):
        self.setWindowTitle("Transcript History")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(780, 600)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        self.container = QFrame()
        self.container.setObjectName("Chassis")
        self.container.setStyleSheet(f"""
            QFrame#Chassis {{
                background: {BG};
                border-radius: 20px;
                border: 1px solid rgba(0, 0, 0, 0.10);
            }}
            QFrame#Panel {{
                background: {PANEL};
                border-radius: 16px;
                border: 1px solid rgba(0, 0, 0, 0.05);
            }}
            QLabel, QPushButton, QLineEdit {{
                font-family: {FONT_STACK};
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(0, 0, 0, 0.16);
                border-radius: 3px;
                min-height: 28px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container.setGraphicsEffect(shadow)
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(18, 12, 18, 18)
        root.setSpacing(10)

        # 1. Titlebar (traffic lights + title + ESC badge)
        tbar = QHBoxLayout()
        tbar.setContentsMargins(4, 0, 4, 0)
        tbar.setSpacing(8)
        for color, hover, action in (
            ("#ff5f57", "#e0443e", self.toggle_visibility),
            ("#febc2e", "#dea123", self.showMinimized),
            ("#28c840", "#1fa833", None),
        ):
            b = QPushButton()
            b.setFixedSize(12, 12)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background:{color}; border:1px solid rgba(0,0,0,0.12); border-radius:6px; }} "
                f"QPushButton:hover {{ background:{hover}; }}"
            )
            if action:
                b.clicked.connect(action)
            tbar.addWidget(b)

        tbar.addSpacing(8)
        title = QLabel("Transcript History")
        title.setStyleSheet(f"color:{TEXT}; font-size:13px; font-weight:600; background:transparent;")
        tbar.addWidget(title)
        tbar.addStretch()

        esc_pill = QLabel("ESC to close")
        esc_pill.setStyleSheet(
            f"background:#EAE7DF; color:{MUTED}; font-size:10px; font-weight:600; "
            "border-radius:7px; padding:3px 8px;"
        )
        tbar.addWidget(esc_pill)
        root.addLayout(tbar)

        # 2. Inner paper panel
        panel = QFrame()
        panel.setObjectName("Panel")
        p_lay = QVBoxLayout(panel)
        p_lay.setContentsMargins(22, 18, 22, 18)
        p_lay.setSpacing(12)

        # Search bar
        search_box = QFrame()
        search_box.setObjectName("SearchBox")
        search_box.setStyleSheet(f"""
            QFrame#SearchBox {{
                background: {CARD};
                border: 1.5px solid {TEAL};
                border-radius: 12px;
            }}
        """)
        s_lay = QHBoxLayout(search_box)
        s_lay.setContentsMargins(14, 8, 14, 8)
        s_lay.setSpacing(10)
        s_lay.addWidget(SearchMagnifierIcon())

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search past dictations, apps, or keywords…")
        self.search_input.setStyleSheet(
            f"background:transparent; border:none; color:{TEXT}; font-size:14px;"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        s_lay.addWidget(self.search_input, stretch=1)

        self.count_label = QLabel("0 results")
        self.count_label.setStyleSheet(
            f"color:{MUTED}; font-size:11px; font-weight:600; background:transparent;"
        )
        s_lay.addWidget(self.count_label)
        p_lay.addWidget(search_box)

        # Filter chips row
        self.chips_layout = QHBoxLayout()
        self.chips_layout.setSpacing(8)
        p_lay.addLayout(self.chips_layout)

        # Scrollable date-grouped results list
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_host = QWidget()
        self.results_layout = QVBoxLayout(self.scroll_host)
        self.results_layout.setContentsMargins(0, 4, 4, 4)
        self.results_layout.setSpacing(8)
        self.results_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_host)
        p_lay.addWidget(self.scroll_area, stretch=1)

        root.addWidget(panel, stretch=1)

        # Debounce timer for search
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._load_results)

    def _on_search_changed(self):
        self.search_timer.start(220)

    def _set_filter(self, key: str):
        self._active_filter = key
        self._load_results()

    def _rebuild_filter_chips(self, all_records: list[dict]):
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Gather up to 3 top distinct clean app names
        app_counts: dict[str, int] = {}
        for r in all_records:
            clean = self._clean_app(r.get("app_name", ""))
            app_counts[clean] = app_counts.get(clean, 0) + 1
        top_apps = [a for a, _ in sorted(app_counts.items(), key=lambda kv: -kv[1])[:3]]

        specs = [
            ("all", "All Dictations"),
            ("today", "Today"),
            ("audio", "With Audio"),
        ] + [(f"app:{a}", a) for a in top_apps]

        for key, label in specs:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            active = (self._active_filter == key)
            if active:
                btn.setStyleSheet(
                    f"QPushButton {{ background:{TEAL}; color:white; border:none; "
                    "border-radius:10px; font-size:11px; font-weight:600; padding:4px 11px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background:{CARD}; color:{MUTED}; border:none; "
                    f"border-radius:10px; font-size:11px; font-weight:600; padding:4px 11px; }} "
                    f"QPushButton:hover {{ background:{CARD_HOV}; color:{TEXT}; }}"
                )
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self.chips_layout.addWidget(btn)

        self.chips_layout.addStretch()

    def _clean_app(self, raw_app: str) -> str:
        if hasattr(self.storage_manager, "_clean_app_name"):
            return self.storage_manager._clean_app_name(raw_app)
        return raw_app or "General"

    @staticmethod
    def _date_heading(date_str: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if date_str == today:
            return "TODAY"
        if date_str == yesterday:
            return "YESTERDAY"
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d, %Y").upper()
        except Exception:
            return date_str or "EARLIER"

    def perform_search(self):
        """Alias for _load_results() for API compatibility."""
        self._load_results()

    def _load_results(self):
        query = self.search_input.text().strip()
        raw_records = self.storage_manager.search_records(query)
        self._rebuild_filter_chips(raw_records)

        today_str = datetime.now().strftime("%Y-%m-%d")
        filtered = []
        for r in raw_records:
            if self._active_filter == "today":
                if not (r.get("timestamp") or "").startswith(today_str):
                    continue
            elif self._active_filter == "audio":
                ap = r.get("audio_path") or ""
                if not (ap and os.path.exists(ap)):
                    continue
            elif self._active_filter.startswith("app:"):
                target_app = self._active_filter.split("app:", 1)[1]
                if self._clean_app(r.get("app_name", "")) != target_app:
                    continue
            filtered.append(r)

        self.count_label.setText(f"{len(filtered)} result{'s' if len(filtered) != 1 else ''}")

        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not filtered:
            empty = QLabel("No matching dictations found.")
            empty.setStyleSheet(f"color:{MUTED}; font-size:13px; padding:24px; background:transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_layout.addWidget(empty)
            self.results_layout.addStretch()
            return

        last_date = None
        for record in filtered:
            ts = record.get("timestamp") or ""
            date_part = ts[:10]
            if date_part != last_date:
                hdr = QLabel(self._date_heading(date_part))
                hdr.setStyleSheet(
                    f"color:{MUTED}; font-size:10px; font-weight:700; "
                    "letter-spacing:0.6px; margin-top:4px; background:transparent;"
                )
                self.results_layout.addWidget(hdr)
                last_date = date_part

            clean_app = self._clean_app(record.get("app_name", ""))
            row = FinderResultItem(record, clean_app_name=clean_app)
            row.play_audio_signal.connect(self._play_audio)
            self.results_layout.addWidget(row)

        self.results_layout.addStretch()

    def _play_audio(self, audio_path: str):
        if not audio_path or not os.path.exists(audio_path):
            return
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
            sd.stop()
            self.is_playing = False
        else:
            self._center_on_screen()
            self._active_filter = "all"
            self.search_input.clear()
            self._load_results()
            self.show()
            self.raise_()
            self.activateWindow()
            self.search_input.setFocus()

    def _center_on_screen(self):
        try:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = max(40, (screen.height() - self.height()) // 2 - 60)
            self.move(x, y)
        except Exception:
            self.move(300, 220)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < self.HEADER_H + 16:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.toggle_visibility()
        else:
            super().keyPressEvent(event)
