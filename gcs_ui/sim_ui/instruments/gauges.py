from __future__ import annotations
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from .base import BaseInstrument, UnitButtonsMixin, TurnTargetMixin
from .circular import CircularGauge
from ..core.telemetry import TelemetryData
from ..core.units import AIRSPEED_UNITS, ALTITUDE_UNITS, unit_index


# =============================================================================
# AIRSPEED INDICATOR
# =============================================================================

class AirspeedIndicator(UnitButtonsMixin, CircularGauge):
    """
    Anemometro con cambio unità:
    KNOTS → KM/H → MPH → M/S
    """

    def __init__(self, p, parent=None):
        super().__init__(p, parent)
        self._base_min = 0.0
        self._base_max = 120.0
        self._base_value = 0.0
        self._minor_per_major = 4
        self.init_units(AIRSPEED_UNITS, 0)
        self._apply_unit()

    def _on_unit_changed(self):
        self._apply_unit()
        super()._on_unit_changed()

    def _apply_unit(self):
        u = self.current_unit()
        if not u:
            return
        self._min_val = self._base_min * u.factor
        self._max_val = self._base_max * u.factor
        self._major_step = u.major_step if u.major_step else 20.0 * u.factor
        self._unit_label = u.label
        self._label_format = "{:.0f}"
        self._value = self._base_value * u.factor

    def update_data(self, d: TelemetryData):
        self._base_value = d.airspeed
        self._value = self._base_value * self.current_unit().factor
        self.update()


# =============================================================================
# ALTIMETER (due lancette)
# =============================================================================

class Altimeter(UnitButtonsMixin, BaseInstrument):
    """
    Altimetro sensibile a due lancette con cambio unità:
    FEET → METERS
    """

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._altitude = 0.0
        self.init_units(ALTITUDE_UNITS, 0)

    def update_data(self, data: TelemetryData):
        self._altitude = max(0.0, data.altitude)
        self.update()

    def _display_altitude(self) -> float:
        u = self.current_unit()
        if not u:
            return self._altitude
        return self._altitude * u.factor

    def paint_background(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(40, 40, 45))
        painter.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        dial_r = outer_r - 6
        painter.setBrush(QColor(18, 20, 26))
        painter.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        tick_outer = dial_r - 4
        num_r = tick_outer - 22
        for i in range(10):
            angle_deg = i * 36.0

            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle_deg)
            painter.setPen(QPen(QColor(230, 230, 230), 2.5))
            painter.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + 16))
            painter.restore()

            rad = math.radians(angle_deg)
            lx = cx + num_r * math.sin(rad)
            ly = cy - num_r * math.cos(rad)
            painter.setPen(QColor(240, 240, 240))
            nf = painter.font()
            nf.setPixelSize(16)
            nf.setBold(True)
            painter.setFont(nf)
            painter.drawText(
                QRectF(lx - 12, ly - 10, 24, 20),
                Qt.AlignmentFlag.AlignCenter,
                str(i)
            )

            for m in range(1, 5):
                minor_angle = angle_deg + m * (36.0 / 5.0)
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(minor_angle)
                painter.setPen(QPen(QColor(180, 180, 180), 1))
                painter.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + 8))
                painter.restore()

        painter.setPen(QColor(180, 190, 200))
        tf = painter.font()
        tf.setPixelSize(9)
        tf.setBold(True)
        painter.setFont(tf)
        painter.drawText(
            QRectF(cx - 50, cy + dial_r * 0.30, 100, 16),
            Qt.AlignmentFlag.AlignCenter,
            "ALT"
        )

        u = self.current_unit()
        caption = f"100 {u.label}" if u else ""
        painter.setPen(QColor(140, 150, 160))
        uf = painter.font()
        uf.setPixelSize(8)
        uf.setBold(False)
        painter.setFont(uf)
        painter.drawText(
            QRectF(cx - 40, cy + dial_r * 0.48, 80, 14),
            Qt.AlignmentFlag.AlignCenter,
            caption
        )

    def paint_foreground(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 10
        alt = self._display_altitude()

        hundreds = alt % 1000.0
        hundreds_angle = (hundreds / 1000.0) * 360.0
        thousands = alt % 10000.0
        thousands_angle = (thousands / 10000.0) * 360.0

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(thousands_angle)
        short_len = dial_r * 0.55
        short_needle = QPainterPath()
        short_needle.moveTo(0, -short_len)
        short_needle.lineTo(-5, 10)
        short_needle.lineTo(5, 10)
        short_needle.closeSubpath()
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawPath(short_needle)
        painter.restore()

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(hundreds_angle)
        long_len = dial_r - 14
        long_needle = QPainterPath()
        long_needle.moveTo(0, -long_len)
        long_needle.lineTo(-2.5, 14)
        long_needle.lineTo(2.5, 14)
        long_needle.closeSubpath()
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawPath(long_needle)
        painter.restore()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(80, 80, 85))
        painter.drawEllipse(QPointF(cx, cy), 8, 8)
        painter.setBrush(QColor(50, 50, 55))
        painter.drawEllipse(QPointF(cx, cy), 5, 5)


# =============================================================================
# RPM GAUGE
# =============================================================================

class RPMGauge(CircularGauge):
    def __init__(self, p, parent=None):
        super().__init__(p, parent)
        self._min_val = 0
        self._max_val = 3000
        self._major_step = 500
        self._minor_per_major = 4
        self._unit_label = "RPM"

    def update_data(self, d: TelemetryData):
        self._value = d.rpm
        self.update()


# =============================================================================
# OIL TEMP GAUGE
# =============================================================================

class OilTempGauge(CircularGauge):
    def __init__(self, p, parent=None):
        super().__init__(p, parent)
        self._min_val = 0
        self._max_val = 150
        self._major_step = 25
        self._minor_per_major = 4
        self._unit_label = "°C"

    def update_data(self, d: TelemetryData):
        self._value = d.oil_temp
        self.update()


# =============================================================================
# HEADING INDICATOR
# =============================================================================

class HeadingIndicator(BaseInstrument):
    # Palette interna dello strumento (non dipende dal tema)
    _BEZEL_COLOR = QColor(40, 40, 45)
    _BEZEL_RING_COLOR = QColor(30, 30, 34)
    _DIAL_COLOR = QColor(20, 22, 28)
    _TICK_MAJOR_COLOR = QColor(220, 220, 220)
    _TICK_MINOR_COLOR = QColor(160, 160, 160)
    _TICK_MAJOR_WIDTH = 2.0
    _TICK_MINOR_WIDTH = 1.0
    _TEXT_COLOR = QColor(220, 220, 220)
    _FONT_SIZE_NUMBERS = 11
    _REFERENCE_COLOR = QColor(255, 160, 0)
    _AIRCRAFT_SYMBOL_COLOR = QColor(255, 200, 0)

    def __init__(self, p, parent=None):
        super().__init__(p, parent)
        self._heading = 0.0

    def update_data(self, d: TelemetryData):
        self._heading = d.heading % 360.0
        self.update()

    def paint_background(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._BEZEL_COLOR)
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)
        p.setBrush(self._BEZEL_RING_COLOR)
        p.drawEllipse(QPointF(cx, cy), outer_r - 3, outer_r - 3)
        dial_r = outer_r - 8
        p.setBrush(self._DIAL_COLOR)
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4
        dial_r = outer_r - 8

        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), dial_r - 2, dial_r - 2)
        p.save()
        p.setClipPath(clip)

        p.save()
        p.translate(cx, cy)
        p.rotate(-self._heading)

        card_r = dial_r - 6
        for deg in range(0, 360, 5):
            if deg % 30 == 0:
                tl, tw, tc = 16, self._TICK_MAJOR_WIDTH, self._TICK_MAJOR_COLOR
            elif deg % 10 == 0:
                tl, tw, tc = 12, self._TICK_MINOR_WIDTH, self._TICK_MAJOR_COLOR
            else:
                tl, tw, tc = 8, self._TICK_MINOR_WIDTH, self._TICK_MINOR_COLOR
            p.save()
            p.rotate(deg)
            p.setPen(QPen(tc, tw))
            p.drawLine(QPointF(0, -card_r), QPointF(0, -card_r + tl))
            p.restore()

        num_r = card_r - 26
        for deg in range(0, 360, 30):
            if deg == 0:
                lb, ic = "N", True
            elif deg == 90:
                lb, ic = "E", True
            elif deg == 180:
                lb, ic = "S", True
            elif deg == 270:
                lb, ic = "W", True
            else:
                lb, ic = str(deg // 10), False

            p.save()
            p.rotate(deg)
            p.translate(0, -num_r)
            p.setPen(self._TEXT_COLOR)
            nf = p.font()
            nf.setPixelSize(14 if ic else self._FONT_SIZE_NUMBERS)
            nf.setBold(ic)
            p.setFont(nf)
            p.drawText(QRectF(-12, -8, 24, 16), Qt.AlignmentFlag.AlignCenter, lb)
            p.restore()

        p.restore()
        p.restore()

        # Lubber line
        p.save()
        p.translate(cx, cy)
        lb2 = QPainterPath()
        lb2.moveTo(0, -dial_r + 3)
        lb2.lineTo(-6, -dial_r + 15)
        lb2.lineTo(6, -dial_r + 15)
        lb2.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._REFERENCE_COLOR)
        p.drawPath(lb2)
        p.restore()

        # Simbolo aereo
        p.save()
        p.translate(cx, cy)
        p.setPen(QPen(self._AIRCRAFT_SYMBOL_COLOR, 2))
        p.drawLine(QPointF(0, -12), QPointF(0, 12))
        p.drawLine(QPointF(-14, -2), QPointF(14, -2))
        p.drawLine(QPointF(-6, 9), QPointF(6, 9))
        p.restore()

# =============================================================================
# TURN COORDINATOR
# =============================================================================

class TurnCoordinator(TurnTargetMixin, BaseInstrument):
    """
    Virosbandometro base:
    - Aereo in miniatura che ruota con il turn_rate
    - Scala L/R con tacche
    - Inclinometro con pallina
    """

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._turn_rate = 0.0
        self._roll = 0.0
        self.init_turn_target(3.0)

    def update_data(self, data: TelemetryData):
        self._turn_rate = data.turn_rate
        self._roll = data.roll
        self.update()

    def paint_background(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(40, 40, 45))
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        dial_r = outer_r - 6
        p.setBrush(QColor(18, 20, 26))
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        tick_r = dial_r - 4
        for deg in [-30, -20, -10, 0, 10, 20, 30]:
            p.save()
            p.translate(cx, cy)
            p.rotate(deg)
            if deg == 0:
                tick_len, tick_w, tick_color = 14, 2.0, QColor(255, 255, 255)
            elif abs(deg) == 10:
                tick_len, tick_w, tick_color = 10, 1.5, QColor(220, 220, 220)
            else:
                tick_len, tick_w, tick_color = 12, 2.0, QColor(255, 255, 255)
            p.setPen(QPen(tick_color, tick_w))
            p.drawLine(QPointF(0, -tick_r), QPointF(0, -tick_r + tick_len))
            p.restore()

        p.setPen(QColor(240, 240, 240))
        lf = p.font()
        lf.setPixelSize(16)
        lf.setBold(True)
        p.setFont(lf)

        l_angle = math.radians(-45)
        lx = cx + (dial_r - 26) * math.sin(l_angle)
        ly = cy - (dial_r - 26) * math.cos(l_angle)
        p.drawText(QRectF(lx - 12, ly - 9, 24, 18),
                   Qt.AlignmentFlag.AlignCenter, "L")

        r_angle = math.radians(45)
        rx = cx + (dial_r - 26) * math.sin(r_angle)
        ry = cy - (dial_r - 26) * math.cos(r_angle)
        p.drawText(QRectF(rx - 12, ry - 9, 24, 18),
                   Qt.AlignmentFlag.AlignCenter, "R")

        p.setPen(QColor(180, 190, 200))
        tf = p.font()
        tf.setPixelSize(9)
        tf.setBold(True)
        p.setFont(tf)
        p.drawText(QRectF(cx - 60, cy + dial_r * 0.32, 120, 14),
                   Qt.AlignmentFlag.AlignCenter, "TURN COORDINATOR")

        p.setPen(QColor(140, 150, 160))
        uf = p.font()
        uf.setPixelSize(8)
        uf.setBold(False)
        p.setFont(uf)
        p.drawText(QRectF(cx - 30, cy + dial_r * 0.47, 60, 12),
                   Qt.AlignmentFlag.AlignCenter, "2 MIN")

        tube_bottom_y = cy + dial_r * 0.80
        tube_half_w = dial_r * 0.28
        tube_r = dial_r * 0.85
        tube_cy = tube_bottom_y - tube_r
        half_angle = math.degrees(math.asin(tube_half_w / tube_r))
        arc_rect = QRectF(cx - tube_r, tube_cy - tube_r, tube_r * 2, tube_r * 2)
        start_a = int((270 - half_angle) * 16)
        span_a = int(2 * half_angle * 16)

        p.setPen(QPen(QColor(235, 238, 242), 12,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect, start_a, span_a)

        outer_rect = QRectF(cx - tube_r - 6, tube_cy - tube_r - 6,
                            (tube_r + 6) * 2, (tube_r + 6) * 2)
        inner_rect = QRectF(cx - tube_r + 6, tube_cy - tube_r + 6,
                            (tube_r - 6) * 2, (tube_r - 6) * 2)
        p.setPen(QPen(QColor(80, 85, 90), 1))
        p.drawArc(outer_rect, start_a, span_a)
        p.drawArc(inner_rect, start_a, span_a)

        ref_gap = 12
        p.setPen(QPen(QColor(30, 30, 35), 1.5))
        p.drawLine(QPointF(cx - ref_gap / 2, tube_bottom_y - 6),
                   QPointF(cx - ref_gap / 2, tube_bottom_y + 6))
        p.drawLine(QPointF(cx + ref_gap / 2, tube_bottom_y - 6),
                   QPointF(cx + ref_gap / 2, tube_bottom_y + 6))

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 10

        self.draw_target_ticks(p, cx, cy, dial_r - 4)

        display_angle = self._turn_rate * (10.0 / 3.0)
        display_angle = max(-45.0, min(45.0, display_angle))

        p.save()
        p.translate(cx, cy)
        p.rotate(display_angle)
        wing_span = dial_r * 0.55
        p.setPen(QPen(QColor(255, 255, 255), 3))
        p.drawLine(QPointF(-wing_span, 0), QPointF(-8, 0))
        p.drawLine(QPointF(8, 0), QPointF(wing_span, 0))
        p.drawLine(QPointF(-wing_span, 0), QPointF(-wing_span, 6))
        p.drawLine(QPointF(wing_span, 0), QPointF(wing_span, 6))
        p.drawLine(QPointF(0, -7), QPointF(0, 7))
        p.drawLine(QPointF(-5, 7), QPointF(5, 7))
        p.setBrush(QColor(255, 255, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0, 0), 3, 3)
        p.restore()

        p.save()
        p.translate(cx, cy)
        p.rotate(display_angle)
        needle_len = dial_r - 12
        needle = QPainterPath()
        needle.moveTo(0, -needle_len)
        needle.lineTo(-3, 8)
        needle.lineTo(3, 8)
        needle.closeSubpath()
        p.setPen(QPen(QColor(140, 70, 30), 1))
        p.setBrush(QColor(255, 130, 40))
        p.drawPath(needle)
        p.restore()

        tube_bottom_y = cy + dial_r * 0.80
        tube_half_w = dial_r * 0.28
        tube_r = dial_r * 0.85
        tube_cy = tube_bottom_y - tube_r
        half_angle = math.degrees(math.asin(tube_half_w / tube_r))

        ball_offset = max(-1.0, min(1.0, self._roll / 30.0))
        ball_angle_deg = ball_offset * half_angle * 0.75
        angle_rad = math.radians(270 + ball_angle_deg)
        ball_x = cx + tube_r * math.cos(angle_rad)
        ball_y = tube_cy - tube_r * math.sin(angle_rad)
        ball_radius = 5.0

        p.setPen(QPen(QColor(15, 30, 70), 1))
        p.setBrush(QColor(30, 60, 150))
        p.drawEllipse(QPointF(ball_x, ball_y), ball_radius, ball_radius)