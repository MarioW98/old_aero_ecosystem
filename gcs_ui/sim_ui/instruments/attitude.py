from __future__ import annotations
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from .base import BaseInstrument
from ..core.telemetry import TelemetryData


_BEZEL_COLOR = QColor(40, 40, 45)
_BEZEL_RING_COLOR = QColor(30, 30, 34)
_DIAL_COLOR = QColor(20, 22, 28)
_TICK_MAJOR_COLOR = QColor(220, 220, 220)
_TICK_MINOR_COLOR = QColor(160, 160, 160)
_TICK_MAJOR_WIDTH = 2.0
_TICK_MINOR_WIDTH = 1.0
_SKY_COLOR = QColor(55, 110, 190)
_GROUND_COLOR = QColor(120, 75, 35)
_HORIZON_COLOR = QColor(255, 255, 255)
_PITCH_LADDER_COLOR = QColor(255, 255, 255)
_NEEDLE_COLOR = QColor(255, 255, 255)
_REFERENCE_COLOR = QColor(255, 160, 0)
_AIRCRAFT_SYMBOL_COLOR = QColor(255, 200, 0)
_FONT_SIZE_UNIT = 9


# =============================================================================
# ATTITUDE INDICATOR (semplice)
# =============================================================================

class AttitudeIndicator(BaseInstrument):
    def __init__(self, p, parent=None):
        super().__init__(p, parent)
        self._pitch = 0.0
        self._roll = 0.0

    def update_data(self, d: TelemetryData):
        self._pitch = d.pitch
        self._roll = d.roll
        self.update()

    def paint_background(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BEZEL_COLOR)
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)
        p.setBrush(_DIAL_COLOR)
        p.drawEllipse(QPointF(cx, cy), outer_r - 6, outer_r - 6)

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        radius = min(cx, cy) - 12

        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), radius, radius)
        p.save()
        p.setClipPath(clip)
        p.translate(cx, cy)
        p.rotate(-self._roll)

        ppx = self._pitch * 2.5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_SKY_COLOR)
        p.drawRect(QRectF(-radius * 2, -radius * 2 + ppx, radius * 4, radius * 2))
        p.setBrush(_GROUND_COLOR)
        p.drawRect(QRectF(-radius * 2, ppx, radius * 4, radius * 2))
        p.setPen(QPen(_HORIZON_COLOR, 2))
        p.drawLine(QPointF(-radius, ppx), QPointF(radius, ppx))

        p.setPen(QPen(_PITCH_LADDER_COLOR, 1))
        for deg in [-20, -10, 10, 20]:
            yo = ppx - deg * 2.5
            hw = 20 if deg % 20 == 0 else 14
            p.drawLine(QPointF(-hw, yo), QPointF(hw, yo))
        p.restore()

        p.save()
        p.translate(cx, cy)
        p.setPen(QPen(_AIRCRAFT_SYMBOL_COLOR, 3))
        p.drawLine(QPointF(-28, 0), QPointF(-10, 0))
        p.drawLine(QPointF(10, 0), QPointF(28, 0))
        p.setBrush(_AIRCRAFT_SYMBOL_COLOR)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0, 0), 3, 3)
        p.restore()

        p.save()
        p.translate(cx, cy)
        tri = QPainterPath()
        tri.moveTo(0, -radius + 2)
        tri.lineTo(-5, -radius + 10)
        tri.lineTo(5, -radius + 10)
        tri.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_AIRCRAFT_SYMBOL_COLOR)
        p.drawPath(tri)
        p.restore()

# =============================================================================
# ATTITUDE INDICATOR FULL
# =============================================================================

class AttitudeIndicatorFull(BaseInstrument):
    """
    Orizzonte artificiale completo con:
    - Scala beccheggio (tacche ogni 5°, numeri ogni 10°)
    - Scala rollio (0°, ±10°, ±20°, ±30°, ±45°, ±60°)
    - Puntatore rollio mobile
    - Simbolo aereo fisso
    """

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._pitch = 0.0
        self._roll = 0.0
        self._px_per_deg = 3.0

    def update_data(self, data: TelemetryData):
        self._pitch = data.pitch
        self._roll = data.roll
        self.update()

    def paint_background(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BEZEL_COLOR)
        painter.drawEllipse(QPointF(cx, cy), outer_r, outer_r)
        painter.setBrush(_BEZEL_RING_COLOR)
        painter.drawEllipse(QPointF(cx, cy), outer_r - 4, outer_r - 4)
        dial_r = outer_r - 8
        painter.setBrush(_DIAL_COLOR)
        painter.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        roll_marks = [0, 10, 20, 30, 45, 60]
        tick_r = dial_r - 2
        for angle in roll_marks:
            signs = [1] if angle == 0 else [1, -1]
            for sign in signs:
                deg = angle * sign
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(deg)
                if angle == 0:
                    tick_len, tick_w = 12, _TICK_MAJOR_WIDTH
                elif angle in (10, 20, 30):
                    tick_len, tick_w = 10, _TICK_MINOR_WIDTH
                else:
                    tick_len, tick_w = 12, _TICK_MINOR_WIDTH
                painter.setPen(QPen(_TICK_MAJOR_COLOR, tick_w))
                painter.drawLine(QPointF(0, -tick_r), QPointF(0, -tick_r + tick_len))
                painter.restore()

    def paint_foreground(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4
        dial_r = outer_r - 8
        sphere_r = dial_r - 16
        if sphere_r <= 0:
            return

        painter.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), sphere_r, sphere_r)
        painter.setClipPath(clip)
        painter.translate(cx, cy)
        painter.rotate(-self._roll)

        pitch_offset = self._pitch * self._px_per_deg
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_SKY_COLOR)
        painter.drawRect(QRectF(-sphere_r * 2, -sphere_r * 2 + pitch_offset,
                                sphere_r * 4, sphere_r * 2))
        painter.setBrush(_GROUND_COLOR)
        painter.drawRect(QRectF(-sphere_r * 2, pitch_offset,
                                sphere_r * 4, sphere_r * 2))
        painter.setPen(QPen(_HORIZON_COLOR, 2))
        painter.drawLine(QPointF(-sphere_r, pitch_offset),
                         QPointF(sphere_r, pitch_offset))

        pf = painter.font()
        pf.setPixelSize(_FONT_SIZE_UNIT)
        painter.setFont(pf)
        for deg in range(-30, 35, 5):
            if deg == 0:
                continue
            y_pos = pitch_offset - deg * self._px_per_deg
            if deg % 10 == 0:
                half_w = 30
                draw_number = True
            else:
                half_w = 18
                draw_number = False
            painter.setPen(QPen(_PITCH_LADDER_COLOR, 1))
            painter.drawLine(QPointF(-half_w, y_pos), QPointF(half_w, y_pos))
            if draw_number:
                label = str(abs(deg))
                painter.setPen(_PITCH_LADDER_COLOR)
                painter.drawText(QRectF(-half_w - 22, y_pos - 6, 20, 12),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                 label)
                painter.drawText(QRectF(half_w + 2, y_pos - 6, 20, 12),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 label)
        painter.restore()

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._roll)
        ptr_r = sphere_r + 4
        ptr = QPainterPath()
        ptr.moveTo(0, -ptr_r)
        ptr.lineTo(-6, -ptr_r + 12)
        ptr.lineTo(6, -ptr_r + 12)
        ptr.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_NEEDLE_COLOR)
        painter.drawPath(ptr)
        painter.restore()

        painter.save()
        painter.translate(cx, cy)
        ref_r = sphere_r + 4
        ref = QPainterPath()
        ref.moveTo(0, -ref_r + 14)
        ref.lineTo(-5, -ref_r + 2)
        ref.lineTo(5, -ref_r + 2)
        ref.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_REFERENCE_COLOR)
        painter.drawPath(ref)
        painter.restore()

        painter.save()
        painter.translate(cx, cy)
        painter.setPen(QPen(_AIRCRAFT_SYMBOL_COLOR, 3))
        painter.drawLine(QPointF(-30, 0), QPointF(-12, 0))
        painter.drawLine(QPointF(12, 0), QPointF(30, 0))
        painter.drawLine(QPointF(-30, 0), QPointF(-30, 5))
        painter.drawLine(QPointF(30, 0), QPointF(30, 5))
        painter.setBrush(_AIRCRAFT_SYMBOL_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 3, 3)
        painter.restore()

# =============================================================================
# ATTITUDE INDICATOR SQUARE
# =============================================================================

class AttitudeIndicatorSquare(BaseInstrument):
    """
    Orizzonte artificiale quadrato con comportamento circolare:
    - 0°: orizzonte normale
    - ±180°: orizzonte invertito
    - Linee orizzonte sia a 0° che a 180°
    """

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._pitch = 0.0
        self._roll = 0.0
        self._px_per_deg = 2.5

    def update_data(self, data: TelemetryData):
        self._pitch = data.pitch
        self._roll = data.roll
        self.update()

    def paint_background(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        margin = 4
        corner = 12
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BEZEL_COLOR)
        painter.drawRoundedRect(QRectF(margin, margin, w - 2 * margin, h - 2 * margin),
                                corner, corner)
        m2 = margin + 4
        painter.setBrush(_BEZEL_RING_COLOR)
        painter.drawRoundedRect(QRectF(m2, m2, w - 2 * m2, h - 2 * m2),
                                corner - 2, corner - 2)
        m3 = margin + 8
        painter.setBrush(_DIAL_COLOR)
        painter.drawRoundedRect(QRectF(m3, m3, w - 2 * m3, h - 2 * m3),
                                corner - 4, corner - 4)

    def paint_foreground(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_margin = 12
        dial_w = w - 2 * dial_margin
        dial_h = h - 2 * dial_margin
        if dial_w <= 0 or dial_h <= 0:
            return

        norm_pitch = ((self._pitch + 180.0) % 360.0) - 180.0

        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(dial_margin, dial_margin, dial_w, dial_h), 8, 8)
        painter.setClipPath(clip)
        painter.translate(cx, cy)
        painter.rotate(-self._roll)

        ppd = self._px_per_deg
        pitch_offset = norm_pitch * ppd
        large = max(w, h) * 3
        h0 = pitch_offset
        half_period = 180.0 * ppd
        if norm_pitch >= 0:
            h_sec = h0 - half_period
        else:
            h_sec = h0 + half_period

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_SKY_COLOR)
        painter.drawRect(QRectF(-large, -large, large * 2, large + h0))
        painter.setBrush(_GROUND_COLOR)
        painter.drawRect(QRectF(-large, h0, large * 2, large))

        if norm_pitch >= 0 and h_sec > -large:
            painter.setBrush(_GROUND_COLOR)
            painter.drawRect(QRectF(-large, -large, large * 2, large + h_sec))
        elif norm_pitch < 0 and h_sec < large:
            painter.setBrush(_SKY_COLOR)
            painter.drawRect(QRectF(-large, h_sec, large * 2, large))

        painter.setPen(QPen(_HORIZON_COLOR, 2))
        painter.drawLine(QPointF(-large, h0), QPointF(large, h0))
        if -large < h_sec < large:
            painter.setPen(QPen(_HORIZON_COLOR, 2))
            painter.drawLine(QPointF(-large, h_sec), QPointF(large, h_sec))

        pf = painter.font()
        pf.setPixelSize(_FONT_SIZE_UNIT)
        painter.setFont(pf)
        for deg in range(-170, 175, 5):
            if deg == 0:
                continue
            y_pos = pitch_offset - deg * ppd
            if deg % 10 == 0:
                half_w = 28
                draw_number = True
            else:
                half_w = 16
                draw_number = False
            painter.setPen(QPen(_PITCH_LADDER_COLOR, 1))
            painter.drawLine(QPointF(-half_w, y_pos), QPointF(half_w, y_pos))
            if draw_number:
                label = str(abs(deg))
                painter.setPen(_PITCH_LADDER_COLOR)
                painter.drawText(QRectF(-half_w - 24, y_pos - 6, 22, 12),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                 label)
                painter.drawText(QRectF(half_w + 2, y_pos - 6, 22, 12),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 label)

        for deg in [-90, 90]:
            y_pos = pitch_offset - deg * ppd
            painter.setPen(QPen(_REFERENCE_COLOR, 2))
            painter.drawLine(QPointF(-40, y_pos), QPointF(40, y_pos))
        painter.restore()

        arc_r = min(dial_w, dial_h) / 2 - 8
        painter.save()
        painter.translate(cx, cy)
        painter.setPen(QPen(_TICK_MINOR_COLOR, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc_rect = QRectF(-arc_r, -arc_r, arc_r * 2, arc_r * 2)
        painter.drawArc(arc_rect, 20 * 16, 140 * 16)
        painter.restore()

        roll_marks = [0, 10, 20, 30, 45, 60]
        for angle in roll_marks:
            signs = [1] if angle == 0 else [1, -1]
            for sign in signs:
                deg = angle * sign
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(deg)
                if angle == 0:
                    tick_len, tick_w = 14, _TICK_MAJOR_WIDTH
                    tick_color = _TICK_MAJOR_COLOR
                elif angle in (10, 20, 30):
                    tick_len, tick_w = 10, _TICK_MINOR_WIDTH
                    tick_color = _TICK_MAJOR_COLOR
                else:
                    tick_len, tick_w = 12, _TICK_MINOR_WIDTH
                    tick_color = _TICK_MAJOR_COLOR
                painter.setPen(QPen(tick_color, tick_w))
                painter.drawLine(QPointF(0, -arc_r), QPointF(0, -arc_r + tick_len))
                painter.restore()

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._roll)
        ptr_r = arc_r - 16
        ptr = QPainterPath()
        ptr.moveTo(0, -ptr_r)
        ptr.lineTo(-6, -ptr_r + 12)
        ptr.lineTo(6, -ptr_r + 12)
        ptr.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_NEEDLE_COLOR)
        painter.drawPath(ptr)
        painter.restore()

        painter.save()
        painter.translate(cx, cy)
        ref_r = arc_r - 16
        ref = QPainterPath()
        ref.moveTo(0, -ref_r + 14)
        ref.lineTo(-5, -ref_r + 2)
        ref.lineTo(5, -ref_r + 2)
        ref.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_REFERENCE_COLOR)
        painter.drawPath(ref)
        painter.restore()

        painter.save()
        painter.translate(cx, cy)
        painter.setPen(QPen(_AIRCRAFT_SYMBOL_COLOR, 3))
        painter.drawLine(QPointF(-30, 0), QPointF(-12, 0))
        painter.drawLine(QPointF(12, 0), QPointF(30, 0))
        painter.drawLine(QPointF(-30, 0), QPointF(-30, 5))
        painter.drawLine(QPointF(30, 0), QPointF(30, 5))
        painter.setBrush(_AIRCRAFT_SYMBOL_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 3, 3)
        painter.restore()





