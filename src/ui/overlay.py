"""
Wispr Flow Bar Overlay — Compact floating voice recording & transcribing capsule.

Single-pass QPainter widget with zero child widgets, smooth spring scale + opacity
animations, 11-bar voice-reactive waveform, live elapsed timer, and a
"Transcribing…" transition state with active-app context badge.

Supports both the Warm Paper theme (default, matching the Insights Dashboard)
and the Obsidian Ink theme (via FLOW_BAR_THEME=ink in .env).
"""

import os
import math
import time
from PyQt6.QtWidgets import QWidget, QApplication, QGraphicsOpacityEffect
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve,
    QRectF, QPointF
)
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QPainterPath, QFont
)


class GlassOverlay(QWidget):
    """
    Wispr Flow Bar capsule — single-pass custom paint, 11-bar voice-reactive waveform,
    live elapsed timer, and smooth "Transcribing…" state.
    """

    state_changed = pyqtSignal(str)
    trigger_start = pyqtSignal()
    trigger_transcribing = pyqtSignal(str)
    trigger_stop = pyqtSignal()
    amplitude_update = pyqtSignal(float)

    # ── Geometry ──
    PILL_W = 240
    PILL_H = 46
    PAD    = 20          # bleed area for multi-layer drop shadow

    # ── Waveform config (11 fine capsule bars) ──
    NUM_BARS   = 11
    BAR_W      = 3.4
    BAR_GAP    = 4.2
    BAR_MAX_H  = 26.0
    BAR_MIN_H  = 4.5
    BAR_IDLE_H = 5.5

    _ATTACK = [0.10, 0.13, 0.17, 0.22, 0.27, 0.30, 0.27, 0.22, 0.17, 0.13, 0.10]
    _DECAY  = [0.05, 0.06, 0.07, 0.09, 0.10, 0.11, 0.10, 0.09, 0.07, 0.06, 0.05]
    _AMP_SCALE = [0.38, 0.52, 0.68, 0.84, 0.95, 1.00, 0.95, 0.84, 0.68, 0.52, 0.38]

    def __init__(self, theme: str | None = None):
        super().__init__()
        self.state = "IDLE"
        self.theme = (theme or os.getenv("FLOW_BAR_THEME", "paper")).lower()
        self._context_app = "General"

        # Waveform & timer state
        self._bar_heights = [self.BAR_IDLE_H] * self.NUM_BARS
        self._amplitude = 0.0
        self._idle_phase = 0.0
        self._pulse_phase = 0.0
        self._record_start_ts = 0.0
        self._scale = 1.0

        self._init_window()
        self._init_animations()

        self.trigger_start.connect(self.start_recording)
        self.trigger_transcribing.connect(self.start_transcribing)
        self.trigger_stop.connect(self.stop_recording)
        self.amplitude_update.connect(self._on_amplitude)

    # ──────────────────────────────────────────────────────────────
    # Init
    # ──────────────────────────────────────────────────────────────

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.NoDropShadowWindowHint |
            Qt.WindowType.WindowDoesNotAcceptFocus |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus)
        self.setFixedSize(self.PILL_W + self.PAD * 2,
                          self.PILL_H + self.PAD * 2)

    def _init_animations(self):
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_in = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_in.setDuration(220)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_out = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_out.setDuration(180)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(self._on_hidden)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)

        self._scale = 0.90
        self._scale_timer = QTimer(self)
        self._scale_timer.timeout.connect(self._tick_scale)

    @staticmethod
    def _font(px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        f = QFont("Inter")
        f.setPixelSize(px)
        f.setWeight(weight)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return f

    # ──────────────────────────────────────────────────────────────
    # Animation ticks
    # ──────────────────────────────────────────────────────────────

    def _on_amplitude(self, rms: float):
        """Thread-safe slot receiving raw RMS from the audio thread."""
        self._amplitude = min(1.0, rms * 16.0)

    def _tick(self):
        amp = self._amplitude
        self._idle_phase += 0.09
        self._pulse_phase = (self._pulse_phase + 0.06) % (2.0 * math.pi)

        for i in range(self.NUM_BARS):
            bar_amp = amp * self._AMP_SCALE[i]
            idle = self.BAR_IDLE_H + 1.8 * math.sin(self._idle_phase + i * 0.65)
            target = max(idle, self.BAR_MIN_H + (self.BAR_MAX_H - self.BAR_MIN_H) * bar_amp)
            target = min(target, self.BAR_MAX_H)

            cur = self._bar_heights[i]
            k = self._ATTACK[i] if target > cur else self._DECAY[i]
            self._bar_heights[i] = cur + (target - cur) * k

        self.update()

    def _tick_scale(self):
        self._scale += (1.0 - self._scale) * 0.22
        if abs(self._scale - 1.0) < 0.001:
            self._scale = 1.0
            self._scale_timer.stop()
        self.update()

    def _on_hidden(self):
        self.hide()
        self._tick_timer.stop()

    def _format_elapsed(self) -> str:
        if self._record_start_ts <= 0:
            return "0:00"
        secs = max(0, int(time.time() - self._record_start_ts))
        return f"{secs // 60}:{secs % 60:02d}"

    # ──────────────────────────────────────────────────────────────
    # Single-pass Paint
    # ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        P = self.PAD
        W, H = self.PILL_W, self.PILL_H
        R = H / 2.0

        cx, cy = P + W / 2.0, P + H / 2.0
        p.translate(cx, cy)
        p.scale(self._scale, self._scale)
        p.translate(-cx, -cy)

        pill = QRectF(P, P, W, H)

        # 1. Soft multi-layer ambient shadow
        for i in range(7, 0, -1):
            s = i * 2.1
            alpha = max(0, int(18 - i * 2.2))
            sr = pill.adjusted(-s, -s + 2.5, s, s + 2.5)
            sp = QPainterPath()
            sp.addRoundedRect(sr, R + s, R + s)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(27, 27, 26, alpha))
            p.drawPath(sp)

        # 2. Palette selection (Warm Paper vs Obsidian Ink)
        if self.theme == "ink":
            bg_col = QColor("#1B1B1A")
            border_col = QColor(255, 255, 255, 36)
            text_col = QColor("#F6F4EF")
            muted_col = QColor("#A09C93")
            chip_bg = QColor(255, 255, 255, 22)
            wave_primary = QColor("#8CC5B8")
            wave_secondary = QColor("#F6F4EF")
            dot_col = QColor("#3F9C8B")
        else:
            bg_col = QColor("#FCFBF9")
            border_col = QColor(27, 27, 26, 30)
            text_col = QColor("#1B1B1A")
            muted_col = QColor("#7B776E")
            chip_bg = QColor("#F3F1EC")
            wave_primary = QColor("#1F6B5E")
            wave_secondary = QColor("#3F9C8B")
            dot_col = QColor("#1F6B5E")

        pill_path = QPainterPath()
        pill_path.addRoundedRect(pill, R, R)
        p.setPen(QPen(border_col, 1.2))
        p.setBrush(bg_col)
        p.drawPath(pill_path)

        if self.state == "TRANSCRIBING":
            self._paint_transcribing(p, P, W, H, cy, text_col, muted_col, chip_bg, dot_col)
        else:
            self._paint_recording(p, P, W, H, cy, muted_col, chip_bg, wave_primary, wave_secondary)

        p.end()

    def _paint_recording(self, p: QPainter, pad: int, pw: int, ph: int, cy: float,
                         muted_col: QColor, chip_bg: QColor,
                         wave_primary: QColor, wave_secondary: QColor):
        # Left: Cancel '✕' chip
        cx_left = pad + 23
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(chip_bg)
        p.drawEllipse(QPointF(cx_left, cy), 14, 14)

        pen_x = QPen(muted_col, 1.7)
        pen_x.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_x)
        p.drawLine(QPointF(cx_left - 4, cy - 4), QPointF(cx_left + 4, cy + 4))
        p.drawLine(QPointF(cx_left + 4, cy - 4), QPointF(cx_left - 4, cy + 4))

        # Center: 11-bar organic waveform
        total_wave_w = self.NUM_BARS * self.BAR_W + (self.NUM_BARS - 1) * self.BAR_GAP
        wave_start_x = pad + 50
        for i, bh in enumerate(self._bar_heights):
            bx = wave_start_x + i * (self.BAR_W + self.BAR_GAP)
            by = cy - bh / 2.0
            dist = abs(i - (self.NUM_BARS - 1) / 2.0) / ((self.NUM_BARS - 1) / 2.0)
            col = wave_primary if dist < 0.55 else wave_secondary
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(bx, by, self.BAR_W, bh), self.BAR_W / 2.0, self.BAR_W / 2.0)

        # Elapsed timer
        timer_x = wave_start_x + total_wave_w + 12
        p.setPen(muted_col)
        p.setFont(self._font(12, QFont.Weight.DemiBold))
        p.drawText(
            QRectF(timer_x, pad, 38, ph),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._format_elapsed()
        )

        # Right: Coral-red Stop chip with rounded white square
        cx_right = pad + pw - 23
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E5534B"))
        p.drawEllipse(QPointF(cx_right, cy), 14, 14)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(cx_right - 4.5, cy - 4.5, 9, 9), 2.2, 2.2)

    def _paint_transcribing(self, p: QPainter, pad: int, pw: int, ph: int, cy: float,
                            text_col: QColor, muted_col: QColor,
                            chip_bg: QColor, dot_col: QColor):
        # Left: Pulsing teal indicator dot + breathing halo
        cx_left = pad + 24
        halo_r = 9.5 + 2.5 * math.sin(self._pulse_phase)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(31, 107, 94, 48))
        p.drawEllipse(QPointF(cx_left, cy), halo_r, halo_r)
        p.setBrush(dot_col)
        p.drawEllipse(QPointF(cx_left, cy), 5.5, 5.5)

        # Center: "Transcribing…"
        p.setPen(text_col)
        p.setFont(self._font(13, QFont.Weight.DemiBold))
        p.drawText(
            QRectF(pad + 44, pad, 115, ph),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Transcribing…"
        )

        # Right: Active context app pill badge
        app_label = (self._context_app or "App")[:10]
        tag_rect = QRectF(pad + pw - 74, cy - 11, 60, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(chip_bg)
        p.drawRoundedRect(tag_rect, 11, 11)
        p.setPen(muted_col)
        p.setFont(self._font(10, QFont.Weight.DemiBold))
        p.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, app_label)

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def _position_bottom_center(self):
        try:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = screen.height() - self.height() - 48
            self.move(x, y)
        except Exception:
            self.move(600, 900)

    def start_recording(self):
        self.state = "RECORDING"
        self._record_start_ts = time.time()
        self._position_bottom_center()

        self._bar_heights = [self.BAR_IDLE_H] * self.NUM_BARS
        self._amplitude = 0.0
        self._idle_phase = 0.0

        self._scale = 0.88
        self._scale_timer.start(16)
        self._tick_timer.start(16)

        self._fade_out.stop()
        self._opacity.setOpacity(0.0)
        self.show()
        self._fade_in.start()
        self.state_changed.emit(self.state)

    def start_transcribing(self, app_name: str = "General"):
        """Transitions the Flow Bar from Listening into the 'Transcribing…' state."""
        self._context_app = app_name or "General"
        self.state = "TRANSCRIBING"
        self._amplitude = 0.0
        if not self._tick_timer.isActive():
            self._tick_timer.start(16)
        self.update()
        self.state_changed.emit(self.state)

    def stop_recording(self):
        self.state = "IDLE"
        self._amplitude = 0.0
        self._scale_timer.stop()
        self._fade_in.stop()
        self._fade_out.stop()
        self._tick_timer.stop()
        self.hide()
        self.state_changed.emit(self.state)
