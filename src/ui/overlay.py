"""
Apple Liquid Glass Overlay — iOS 26 style.

Everything is painted in a single paintEvent pass — no child widgets,
no z-order issues, no opaque backgrounds eating the glass effect.

The waveform bars are driven by real microphone RMS amplitude via the
amplitude_update signal (thread-safe Qt signal/slot from audio thread).
"""

import math
from PyQt6.QtWidgets import QWidget, QApplication, QGraphicsOpacityEffect
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve,
    QRectF
)
from PyQt6.QtGui import (
    QColor, QPainter, QBrush, QPen, QLinearGradient,
    QRadialGradient, QPainterPath, QFont
)


class GlassOverlay(QWidget):
    """
    Liquid Glass pill — single-pass custom paint, voice-reactive waveform.
    """

    state_changed = pyqtSignal(str)
    trigger_start = pyqtSignal()
    trigger_stop  = pyqtSignal()
    amplitude_update = pyqtSignal(float)

    # ── Geometry ──
    PILL_W = 260
    PILL_H = 60
    PAD    = 24          # bleed area for shadow

    # ── Waveform config ──
    NUM_BARS   = 7
    BAR_W      = 4.0
    BAR_GAP    = 3.5
    BAR_MAX_H  = 26.0
    BAR_MIN_H  = 4.0
    BAR_IDLE_H = 5.0

    # Per-bar smoothing: centre bars react fastest
    _ATTACK = [0.10, 0.14, 0.20, 0.28, 0.20, 0.14, 0.10]
    _DECAY  = [0.04, 0.06, 0.08, 0.10, 0.08, 0.06, 0.04]
    # Per-bar amplitude scaling: centre gets full signal, edges are damped
    _AMP_SCALE = [0.50, 0.70, 0.88, 1.00, 0.88, 0.70, 0.50]

    def __init__(self):
        super().__init__()
        self.state = "IDLE"

        # Waveform state
        self._bar_heights = [self.BAR_IDLE_H] * self.NUM_BARS
        self._amplitude = 0.0
        self._idle_phase = 0.0

        # Scale animation state
        self._scale = 1.0

        # Shimmer phase for specular
        self._shimmer = 0.0

        self._init_window()
        self._init_animations()

        self.trigger_start.connect(self.start_recording)
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
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.PILL_W + self.PAD * 2,
                          self.PILL_H + self.PAD * 2)

    def _init_animations(self):
        # Opacity
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_in = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_in.setDuration(300)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_out = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_out.setDuration(200)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(self._on_hidden)

        # Master animation timer (~60 fps)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)

        # Scale spring timer
        self._scale = 0.90
        self._scale_timer = QTimer(self)
        self._scale_timer.timeout.connect(self._tick_scale)

    # ──────────────────────────────────────────────────────────────
    # Font
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _font(size_pt: float, bold: bool = False) -> QFont:
        for family in ("Segoe UI Variable Display", "Segoe UI",
                       "SF Pro Display", "Helvetica Neue", "Arial"):
            f = QFont(family)
            if f.exactMatch() or family in ("Segoe UI", "Arial"):
                f.setPointSizeF(size_pt)
                f.setBold(bold)
                f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
                return f
        f = QFont()
        f.setPointSizeF(size_pt)
        f.setBold(bold)
        return f

    # ──────────────────────────────────────────────────────────────
    # Animation ticks
    # ──────────────────────────────────────────────────────────────

    def _on_amplitude(self, rms: float):
        """Thread-safe slot. Receives raw RMS from audio thread."""
        self._amplitude = min(1.0, rms * 15.0)

    def _tick(self):
        """Master tick — updates waveform bars + shimmer."""
        amp = self._amplitude
        self._idle_phase += 0.07
        self._shimmer = (self._shimmer + 0.015) % 1.0

        for i in range(self.NUM_BARS):
            # Target height based on amplitude + idle drift
            bar_amp = amp * self._AMP_SCALE[i]
            idle = self.BAR_IDLE_H + 2.0 * math.sin(self._idle_phase + i * 0.9)
            target = max(idle, self.BAR_MIN_H + (self.BAR_MAX_H - self.BAR_MIN_H) * bar_amp)
            target = min(target, self.BAR_MAX_H)

            cur = self._bar_heights[i]
            k = self._ATTACK[i] if target > cur else self._DECAY[i]
            self._bar_heights[i] = cur + (target - cur) * k

        self.update()

    def _tick_scale(self):
        self._scale += (1.0 - self._scale) * 0.20
        if abs(self._scale - 1.0) < 0.001:
            self._scale = 1.0
            self._scale_timer.stop()
        self.update()

    def _on_hidden(self):
        self.hide()
        self._tick_timer.stop()

    # ──────────────────────────────────────────────────────────────
    # Paint — single-pass, everything in one go
    # ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        P = self.PAD
        W, H = self.PILL_W, self.PILL_H
        R = H / 2.0

        # Scale transform around pill centre
        cx, cy = P + W / 2.0, P + H / 2.0
        p.translate(cx, cy)
        p.scale(self._scale, self._scale)
        p.translate(-cx, -cy)

        pill = QRectF(P, P, W, H)
        pill_path = QPainterPath()
        pill_path.addRoundedRect(pill, R, R)

        # ── 1  Outer shadow ──────────────────────────────────────
        # Soft, slightly offset downward — like real glass on a surface
        for i in range(6, 0, -1):
            s = i * 2.2
            a = max(0, int(14 - i * 2))
            sr = pill.adjusted(-s, -s + 1.5, s, s + 1.5)
            sp = QPainterPath()
            sp.addRoundedRect(sr, R + s, R + s)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, a))
            p.drawPath(sp)

        # ── 2  Glass fill ────────────────────────────────────────
        # Semi-opaque frosted white — visible on ANY background.
        # This is the key: high enough alpha to read as "glass",
        # not so high it looks like a solid card.
        fill = QLinearGradient(P, P, P, P + H)
        fill.setColorAt(0.0, QColor(255, 255, 255, 78))   # brighter top
        fill.setColorAt(0.4, QColor(245, 248, 255, 60))
        fill.setColorAt(1.0, QColor(230, 235, 248, 65))   # slightly cooler bottom
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fill))
        p.drawPath(pill_path)

        # ── 3  Inner brightness — radial lens glow ───────────────
        # Centred slightly above-middle to simulate overhead lighting
        lens = QRadialGradient(P + W * 0.38, P + H * 0.35, W * 0.45)
        lens.setColorAt(0.0, QColor(255, 255, 255, 40))
        lens.setColorAt(0.6, QColor(255, 255, 255, 12))
        lens.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(lens))
        p.drawPath(pill_path)

        # ── 4  Top specular highlight ────────────────────────────
        # Bright white band across top edge — the hallmark of glass.
        # Gently pulses via shimmer.
        sa = int(100 + 25 * math.sin(self._shimmer * 2 * math.pi))
        spec = QLinearGradient(P + W * 0.12, P, P + W * 0.88, P)
        spec.setColorAt(0.0,  QColor(255, 255, 255, 0))
        spec.setColorAt(0.2,  QColor(255, 255, 255, sa))
        spec.setColorAt(0.5,  QColor(255, 255, 255, int(sa * 1.15)))
        spec.setColorAt(0.8,  QColor(255, 255, 255, sa))
        spec.setColorAt(1.0,  QColor(255, 255, 255, 0))

        clip_top = QPainterPath()
        clip_top.addRoundedRect(
            pill.adjusted(2, 1, -2, -H * 0.58), R - 2, R - 2
        )
        p.save()
        p.setClipPath(clip_top)
        p.setBrush(QBrush(spec))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(pill_path)
        p.restore()

        # ── 5  Bottom inset shadow ───────────────────────────────
        bot = QLinearGradient(P, P + H * 0.72, P, P + H)
        bot.setColorAt(0.0, QColor(0, 0, 0, 0))
        bot.setColorAt(1.0, QColor(0, 0, 0, 14))
        p.save()
        p.setClipPath(pill_path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bot))
        p.drawPath(pill_path)
        p.restore()

        # ── 6  Border — thin gradient stroke ─────────────────────
        # Brighter on top, fading on bottom — real glass edge catching light
        bd = QLinearGradient(P, P, P, P + H)
        bd.setColorAt(0.0, QColor(255, 255, 255, 110))
        bd.setColorAt(0.35, QColor(255, 255, 255, 55))
        bd.setColorAt(1.0, QColor(255, 255, 255, 22))
        bp = QPainterPath()
        bp.addRoundedRect(pill.adjusted(0.5, 0.5, -0.5, -0.5),
                          R - 0.5, R - 0.5)
        p.setPen(QPen(QBrush(bd), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(bp)

        # ── 7  Waveform bars ─────────────────────────────────────
        self._paint_waveform(p, P, W, H)

        # ── 8  Text ──────────────────────────────────────────────
        self._paint_text(p, P, W, H)

        p.end()

    # ── Waveform painting ────────────────────────────────────────

    def _paint_waveform(self, p: QPainter, pad: int, pw: int, ph: int):
        total_w = self.NUM_BARS * self.BAR_W + (self.NUM_BARS - 1) * self.BAR_GAP
        # Position: left side of pill, vertically centred
        wave_x = pad + 20
        wave_cy = pad + ph / 2.0

        for i, h in enumerate(self._bar_heights):
            x = wave_x + i * (self.BAR_W + self.BAR_GAP)
            y = wave_cy - h / 2.0

            bar = QPainterPath()
            bar.addRoundedRect(QRectF(x, y, self.BAR_W, h), 2.0, 2.0)

            # White gradient — brighter at top, slightly translucent at bottom
            g = QLinearGradient(x, y, x, y + h)
            g.setColorAt(0.0, QColor(255, 255, 255, 245))
            g.setColorAt(1.0, QColor(255, 255, 255, 170))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawPath(bar)

    # ── Text painting ────────────────────────────────────────────

    def _paint_text(self, p: QPainter, pad: int, pw: int, ph: int):
        total_wave_w = self.NUM_BARS * self.BAR_W + (self.NUM_BARS - 1) * self.BAR_GAP
        text_x = pad + 20 + total_wave_w + 16   # after waveform + gap
        text_w = pw - (text_x - pad) - 16

        if self.state == "RECORDING":
            title = "Listening…"
            subtitle = "Tap hotkey to stop"
        else:
            title = "Voice to Type"
            subtitle = "Ready"

        # Title
        p.setFont(self._font(11.5, bold=True))
        p.setPen(QColor(255, 255, 255, 240))
        title_rect = QRectF(text_x, pad + 10, text_w, 20)
        p.drawText(title_rect,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   title)

        # Subtitle
        p.setFont(self._font(9.0, bold=False))
        p.setPen(QColor(255, 255, 255, 140))
        sub_rect = QRectF(text_x, pad + 30, text_w, 16)
        p.drawText(sub_rect,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   subtitle)

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def start_recording(self):
        self.state = "RECORDING"

        # Position: bottom-centre of screen
        try:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = screen.height() - self.height() - 56
            self.move(x, y)
        except Exception:
            self.move(600, 900)

        # Reset waveform
        self._bar_heights = [self.BAR_IDLE_H] * self.NUM_BARS
        self._amplitude = 0.0
        self._idle_phase = 0.0

        # Start animations
        self._scale = 0.86
        self._scale_timer.start(16)
        self._tick_timer.start(16)

        self._fade_out.stop()
        self._opacity.setOpacity(0.0)
        self.show()
        self._fade_in.start()
        self.state_changed.emit(self.state)

    def stop_recording(self):
        self.state = "IDLE"
        self._amplitude = 0.0
        self._scale_timer.stop()
        self._fade_in.stop()
        self._fade_out.start()
        self.state_changed.emit(self.state)
