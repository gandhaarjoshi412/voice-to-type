"""
Insights dashboard — warm, minimal "paper" design.

Sidebar + tabbed content (Your Usage / Your Voice / History) with a pace gauge,
app-usage bars and a streak heatmap. Everything is custom painted or styled
through object-name scoped stylesheets (so labels never inherit card borders).
"""

import os
import sys
import threading
import logging
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QGridLayout, QGraphicsDropShadowEffect, QSizePolicy,
    QApplication, QStackedWidget, QButtonGroup, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QFont
import sounddevice as sd
from scipy.io import wavfile

logger = logging.getLogger(__name__)

# ── Palette ──────────────────────────────────────────────────────────────
BG      = "#F6F4EF"   # window / sidebar
PANEL   = "#FCFBF9"   # main content panel
CARD    = "#F3F1EC"   # cards
TRACK   = "#E4E0D7"   # empty bars / heatmap cells
TEXT    = "#1B1B1A"
MUTED   = "#7B776E"
TEAL    = "#1F6B5E"
TEAL_2  = "#3F9C8B"
TEAL_3  = "#8CC5B8"
GREEN_BG = "#DDF0E6"
GREEN_FG = "#2D7A55"
RED     = "#E5534B"

FONT_STACK = '"Inter", "Cantarell", "SF Pro Text", "Segoe UI", sans-serif'

APP_ICON_COLORS = [TEAL, TEAL_2, "#C98B3C", "#B9604E", "#8A6FB0", "#6F8FA6"]


def _font(px, weight=QFont.Weight.Normal):
    f = QFont()
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def _fmt_duration(minutes: float) -> str:
    if minutes >= 60:
        return f"{minutes / 60:.1f} hrs"
    return f"{minutes:.0f} min"


# ── Custom painted widgets ───────────────────────────────────────────────

class LogoWidget(QWidget):
    """Tiny five-bar waveform mark for the sidebar."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(28, 28)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TEXT))
        heights = [10, 18, 24, 14, 8]
        for i, h in enumerate(heights):
            p.drawRoundedRect(QRectF(2 + i * 5, (28 - h) / 2, 3, h), 1.5, 1.5)


class GaugeWidget(QWidget):
    """Semicircle gauge with a big centred value and a caption."""
    def __init__(self, caption="WORDS PER MINUTE", max_value=250):
        super().__init__()
        self.caption = caption
        self.max_value = max_value
        self.value = 0
        self.setMinimumHeight(130)

    def set_value(self, value):
        self.value = value
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pen_w = 16
        radius = min((w - 2 * pen_w) / 2, h - pen_w / 2 - 4 - 46)
        radius = max(radius, 30)
        cx, cy = w / 2, pen_w / 2 + 4 + radius
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        track = QPen(QColor(TRACK), pen_w)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track)
        p.drawArc(rect, 180 * 16, -180 * 16)

        frac = max(0.0, min(1.0, self.value / float(self.max_value)))
        if frac > 0:
            fill = QPen(QColor(TEAL), pen_w)
            fill.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(fill)
            p.drawArc(rect, 180 * 16, -int(frac * 180 * 16))

        p.setPen(QColor(TEXT))
        p.setFont(_font(36, QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - 90, cy - 44, 180, 44), Qt.AlignmentFlag.AlignCenter, f"{self.value:,.0f}")
        p.setPen(QColor(MUTED))
        p.setFont(_font(10, QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - 110, cy + 4, 220, 16), Qt.AlignmentFlag.AlignCenter, self.caption)


class BarChartWidget(QWidget):
    """Rounded pill bars. items: [{'label','value','highlight'}]"""
    def __init__(self, label_every=1, show_values=True):
        super().__init__()
        self.items = []
        self.label_every = label_every
        self.show_values = show_values
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, items):
        self.items = items or []
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if not self.items:
            return
        top, bottom, side = 22, 26, 6
        chart_h = h - top - bottom
        slot = (w - 2 * side) / len(self.items)
        bar_w = min(26.0, slot * 0.55)
        max_v = max([i["value"] for i in self.items] + [1])

        for idx, item in enumerate(self.items):
            cx = side + (idx + 0.5) * slot
            track = QRectF(cx - bar_w / 2, top, bar_w, chart_h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(TRACK if not item.get("highlight") else "#D9D4C8"))
            p.drawRoundedRect(track, bar_w / 2, bar_w / 2)

            v = item["value"]
            if v > 0:
                bh = max(bar_w, v / max_v * chart_h)
                bar = QRectF(cx - bar_w / 2, top + chart_h - bh, bar_w, bh)
                p.setBrush(QColor(TEAL if item.get("highlight") else TEAL_2))
                p.drawRoundedRect(bar, bar_w / 2, bar_w / 2)
                if self.show_values:
                    p.setPen(QColor(TEXT))
                    p.setFont(_font(10, QFont.Weight.Medium))
                    p.drawText(QRectF(cx - 26, bar.top() - 17, 52, 14),
                               Qt.AlignmentFlag.AlignCenter, f"{v:,}")

            if idx % self.label_every == 0:
                hl = item.get("highlight")
                p.setPen(QColor(TEAL if hl else MUTED))
                p.setFont(_font(11, QFont.Weight.DemiBold if hl else QFont.Weight.Normal))
                p.drawText(QRectF(cx - 24, top + chart_h + 6, 48, 16),
                           Qt.AlignmentFlag.AlignCenter, item["label"])


class HeatmapWidget(QWidget):
    """GitHub-style weekday x week activity grid in teal."""
    WEEKS = 16
    SHADES = [TRACK, "#BFDCD3", TEAL_3, TEAL_2, TEAL]

    def __init__(self):
        super().__init__()
        self.by_date = {}
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, daily):
        self.by_date = {d["date"]: d["words"] for d in (daily or [])}
        self.update()

    def _level(self, words, max_w):
        if words <= 0:
            return 0
        return min(4, 1 + int(words / max(1, max_w) * 3.999))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        left, top, bottom = 30, 18, 22
        today = datetime.now().date()
        start = today - timedelta(days=today.weekday()) - timedelta(weeks=self.WEEKS - 1)
        max_w = max(list(self.by_date.values()) + [1])

        cell = min((w - left) / self.WEEKS, (h - top - bottom) / 7.0)
        gap = max(2.0, cell * 0.14)
        size = cell - gap

        p.setFont(_font(10))
        p.setPen(QColor(MUTED))
        for r, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            p.drawText(QRectF(0, top + r * cell, left - 4, size),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)

        last_month = None
        for c in range(self.WEEKS):
            week_start = start + timedelta(weeks=c)
            if week_start.month != last_month:
                p.setPen(QColor(MUTED))
                p.drawText(QRectF(left + c * cell, 0, 40, 14), Qt.AlignmentFlag.AlignLeft,
                           week_start.strftime("%b"))
                last_month = week_start.month
            for r in range(7):
                day = week_start + timedelta(days=r)
                if day > today:
                    continue
                words = self.by_date.get(day.strftime("%Y-%m-%d"), 0)
                rect = QRectF(left + c * cell, top + r * cell, size, size)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(self.SHADES[self._level(words, max_w)]))
                p.drawRoundedRect(rect, 3, 3)
                if day == today:
                    p.setPen(QPen(QColor(TEXT), 1.2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3.5, 3.5)

        # Legend
        ly = h - 14
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(left, ly - 2, 30, 14), Qt.AlignmentFlag.AlignLeft, "Less")
        for i, col in enumerate(self.SHADES):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(left + 34 + i * 14, ly, 10, 10), 2.5, 2.5)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(left + 34 + 5 * 14 + 2, ly - 2, 30, 14), Qt.AlignmentFlag.AlignLeft, "More")


class AppBarRow(QWidget):
    """[letter badge] [percent bar] [count] for one application."""
    def __init__(self, name, percent, words, sessions, color):
        super().__init__()
        self.name, self.percent, self.color = name, percent, color
        self.setFixedHeight(34)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        badge = QLabel(name[:1].upper())
        badge.setFixedSize(26, 26)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background:{color}; color:white; border-radius:13px; font-size:12px; font-weight:600;")
        lay.addWidget(badge)

        self.bar = _PercentBar(percent, color, name)
        lay.addWidget(self.bar, stretch=1)

        count = QLabel(f"{words:,} WORDS")
        count.setFixedWidth(96)
        count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        count.setStyleSheet(f"color:{MUTED}; font-size:10px; font-weight:600; background:transparent;")
        lay.addWidget(count)


class _PercentBar(QWidget):
    def __init__(self, percent, color, name):
        super().__init__()
        self.percent, self.color, self.name = percent, color, name
        self.setMinimumHeight(26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(QRectF(0, 0, w, h), 6, 6)
        fw = max(h, w * min(100.0, max(0.0, self.percent)) / 100.0)
        p.setBrush(QColor(self.color))
        p.drawRoundedRect(QRectF(0, 0, fw, h), 6, 6)
        p.setPen(QColor("white"))
        p.setFont(_font(11, QFont.Weight.DemiBold))
        p.drawText(QRectF(10, 0, fw - 12, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   f"{self.percent:.0f}%")
        # app name sits on the empty track if it fits
        p.setPen(QColor(MUTED))
        p.setFont(_font(11))
        if w - fw > 90:
            p.drawText(QRectF(fw + 10, 0, w - fw - 14, h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.name)


class RecentSessionRow(QFrame):
    play_audio_signal = pyqtSignal(str)

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record = record
        self.setObjectName("Row")
        self.setStyleSheet(f"""
            QFrame#Row {{ background:{CARD}; border-radius:14px; }}
            QFrame#Row:hover {{ background:#ECE9E1; }}
            QLabel {{ background:transparent; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(4)
        app = record.get("app_name") or "General"
        words = record.get("word_count", 0)
        dur = record.get("duration", 0.0)
        meta = QLabel(f"{app}  ·  {record.get('timestamp', '')}  ·  {words} words, {dur:.1f}s")
        meta.setStyleSheet(f"color:{MUTED}; font-size:11px;")
        text = QLabel((record.get("text") or "").strip())
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{TEXT}; font-size:14px;")
        col.addWidget(meta)
        col.addWidget(text)
        lay.addLayout(col, stretch=1)

        path = record.get("audio_path", "")
        if path and os.path.exists(path):
            btn = QPushButton("▶")
            btn.setFixedSize(34, 34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background:{TEAL}; color:white; border:none; border-radius:17px;
                               font-size:11px; padding-left:2px; }}
                QPushButton:hover {{ background:{TEAL_2}; }}
            """)
            btn.clicked.connect(lambda: self.play_audio_signal.emit(path))
            lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignVCenter)


class SideIcon(QPushButton):
    """Sidebar button with a hand-painted line icon (no font-glyph dependence)."""
    def __init__(self, kind, tip, active=False):
        super().__init__()
        self.kind = kind
        self.active = active
        self.recording = False
        self.setToolTip(tip)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restyle()

    def _restyle(self):
        if self.recording:
            bg, hov = "#FBE3E1", "#F8D3D0"
        else:
            bg, hov = ("#E9E6DF" if self.active else "transparent"), "#EAE7E0"
        self.setStyleSheet(f"QPushButton {{ background:{bg}; border:none; border-radius:11px; }}"
                           f"QPushButton:hover {{ background:{hov}; }}")

    def set_recording(self, recording):
        self.recording = recording
        self._restyle()
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        pen = QPen(QColor(TEXT), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if self.kind == "insights":
            for i, h in enumerate([8, 14, 10, 17]):
                x = cx - 9 + i * 6
                p.drawLine(QPointF(x, cy + 8), QPointF(x, cy + 8 - h))
        elif self.kind == "record":
            if self.recording:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(RED))
                p.drawRoundedRect(QRectF(cx - 6, cy - 6, 12, 12), 3, 3)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), 8, 8)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(TEXT))
                p.drawEllipse(QPointF(cx, cy), 4, 4)
        elif self.kind == "search":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx - 2, cy - 2), 6.5, 6.5)
            p.drawLine(QPointF(cx + 3, cy + 3), QPointF(cx + 8, cy + 8))
        elif self.kind == "refresh":
            p.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(cx - 8, cy - 8, 16, 16)
            p.drawArc(rect, 60 * 16, 270 * 16)
            p.drawLine(QPointF(cx + 4, cy - 7.5), QPointF(cx + 8.5, cy - 7.5))
            p.drawLine(QPointF(cx + 8.5, cy - 7.5), QPointF(cx + 8.5, cy - 12))


# ── Dashboard window ─────────────────────────────────────────────────────

class AnalyticsDashboard(QWidget):
    trigger_toggle = pyqtSignal()
    trigger_show = pyqtSignal()
    trigger_record_toggle = pyqtSignal()
    trigger_search_toggle = pyqtSignal()
    trigger_refresh = pyqtSignal()
    trigger_recording_state = pyqtSignal(bool)

    HEADER_H = 52  # draggable strip height (px, inside outer margin)

    def __init__(self, storage_manager):
        super().__init__()
        self.storage_manager = storage_manager
        self.is_playing = False
        self._drag_position = None
        self._init_window()
        self._build_ui()
        self.refresh_data()
        self.trigger_toggle.connect(self.toggle_visibility)
        self.trigger_show.connect(self.show_dashboard)
        self.trigger_refresh.connect(self.refresh_data)
        self.trigger_recording_state.connect(self.set_recording_state)

    def _init_window(self):
        self.setWindowTitle("Voice to Type")
        self.resize(1040, 720)
        self.setMinimumSize(900, 620)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # ── UI construction ──
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        self.chassis = QFrame()
        self.chassis.setObjectName("Chassis")
        self.chassis.setStyleSheet(f"""
            QFrame#Chassis {{ background:{BG}; border-radius:20px; border:1px solid rgba(0,0,0,0.10); }}
            QLabel, QPushButton {{ font-family:{FONT_STACK}; }}
            QFrame#Panel {{ background:{PANEL}; border-radius:20px; border:1px solid rgba(0,0,0,0.05); }}
            QFrame#Card {{ background:{CARD}; border-radius:16px; }}
            QScrollArea {{ border:none; background:transparent; }}
            QScrollArea > QWidget > QWidget {{ background:transparent; }}
            QScrollBar:vertical {{ background:transparent; width:8px; margin:2px; }}
            QScrollBar::handle:vertical {{ background:rgba(0,0,0,0.16); border-radius:3px; min-height:30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 10)
        self.chassis.setGraphicsEffect(shadow)
        outer.addWidget(self.chassis)

        root = QVBoxLayout(self.chassis)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_titlebar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 14, 14)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_panel(), stretch=1)
        root.addLayout(body, stretch=1)

    def _build_titlebar(self):
        bar = QWidget()
        bar.setFixedHeight(self.HEADER_H - 16)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(8)
        for color, hover, action in (("#ff5f57", "#e0443e", self.hide),
                                     ("#febc2e", "#dea123", self.showMinimized),
                                     ("#28c840", "#1fa833", self._toggle_maximize)):
            b = QPushButton()
            b.setFixedSize(12, 12)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton {{ background:{color}; border:1px solid rgba(0,0,0,0.12); "
                            f"border-radius:6px; }} QPushButton:hover {{ background:{hover}; }}")
            b.clicked.connect(action)
            lay.addWidget(b)
        lay.addStretch()

        self.status_pill = QLabel("● Ready")
        self.status_pill.setFixedHeight(22)
        self._style_status(False)
        lay.addWidget(self.status_pill, alignment=Qt.AlignmentFlag.AlignVCenter)
        return bar

    def _style_status(self, recording):
        if recording:
            self.status_pill.setText("● Recording")
            self.status_pill.setStyleSheet(
                f"background:#FBE3E1; color:{RED}; font-size:11px; font-weight:600; "
                "border-radius:10px; padding:3px 10px;")
        else:
            self.status_pill.setText("● Ready")
            self.status_pill.setStyleSheet(
                f"background:{GREEN_BG}; color:{GREEN_FG}; font-size:11px; font-weight:600; "
                "border-radius:10px; padding:3px 10px;")

    def _side_btn(self, kind, tip, slot, active=False):
        b = SideIcon(kind, tip, active)
        if slot:
            b.clicked.connect(slot)
        return b

    def _build_sidebar(self):
        side = QWidget()
        side.setFixedWidth(68)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 4, 14, 8)
        lay.setSpacing(6)
        lay.addWidget(LogoWidget(), alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)
        lay.addWidget(self._side_btn("insights", "Insights", None, active=True))
        self.record_btn = self._side_btn("record", "Start / stop recording", self.trigger_record_toggle.emit)
        lay.addWidget(self.record_btn)
        lay.addWidget(self._side_btn("search", "Search history", self.trigger_search_toggle.emit))
        lay.addStretch()
        lay.addWidget(self._side_btn("refresh", "Refresh", self.refresh_data))
        return side

    def _build_panel(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(36, 26, 36, 24)
        lay.setSpacing(14)

        title = QLabel("Insights")
        title.setStyleSheet(f"color:{TEXT}; font-size:20px; font-weight:600;")
        lay.addWidget(title)

        # Tabs
        tabs = QHBoxLayout()
        tabs.setSpacing(22)
        self.tab_group = QButtonGroup(self)
        self.stack = QStackedWidget()
        for i, name in enumerate(["Your Usage", "Your Voice", "History"]):
            t = QPushButton(name)
            t.setCheckable(True)
            t.setChecked(i == 0)
            t.setCursor(Qt.CursorShape.PointingHandCursor)
            t.setStyleSheet(f"""
                QPushButton {{ background:transparent; border:none; border-bottom:2px solid transparent;
                               color:{MUTED}; font-size:14px; padding:6px 0; }}
                QPushButton:checked {{ color:{TEXT}; border-bottom:2px solid {TEXT}; }}
                QPushButton:hover:!checked {{ color:{TEXT}; }}
            """)
            self.tab_group.addButton(t, i)
            tabs.addWidget(t)
        tabs.addStretch()
        self.tab_group.idClicked.connect(self.stack.setCurrentIndex)
        lay.addLayout(tabs)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background:rgba(0,0,0,0.08);")
        lay.addWidget(divider)

        self.stack.addWidget(self._scrollable(self._build_usage_page()))
        self.stack.addWidget(self._scrollable(self._build_voice_page()))
        self.stack.addWidget(self._build_history_page())
        lay.addWidget(self.stack, stretch=1)
        return panel

    def _scrollable(self, widget):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(widget)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        return sa

    def _card(self):
        c = QFrame()
        c.setObjectName("Card")
        return c

    def _caption(self, text):
        l = QLabel(text)
        l.setStyleSheet(f"color:{MUTED}; font-size:10px; font-weight:600; background:transparent;")
        return l

    def _big(self, text, px=34):
        l = QLabel(text)
        l.setStyleSheet(f"color:{TEXT}; font-size:{px}px; font-weight:600; background:transparent;")
        return l

    # ── Your Usage ──
    def _build_usage_page(self):
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 8, 6, 8)
        grid.setSpacing(14)

        # Pace gauge
        c = self._card()
        v = QVBoxLayout(c)
        v.setContentsMargins(18, 16, 18, 16)
        self.gauge = GaugeWidget("WORDS PER MINUTE")
        v.addWidget(self.gauge)
        grid.addWidget(c, 0, 0)

        # Time saved
        c = self._card()
        v = QVBoxLayout(c)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(6)
        self.lbl_time_saved_val = self._big("0 min")
        v.addWidget(self.lbl_time_saved_val)
        v.addWidget(self._caption("TIME SAVED VS TYPING"))
        v.addStretch()
        self.lbl_time_saved_sub = QLabel("")
        self.lbl_time_saved_sub.setStyleSheet(f"color:{TEXT}; font-size:12px; background:transparent;")
        self.lbl_sessions_val = QLabel("0")  # kept for API/tests; rendered in the line below
        self.lbl_sessions_val.setStyleSheet(f"color:{TEXT}; font-size:12px; background:transparent;")
        v.addWidget(self.lbl_time_saved_sub)
        v.addWidget(self.lbl_sessions_val)
        grid.addWidget(c, 0, 1)

        # Total words
        c = self._card()
        v = QVBoxLayout(c)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.addStretch()
        self.lbl_today_pill = QLabel("+0 today")
        self.lbl_today_pill.setStyleSheet(
            f"background:{GREEN_BG}; color:{GREEN_FG}; font-size:11px; font-weight:600; "
            "border-radius:9px; padding:2px 9px;")
        top.addWidget(self.lbl_today_pill)
        v.addLayout(top)
        self.lbl_total_words = self._big("0", 38)
        v.addWidget(self.lbl_total_words)
        v.addWidget(self._caption("TOTAL WORDS DICTATED"))
        self.lbl_words_sub = QLabel("")
        self.lbl_words_sub.setStyleSheet(f"color:{TEXT}; font-size:13px; background:transparent;")
        v.addWidget(self.lbl_words_sub)
        v.addStretch()
        self.milestone_bar = QProgressBar()
        self.milestone_bar.setFixedHeight(8)
        self.milestone_bar.setTextVisible(False)
        self.milestone_bar.setRange(0, 1000)
        self.milestone_bar.setStyleSheet(f"""
            QProgressBar {{ background:{TRACK}; border-radius:4px; border:none; }}
            QProgressBar::chunk {{ background:{TEAL}; border-radius:4px; }}
        """)
        v.addWidget(self.milestone_bar)
        self.lbl_milestone = QLabel("")
        self.lbl_milestone.setStyleSheet(f"color:{MUTED}; font-size:11px; background:transparent;")
        v.addWidget(self.lbl_milestone)
        grid.addWidget(c, 0, 2)

        # Desktop usage
        c = self._card()
        v = QVBoxLayout(c)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        head = QHBoxLayout()
        t = QLabel("Desktop usage")
        t.setStyleSheet(f"color:{TEXT}; font-size:18px; font-weight:600; background:transparent;")
        head.addWidget(t)
        head.addStretch()
        self.lbl_apps_total = self._caption("TOTAL APPS USED | 0")
        head.addWidget(self.lbl_apps_total)
        v.addLayout(head)
        self.apps_layout = QVBoxLayout()
        self.apps_layout.setSpacing(8)
        v.addLayout(self.apps_layout)
        v.addStretch()
        grid.addWidget(c, 1, 0, 1, 1)

        # Streak
        c = self._card()
        v = QVBoxLayout(c)
        v.setContentsMargins(22, 18, 22, 14)
        v.setSpacing(8)
        head = QHBoxLayout()
        self.lbl_streak = QLabel("0 day streak")
        self.lbl_streak.setStyleSheet(f"color:{TEXT}; font-size:18px; font-weight:600; background:transparent;")
        head.addWidget(self.lbl_streak)
        head.addStretch()
        self.lbl_longest = self._caption("LONGEST STREAK | 0 DAYS")
        head.addWidget(self.lbl_longest)
        v.addLayout(head)
        self.heatmap = HeatmapWidget()
        v.addWidget(self.heatmap, stretch=1)
        grid.addWidget(c, 1, 1, 1, 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(0, 0)
        grid.setRowStretch(1, 1)
        grid.setColumnMinimumWidth(0, 250)
        return page

    # ── Your Voice ──
    def _build_voice_page(self):
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 8, 6, 8)
        grid.setSpacing(14)

        def stat_card(caption):
            c = self._card()
            v = QVBoxLayout(c)
            v.setContentsMargins(20, 18, 20, 16)
            val = self._big("0")
            v.addWidget(val)
            v.addWidget(self._caption(caption))
            v.addStretch()
            return c, val

        c, self.lbl_voice_avg = stat_card("AVG WORDS PER DICTATION")
        grid.addWidget(c, 0, 0)
        c, self.lbl_voice_longest = stat_card("LONGEST DICTATION (WORDS)")
        grid.addWidget(c, 0, 1)
        c, self.lbl_voice_time = stat_card("TOTAL SPEAKING TIME")
        grid.addWidget(c, 0, 2)

        c = self._card()
        v = QVBoxLayout(c)
        v.setContentsMargins(22, 18, 22, 14)
        t = QLabel("Last 7 days")
        t.setStyleSheet(f"color:{TEXT}; font-size:16px; font-weight:600; background:transparent;")
        v.addWidget(t)
        self.chart_widget = BarChartWidget(label_every=1, show_values=True)
        v.addWidget(self.chart_widget, stretch=1)
        grid.addWidget(c, 1, 0, 1, 3)

        c = self._card()
        v = QVBoxLayout(c)
        v.setContentsMargins(22, 18, 22, 14)
        t = QLabel("When you dictate")
        t.setStyleSheet(f"color:{TEXT}; font-size:16px; font-weight:600; background:transparent;")
        v.addWidget(t)
        self.hour_chart = BarChartWidget(label_every=3, show_values=False)
        v.addWidget(self.hour_chart, stretch=1)
        grid.addWidget(c, 2, 0, 1, 3)

        for col in range(3):
            grid.setColumnStretch(col, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)
        return page

    # ── History ──
    def _build_history_page(self):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        host = QWidget()
        self.recent_items_layout = QVBoxLayout(host)
        self.recent_items_layout.setContentsMargins(0, 8, 6, 8)
        self.recent_items_layout.setSpacing(8)
        self.recent_items_layout.addStretch()
        sa.setWidget(host)
        return sa

    # ── State ──
    def set_recording_state(self, is_recording: bool):
        self._style_status(is_recording)
        self.record_btn.set_recording(is_recording)

    # ── Data ──
    MILESTONES = [1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000]

    def refresh_data(self):
        s = self.storage_manager
        summary = s.get_analytics_summary()
        daily7 = s.get_daily_activity(days=7)
        heat = s.get_daily_activity(days=HeatmapWidget.WEEKS * 7)
        top_apps = s.get_top_apps(limit=5)
        recent = s.get_recent_sessions(limit=30)
        voice = s.get_voice_stats()
        longest = s.get_longest_streak()

        total_words = summary.get("total_words", 0)

        self.gauge.set_value(summary.get("speaking_wpm", 0) if total_words else 0)
        self.lbl_time_saved_val.setText(_fmt_duration(summary.get("time_saved_min", 0.0)))
        self.lbl_time_saved_sub.setText(f"↑ {summary.get('speed_multiplier', 0)}× faster than typing")
        sessions = summary.get("total_sessions", 0)
        self.lbl_sessions_val.setText(f"{sessions:,} dictation{'s' if sessions != 1 else ''}")

        self.lbl_total_words.setText(f"{total_words:,}")
        self.lbl_today_pill.setText(f"+{summary.get('today_words', 0):,} today")
        if total_words >= 80_000:
            self.lbl_words_sub.setText(f"You've written {total_words // 80_000} complete book"
                                       f"{'s' if total_words // 80_000 != 1 else ''}!")
        elif total_words > 0:
            self.lbl_words_sub.setText(f"About {max(1, round(total_words / 500))} pages of writing.")
        else:
            self.lbl_words_sub.setText("Start dictating to see this grow.")
        nxt = next((m for m in self.MILESTONES if m > total_words), self.MILESTONES[-1])
        self.milestone_bar.setValue(int(min(1.0, total_words / nxt) * 1000))
        self.lbl_milestone.setText(f"{total_words:,} / {nxt:,} words to next milestone")

        streak = summary.get("streak_days", 0)
        self.lbl_streak.setText(f"{streak} day streak")
        self.lbl_longest.setText(f"LONGEST STREAK | {longest} DAY{'S' if longest != 1 else ''}")
        self.heatmap.set_data(heat)

        self._populate_top_apps(top_apps)

        today = datetime.now().strftime("%Y-%m-%d")
        self.chart_widget.set_data([
            {"label": d["day_label"], "value": d["words"], "highlight": d["date"] == today} for d in daily7])
        cur_hour = datetime.now().hour
        self.hour_chart.set_data([
            {"label": f"{h:02d}", "value": voice["hourly"][h], "highlight": h == cur_hour} for h in range(24)])
        self.lbl_voice_avg.setText(f"{voice['avg_words']:,}")
        self.lbl_voice_longest.setText(f"{voice['longest_words']:,}")
        self.lbl_voice_time.setText(_fmt_duration(voice["total_duration_sec"] / 60.0))

        self._populate_recent_sessions(recent)

    def _clear(self, layout, keep_stretch=False):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _populate_top_apps(self, top_apps):
        self._clear(self.apps_layout)
        self.lbl_apps_total.setText(f"TOTAL APPS USED | {len(top_apps)}")
        if not top_apps:
            e = QLabel("No application data yet")
            e.setStyleSheet(f"color:{MUTED}; font-size:12px; background:transparent;")
            self.apps_layout.addWidget(e)
            return
        for i, app in enumerate(top_apps):
            self.apps_layout.addWidget(AppBarRow(
                app.get("app_name", "General"), app.get("percent", 0.0), app.get("words", 0),
                app.get("sessions", 0), APP_ICON_COLORS[i % len(APP_ICON_COLORS)]))

    def _populate_recent_sessions(self, recent):
        self._clear(self.recent_items_layout)
        if not recent:
            e = QLabel("No dictations yet. Trigger a recording to get started.")
            e.setStyleSheet(f"color:{MUTED}; font-size:13px; padding:16px;")
            self.recent_items_layout.addWidget(e)
        for record in recent:
            row = RecentSessionRow(record)
            row.play_audio_signal.connect(self._play_audio)
            self.recent_items_layout.addWidget(row)
        self.recent_items_layout.addStretch()

    def _play_audio(self, audio_path):
        if not audio_path or not os.path.exists(audio_path):
            return

        def worker():
            try:
                self.is_playing = True
                sr, data = wavfile.read(audio_path)
                sd.play(data, sr)
                sd.wait()
            except Exception as e:
                logger.error(f"Error playing audio in dashboard: {e}")
            finally:
                self.is_playing = False

        threading.Thread(target=worker, daemon=True).start()

    # ── Window behaviour ──
    def _toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show_dashboard()

    def show_dashboard(self):
        self.refresh_data()
        self.show()
        self.raise_()
        self.activateWindow()

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
            self.hide()
        else:
            super().keyPressEvent(event)


if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    from src.core.storage import StorageManager
    app = QApplication.instance() or QApplication(sys.argv)
    dashboard = AnalyticsDashboard(StorageManager())
    dashboard.show()
    sys.exit(app.exec())
