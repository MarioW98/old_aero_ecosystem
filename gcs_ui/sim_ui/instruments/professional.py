from __future__ import annotations
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen,
    QRadialGradient, QLinearGradient,
)

from .base import BaseInstrument, UnitButtonsMixin, TurnTargetMixin
from ..core.telemetry import TelemetryData
from ..core.units import AIRSPEED_UNITS, ALTITUDE_UNITS, VSI_UNITS, unit_index


# =============================================================================
# AIRSPEED PROFESSIONAL
# =============================================================================

class AirspeedIndicatorProfessional(UnitButtonsMixin, BaseInstrument):
    """
    Anemometro professionale con:
    - Bezel metallico con viti
    - Archi colorati (verde/giallo/rosso)
    - Lancetta con contrappeso
    - Effetto vetro
    - Cambio unità supportato
    """

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._base_min = 0.0
        self._base_max = 120.0
        self._base_value = 0.0
        self._value = 0.0

        # Range del gauge in unità corrente
        self._min_val = 0.0
        self._max_val = 200.0
        self._major_step = 20.0
        self._minor_per_major = 4
        self._unit_label = "KNOTS"

        self.init_units(AIRSPEED_UNITS, 0)
        self._apply_unit()

    # =========================================================================
    # UNITÀ DI MISURA
    # =========================================================================

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
        self._value = self._base_value * u.factor

    def update_data(self, data: TelemetryData):
        self._base_value = data.airspeed
        self._value = self._base_value * self.current_unit().factor
        self.update()

    def _value_to_rotation(self, v: float) -> float:
        n = (v - self._min_val) / max(1e-9, self._max_val - self._min_val)
        return -135.0 + max(0.0, min(1.0, n)) * 270.0

    def _value_to_qt_angle(self, v: float) -> float:
        """Converte un valore in angolo Qt per drawArc."""
        rot = self._value_to_rotation(v)
        return 90.0 - rot

    def _draw_color_arc(self, p: QPainter, rect: QRectF,
                        start_val: float, end_val: float,
                        color: QColor, width: float):
        """Disegna un arco colorato tra due valori."""
        start_qt = self._value_to_qt_angle(start_val)
        end_qt = self._value_to_qt_angle(end_val)
        span = end_qt - start_qt
        p.setPen(QPen(color, width))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, int(start_qt * 16), int(span * 16))

    # =========================================================================
    # SFONDO
    # =========================================================================

    def paint_background(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 2

        # --- Bezel metallico con gradiente ---
        gradient = QRadialGradient(cx, cy, outer_r)
        gradient.setColorAt(0.0, QColor(75, 75, 80))
        gradient.setColorAt(0.70, QColor(55, 55, 60))
        gradient.setColorAt(0.85, QColor(85, 85, 90))
        gradient.setColorAt(0.95, QColor(65, 65, 70))
        gradient.setColorAt(1.0, QColor(45, 45, 50))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # --- Quadrante nero ---
        dial_r = outer_r - 3
        p.setBrush(QColor(10, 10, 12))
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # --- Archi colorati ---
        arc_r = dial_r - 6
        arc_rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)

        # Verde: range operativo (20% - 80% del range)
        green_start = self._min_val + 0.20 * (self._max_val - self._min_val)
        green_end = self._min_val + 0.80 * (self._max_val - self._min_val)
        self._draw_color_arc(p, arc_rect, green_start, green_end,
                             QColor(40, 180, 60), 5)

        # Giallo: cautela (80% - 90%)
        yellow_start = green_end
        yellow_end = self._min_val + 0.90 * (self._max_val - self._min_val)
        self._draw_color_arc(p, arc_rect, yellow_start, yellow_end,
                             QColor(240, 200, 40), 5)

        # Rosso: limite (90% - 100%)
        red_start = yellow_end
        red_end = self._max_val
        self._draw_color_arc(p, arc_rect, red_start, red_end,
                             QColor(220, 50, 40), 5)

        # --- Tacche e numeri ---
        tick_outer = dial_r - 14
        major_len = 16
        minor_len = 9
        label_r = tick_outer - major_len - 14
        nm = int((self._max_val - self._min_val) / self._major_step) + 1

        for i in range(nm):
            val = self._min_val + i * self._major_step
            rot = self._value_to_rotation(val)

            # Tacca maggiore
            p.save()
            p.translate(cx, cy)
            p.rotate(rot)
            p.setPen(QPen(QColor(240, 240, 240), 2.5))
            p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + major_len))
            p.restore()

            # Numero
            rad = math.radians(rot)
            lx = cx + label_r * math.sin(rad)
            ly = cy - label_r * math.cos(rad)
            p.setPen(QColor(250, 250, 250))
            nf = p.font()
            nf.setPixelSize(13)
            nf.setBold(True)
            p.setFont(nf)
            p.drawText(QRectF(lx - 16, ly - 8, 32, 16),
                       Qt.AlignmentFlag.AlignCenter, f"{val:.0f}")

            # Tacche minori
            if i < nm - 1:
                for m in range(1, self._minor_per_major + 1):
                    mv = val + m * (self._major_step / (self._minor_per_major + 1))
                    mr = self._value_to_rotation(mv)
                    p.save()
                    p.translate(cx, cy)
                    p.rotate(mr)
                    p.setPen(QPen(QColor(180, 180, 180), 1))
                    p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + minor_len))
                    p.restore()

        # --- Titolo ---
        p.setPen(QColor(200, 210, 220))
        tf = p.font()
        tf.setPixelSize(10)
        tf.setBold(True)
        p.setFont(tf)
        p.drawText(QRectF(cx - 50, cy + dial_r * 0.30, 100, 18),
                   Qt.AlignmentFlag.AlignCenter, "AIRSPEED")

        # --- Etichetta unità ---
        p.setPen(QColor(150, 160, 170))
        uf = p.font()
        uf.setPixelSize(8)
        uf.setBold(False)
        p.setFont(uf)
        p.drawText(QRectF(cx - 40, cy + dial_r * 0.48, 80, 14),
                   Qt.AlignmentFlag.AlignCenter, self._unit_label)

        # --- Viti decorative ---
        screw_r = dial_r + 1
        for angle_deg in [45, 135, 225, 315]:
            rad = math.radians(angle_deg)
            sx = cx + screw_r * math.sin(rad)
            sy = cy - screw_r * math.cos(rad)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(60, 60, 65))
            p.drawEllipse(QPointF(sx, sy), 3.5, 3.5)
            p.setPen(QPen(QColor(35, 35, 40), 1))
            p.drawLine(QPointF(sx - 2, sy - 2), QPointF(sx + 2, sy + 2))

    # =========================================================================
    # PRIMO PIANO
    # =========================================================================

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 13
        needle_len = dial_r - 22
        rot = self._value_to_rotation(self._value)

        # --- Lancetta con contrappeso ---
        p.save()
        p.translate(cx, cy)
        p.rotate(rot)

        # Contrappeso (dietro il centro)
        cw = QPainterPath()
        cw.moveTo(-3, 18)
        cw.lineTo(3, 18)
        cw.lineTo(4, 8)
        cw.lineTo(-4, 8)
        cw.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(220, 220, 220))
        p.drawPath(cw)

        # Lancetta principale
        needle = QPainterPath()
        needle.moveTo(0, -needle_len)
        needle.lineTo(-3.5, 10)
        needle.lineTo(3.5, 10)
        needle.closeSubpath()
        p.setPen(QPen(QColor(180, 180, 180), 1))
        p.setBrush(QColor(255, 255, 255))
        p.drawPath(needle)

        p.restore()

        # --- Cappuccio centrale ---
        cap_gradient = QRadialGradient(cx, cy, 9)
        cap_gradient.setColorAt(0.0, QColor(100, 100, 105))
        cap_gradient.setColorAt(1.0, QColor(50, 50, 55))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cap_gradient))
        p.drawEllipse(QPointF(cx, cy), 8, 8)

        # --- Effetto vetro (riflesso) ---
        p.setPen(QPen(QColor(255, 255, 255, 18), 6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        glass_r = dial_r - 4
        glass_rect = QRectF(cx - glass_r, cy - glass_r, glass_r * 2, glass_r * 2)
        p.drawArc(glass_rect, 30 * 16, 120 * 16)


# =============================================================================
# HEADING INDICATOR PROFESSIONAL
# =============================================================================

class HeadingIndicatorProfessional(BaseInstrument):
    """
    Indicatore di prua professionale con:
    - Bezel metallico con viti
    - Rosa dei venti dettagliata
    - Cardinali stilizzati
    - Effetto vetro
    """

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._heading = 0.0

    def update_data(self, data: TelemetryData):
        self._heading = data.heading % 360.0
        self.update()

    # =========================================================================
    # SFONDO
    # =========================================================================

    def paint_background(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 2

        # Bezel metallico
        gradient = QRadialGradient(cx, cy, outer_r)
        gradient.setColorAt(0.0, QColor(75, 75, 80))
        gradient.setColorAt(0.70, QColor(55, 55, 60))
        gradient.setColorAt(0.85, QColor(85, 85, 90))
        gradient.setColorAt(0.95, QColor(65, 65, 70))
        gradient.setColorAt(1.0, QColor(45, 45, 50))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante
        dial_r = outer_r - 3
        p.setBrush(QColor(10, 10, 12))
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # Anello interno decorativo
        p.setPen(QPen(QColor(60, 60, 65), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), dial_r - 2, dial_r - 2)

        # Viti decorative
        screw_r = dial_r + 1
        for angle_deg in [45, 135, 225, 315]:
            rad = math.radians(angle_deg)
            sx = cx + screw_r * math.sin(rad)
            sy = cy - screw_r * math.cos(rad)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(60, 60, 65))
            p.drawEllipse(QPointF(sx, sy), 3.5, 3.5)
            p.setPen(QPen(QColor(35, 35, 40), 1))
            p.drawLine(QPointF(sx - 2, sy - 2), QPointF(sx + 2, sy + 2))

    # =========================================================================
    # PRIMO PIANO
    # =========================================================================

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 3
        dial_r = outer_r - 10

        # Clip per la rosa dei venti
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), dial_r - 4, dial_r - 4)
        p.save()
        p.setClipPath(clip)

        # --- Rosa dei venti (ruota con l'heading) ---
        p.save()
        p.translate(cx, cy)
        p.rotate(-self._heading)

        card_r = dial_r - 8

        # Tacche ogni 5°
        for deg in range(0, 360, 5):
            if deg % 30 == 0:
                tick_len, tick_w, tick_color = 18, 2.5, QColor(250, 250, 250)
            elif deg % 10 == 0:
                tick_len, tick_w, tick_color = 13, 1.5, QColor(220, 220, 220)
            else:
                tick_len, tick_w, tick_color = 8, 1.0, QColor(160, 160, 160)

            p.save()
            p.rotate(deg)
            p.setPen(QPen(tick_color, tick_w))
            p.drawLine(QPointF(0, -card_r), QPointF(0, -card_r + tick_len))
            p.restore()

        # Numeri ogni 30° e cardinali
        num_r = card_r - 28
        for deg in range(0, 360, 30):
            if deg == 0:
                label, is_cardinal, card_color = "N", True, QColor(255, 100, 80)
            elif deg == 90:
                label, is_cardinal, card_color = "E", True, QColor(250, 250, 250)
            elif deg == 180:
                label, is_cardinal, card_color = "S", True, QColor(250, 250, 250)
            elif deg == 270:
                label, is_cardinal, card_color = "W", True, QColor(250, 250, 250)
            else:
                label, is_cardinal, card_color = str(deg // 10), False, QColor(220, 220, 220)

            p.save()
            p.rotate(deg)
            p.translate(0, -num_r)
            p.setPen(card_color if is_cardinal else QColor(220, 220, 220))
            nf = p.font()
            nf.setPixelSize(16 if is_cardinal else 11)
            nf.setBold(is_cardinal)
            p.setFont(nf)
            p.drawText(QRectF(-14, -9, 28, 18), Qt.AlignmentFlag.AlignCenter, label)
            p.restore()

        p.restore()  # Fine rotazione rosa
        p.restore()  # Fine clip

        # --- Lubber line (fissa, non ruota) ---
        p.save()
        p.translate(cx, cy)

        lubber = QPainterPath()
        lubber.moveTo(0, -dial_r + 4)
        lubber.lineTo(-7, -dial_r + 18)
        lubber.lineTo(7, -dial_r + 18)
        lubber.closeSubpath()
        p.setPen(QPen(QColor(200, 120, 0), 1))
        p.setBrush(QColor(255, 150, 0))
        p.drawPath(lubber)

        # Linea centrale dal lubber verso il centro
        p.setPen(QPen(QColor(255, 150, 0, 120), 1))
        p.drawLine(QPointF(0, -dial_r + 18), QPointF(0, -dial_r + 30))

        p.restore()

        # --- Simbolo aereo (fisso) ---
        p.save()
        p.translate(cx, cy)

        p.setPen(QPen(QColor(255, 210, 60), 2.5))
        # Ali
        p.drawLine(QPointF(-16, -2), QPointF(-6, -2))
        p.drawLine(QPointF(6, -2), QPointF(16, -2))
        # Piegatura ali
        p.drawLine(QPointF(-16, -2), QPointF(-16, 3))
        p.drawLine(QPointF(16, -2), QPointF(16, 3))
        # Fusoliera
        p.drawLine(QPointF(0, -10), QPointF(0, 10))
        # Coda
        p.drawLine(QPointF(-5, 8), QPointF(5, 8))

        # Punto centrale
        p.setBrush(QColor(255, 210, 60))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0, 0), 2.5, 2.5)

        p.restore()

        # --- Effetto vetro ---
        p.setPen(QPen(QColor(255, 255, 255, 15), 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        glass_r = dial_r - 6
        glass_rect = QRectF(cx - glass_r, cy - glass_r, glass_r * 2, glass_r * 2)
        p.drawArc(glass_rect, 30 * 16, 120 * 16)

# =============================================================================
# ALTIMETER PROFESSIONAL
# =============================================================================

class AltimeterProfessional(UnitButtonsMixin, BaseInstrument):
    """
    Altimetro professionale a due lancette con:
    - Bezel metallico con viti
    - Lancette con contrappeso
    - Finestrella digitale per le migliaia
    - Effetto vetro
    - Cambio unità supportato (FEET / METERS)
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

    # =========================================================================
    # SFONDO
    # =========================================================================

    def paint_background(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 2

        # Bezel metallico con gradiente
        gradient = QRadialGradient(cx, cy, outer_r)
        gradient.setColorAt(0.0, QColor(75, 75, 80))
        gradient.setColorAt(0.70, QColor(55, 55, 60))
        gradient.setColorAt(0.85, QColor(85, 85, 90))
        gradient.setColorAt(0.95, QColor(65, 65, 70))
        gradient.setColorAt(1.0, QColor(45, 45, 50))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante nero
        dial_r = outer_r - 3
        painter.setBrush(QColor(10, 10, 12))
        painter.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # Tacche e numeri 0-9
        tick_outer = dial_r - 4
        num_r = tick_outer - 22

        for i in range(10):
            angle_deg = i * 36.0

            # Tacca principale
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle_deg)
            painter.setPen(QPen(QColor(245, 245, 245), 2.5))
            painter.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + 16))
            painter.restore()

            # Numero grande
            rad = math.radians(angle_deg)
            lx = cx + num_r * math.sin(rad)
            ly = cy - num_r * math.cos(rad)
            painter.setPen(QColor(250, 250, 250))
            nf = painter.font()
            nf.setPixelSize(18)
            nf.setBold(True)
            painter.setFont(nf)
            painter.drawText(QRectF(lx - 14, ly - 10, 28, 20),
                             Qt.AlignmentFlag.AlignCenter, str(i))

            # Tacche minori
            for m in range(1, 5):
                minor_angle = angle_deg + m * (36.0 / 5.0)
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(minor_angle)
                painter.setPen(QPen(QColor(160, 160, 160), 1))
                painter.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + 8))
                painter.restore()

        # Titolo (sopra il centro)
        painter.setPen(QColor(200, 210, 220))
        tf = painter.font()
        tf.setPixelSize(10)
        tf.setBold(True)
        painter.setFont(tf)
        painter.drawText(QRectF(cx - 50, cy - dial_r * 0.42, 100, 16),
                         Qt.AlignmentFlag.AlignCenter, "ALTIMETER")

        # Etichetta unità
        u = self.current_unit()
        caption = f"100 {u.label}" if u else ""
        painter.setPen(QColor(150, 160, 170))
        uf = painter.font()
        uf.setPixelSize(8)
        uf.setBold(False)
        painter.setFont(uf)
        painter.drawText(QRectF(cx - 40, cy - dial_r * 0.58, 80, 14),
                         Qt.AlignmentFlag.AlignCenter, caption)

        # Cornice finestrella migliaia (sotto il centro)
        win_w, win_h = 42, 18
        win_x = cx - win_w / 2
        win_y = cy + dial_r * 0.30
        painter.setPen(QPen(QColor(80, 80, 85), 1))
        painter.setBrush(QColor(5, 5, 8))
        painter.drawRoundedRect(QRectF(win_x, win_y, win_w, win_h), 3, 3)

        # Viti decorative
        screw_r = dial_r + 1
        for angle_deg in [45, 135, 225, 315]:
            rad = math.radians(angle_deg)
            sx = cx + screw_r * math.sin(rad)
            sy = cy - screw_r * math.cos(rad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(60, 60, 65))
            painter.drawEllipse(QPointF(sx, sy), 2.0, 2.0)
            painter.setPen(QPen(QColor(35, 35, 40), 1))
            painter.drawLine(QPointF(sx - 1.2, sy - 1.2), QPointF(sx + 1.2, sy + 1.2))

    # =========================================================================
    # PRIMO PIANO
    # =========================================================================

    def paint_foreground(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 2
        dial_r = outer_r - 3
        alt = self._display_altitude()

        # Calcolo angoli lancette
        hundreds = alt % 1000.0
        hundreds_angle = (hundreds / 1000.0) * 360.0
        thousands = alt % 10000.0
        thousands_angle = (thousands / 10000.0) * 360.0

        # --- Lancetta corta (migliaia) con contrappeso ---
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(thousands_angle)

        # Contrappeso
        cw = QPainterPath()
        cw.moveTo(-3, 16)
        cw.lineTo(3, 16)
        cw.lineTo(3.5, 8)
        cw.lineTo(-3.5, 8)
        cw.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(220, 220, 220))
        painter.drawPath(cw)

        # Lancetta
        short_len = dial_r * 0.55
        short_needle = QPainterPath()
        short_needle.moveTo(0, -short_len)
        short_needle.lineTo(-5, 10)
        short_needle.lineTo(5, 10)
        short_needle.closeSubpath()
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawPath(short_needle)
        painter.restore()

        # --- Lancetta lunga (centinaia) con contrappeso ---
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(hundreds_angle)

        # Contrappeso
        cw2 = QPainterPath()
        cw2.moveTo(-2.5, 20)
        cw2.lineTo(2.5, 20)
        cw2.lineTo(3, 10)
        cw2.lineTo(-3, 10)
        cw2.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(220, 220, 220))
        painter.drawPath(cw2)

        # Lancetta
        long_len = dial_r - 14
        long_needle = QPainterPath()
        long_needle.moveTo(0, -long_len)
        long_needle.lineTo(-2.5, 12)
        long_needle.lineTo(2.5, 12)
        long_needle.closeSubpath()
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawPath(long_needle)
        painter.restore()

        # --- Cappuccio centrale ---
        cap_gradient = QRadialGradient(cx, cy, 9)
        cap_gradient.setColorAt(0.0, QColor(100, 100, 105))
        cap_gradient.setColorAt(1.0, QColor(50, 50, 55))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(cap_gradient))
        painter.drawEllipse(QPointF(cx, cy), 8, 8)

        # --- Valore finestrella migliaia ---
        win_w, win_h = 42, 18
        win_x = cx - win_w / 2
        win_y = cy + dial_r * 0.30
        thousands_value = int(alt / 1000)

        painter.setPen(QColor(255, 180, 60))
        vf = painter.font()
        vf.setPixelSize(12)
        vf.setBold(True)
        vf.setFamily("Consolas")
        painter.setFont(vf)
        painter.drawText(QRectF(win_x, win_y, win_w, win_h),
                         Qt.AlignmentFlag.AlignCenter, f"{thousands_value:02d}")

        # --- Effetto vetro ---
        painter.setPen(QPen(QColor(255, 255, 255, 18), 6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        glass_r = dial_r - 4
        glass_rect = QRectF(cx - glass_r, cy - glass_r, glass_r * 2, glass_r * 2)
        painter.drawArc(glass_rect, 30 * 16, 120 * 16)

# =============================================================================
# VSI (VERTICAL SPEED INDICATOR) PROFESSIONAL
# =============================================================================

class VSIGaugeProfessional(UnitButtonsMixin, BaseInstrument):
    """
    Variometro professionale con:
    - Scala UP/DOWN con 0 a ore 9
    - Bezel metallico con viti
    - Lancetta con contrappeso
    - Effetto vetro
    - Cambio unità (FT/MIN / M/S)
    """

    SWEEP_DEG = 170.0  # escursione per lato (170° sopra e sotto lo zero)

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._base_max_abs = 10.0   # valore assoluto massimo in unità base (fpm)
        self._base_value = 0.0
        self._value = 0.0

        self._max_abs = 2000.0        # max assoluto in unità corrente
        self._major_step = 500.0
        self._label_scale = 100.0     # divisore per etichette (500→"5")
        self._unit_label = "FT/MIN"

        self.init_units(VSI_UNITS, unit_index(VSI_UNITS, "M/S"))
        self._apply_unit()

    # =========================================================================
    # UNITÀ DI MISURA
    # =========================================================================

    def _on_unit_changed(self):
        self._apply_unit()
        super()._on_unit_changed()

    def _apply_unit(self):
        u = self.current_unit()
        if not u:
            return
        self._max_abs = self._base_max_abs * u.factor
        self._major_step = u.major_step if u.major_step else 500.0 * u.factor
        self._unit_label = u.label
        # Scala etichette: in fpm mostro centinaia (500→"5"), in m/s il valore diretto
        self._label_scale = 100.0 if u.unit_id == "fpm" else 1.0

    def update_data(self, data: TelemetryData):
        self._base_value = data.vertical_speed
        self._value = self._base_value * self.current_unit().factor
        self.update()

    # =========================================================================
    # CONVERSIONE VALORE → ROTAZIONE
    # =========================================================================

    def _value_to_rotation(self, v: float) -> float:
        """
        0 → 270° (ore 9, sinistra)
        +max → 270° + 170° = 440° (= 80°)
        -max → 270° - 170° = 100°
        """
        n = v / max(1e-9, self._max_abs)
        n = max(-1.0, min(1.0, n))
        return 270.0 + n * self.SWEEP_DEG

    # =========================================================================
    # SFONDO
    # =========================================================================

    def paint_background(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 2

        # Bezel metallico con gradiente
        gradient = QRadialGradient(cx, cy, outer_r)
        gradient.setColorAt(0.0, QColor(75, 75, 80))
        gradient.setColorAt(0.70, QColor(55, 55, 60))
        gradient.setColorAt(0.85, QColor(85, 85, 90))
        gradient.setColorAt(0.95, QColor(65, 65, 70))
        gradient.setColorAt(1.0, QColor(45, 45, 50))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante nero
        dial_r = outer_r - 3
        p.setBrush(QColor(10, 10, 12))
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # =====================================================================
        # TACCHE E NUMERI
        # =====================================================================
        tick_outer = dial_r - 4
        major_len = 16
        minor_len = 9
        label_r = tick_outer - major_len - 14
        num_steps = int(self._max_abs / self._major_step)

        # --- Tacche maggiori e numeri (entrambi i lati) ---
        for i in range(num_steps + 1):
            val = i * self._major_step

            # Lato positivo (UP) e negativo (DOWN)
            for sign in ([1] if i == 0 else [1, -1]):
                v = val * sign
                rot = self._value_to_rotation(v)

                # Tacca maggiore
                p.save()
                p.translate(cx, cy)
                p.rotate(rot)
                p.setPen(QPen(QColor(245, 245, 245), 2.5))
                p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + major_len))
                p.restore()

                # Numero (solo per i > 0, lo 0 lo disegno una volta)
                if i > 0 or sign == 1:
                    label_val = val / self._label_scale
                    rad = math.radians(rot)
                    lx = cx + label_r * math.sin(rad)
                    ly = cy - label_r * math.cos(rad)
                    p.setPen(QColor(250, 250, 250))
                    nf = p.font()
                    nf.setPixelSize(13)
                    nf.setBold(True)
                    p.setFont(nf)
                    p.drawText(QRectF(lx - 16, ly - 8, 32, 16),
                               Qt.AlignmentFlag.AlignCenter, f"{label_val:.0f}")

            # --- Tacche minori (tra questa e la prossima maggiore) ---
            if i < num_steps:
                for m in range(1, 3):
                    frac = m / 3.0

                    # Lato positivo
                    mv_pos = val + frac * self._major_step
                    rot_pos = self._value_to_rotation(mv_pos)
                    p.save()
                    p.translate(cx, cy)
                    p.rotate(rot_pos)
                    p.setPen(QPen(QColor(160, 160, 160), 1))
                    p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + minor_len))
                    p.restore()

                    # Lato negativo
                    mv_neg = -(val + frac * self._major_step)
                    rot_neg = self._value_to_rotation(mv_neg)
                    p.save()
                    p.translate(cx, cy)
                    p.rotate(rot_neg)
                    p.setPen(QPen(QColor(160, 160, 160), 1))
                    p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + minor_len))
                    p.restore()

        # =====================================================================
        # ETICHETTE UP / DOWN
        # =====================================================================
        p.setPen(QColor(200, 210, 220))
        tf = p.font()
        tf.setPixelSize(11)
        tf.setBold(True)
        p.setFont(tf)

        # UP: in alto leggermente a sinistra (zona positiva)
        p.drawText(QRectF(cx - 50, cy - dial_r * 0.36, 40, 16),
                   Qt.AlignmentFlag.AlignCenter, "UP")

        # DOWN: in basso leggermente a sinistra (zona negativa)
        p.drawText(QRectF(cx - 50, cy + dial_r * 0.20, 46, 16),
                   Qt.AlignmentFlag.AlignCenter, "DOWN")

        # --- Titolo ---
        tf2 = p.font()
        tf2.setPixelSize(9)
        tf2.setBold(True)
        p.setFont(tf2)
        p.setPen(QColor(180, 190, 200))
        p.drawText(QRectF(cx - 55, cy - dial_r * 0.18, 110, 14),
                   Qt.AlignmentFlag.AlignCenter, "VERTICAL SPEED")

        # --- Etichetta unità ---
        p.setPen(QColor(150, 160, 170))
        uf = p.font()
        uf.setPixelSize(8)
        uf.setBold(False)
        p.setFont(uf)
        p.drawText(QRectF(cx - 45, cy + dial_r * 0.08, 90, 12),
                   Qt.AlignmentFlag.AlignCenter, self._unit_label)

        # =====================================================================
        # VITI DECORATIVE
        # =====================================================================
        screw_r = dial_r + 1
        for angle_deg in [45, 135, 225, 315]:
            rad = math.radians(angle_deg)
            sx = cx + screw_r * math.sin(rad)
            sy = cy - screw_r * math.cos(rad)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(60, 60, 65))
            p.drawEllipse(QPointF(sx, sy), 2.0, 2.0)
            p.setPen(QPen(QColor(35, 35, 40), 1))
            p.drawLine(QPointF(sx - 1.2, sy - 1.2), QPointF(sx + 1.2, sy + 1.2))
    # =========================================================================
    # PRIMO PIANO
    # =========================================================================

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 2
        dial_r = outer_r - 3
        needle_len = dial_r - 20
        rot = self._value_to_rotation(self._value)

        # Lancetta con contrappeso
        p.save()
        p.translate(cx, cy)
        p.rotate(rot)

        # Contrappeso
        cw = QPainterPath()
        cw.moveTo(-3, 18)
        cw.lineTo(3, 18)
        cw.lineTo(3.5, 8)
        cw.lineTo(-3.5, 8)
        cw.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(220, 220, 220))
        p.drawPath(cw)

        # Lancetta
        nd = QPainterPath()
        nd.moveTo(0, -needle_len)
        nd.lineTo(-3, 10)
        nd.lineTo(3, 10)
        nd.closeSubpath()
        p.setPen(QPen(QColor(180, 180, 180), 1))
        p.setBrush(QColor(255, 255, 255))
        p.drawPath(nd)
        p.restore()

        # Cappuccio centrale
        cap_gradient = QRadialGradient(cx, cy, 9)
        cap_gradient.setColorAt(0.0, QColor(100, 100, 105))
        cap_gradient.setColorAt(1.0, QColor(50, 50, 55))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cap_gradient))
        p.drawEllipse(QPointF(cx, cy), 8, 8)

        # Effetto vetro
        p.setPen(QPen(QColor(255, 255, 255, 18), 6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        glass_r = dial_r - 4
        glass_rect = QRectF(cx - glass_r, cy - glass_r, glass_r * 2, glass_r * 2)
        p.drawArc(glass_rect, 30 * 16, 120 * 16)

# =============================================================================
# TURN COORDINATOR PROFESSIONAL
# =============================================================================

class TurnCoordinatorProfessional(TurnTargetMixin, BaseInstrument):
    """
    Virosbandometro professionale con:
    - Bezel metallico con viti
    - Aereo in miniatura dettagliato
    - Scala L/R con tacche precise
    - Inclinometro con pallina
    - Effetto vetro
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

    # =========================================================================
    # SFONDO
    # =========================================================================

    def paint_background(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 2

        # Bezel metallico con gradiente
        gradient = QRadialGradient(cx, cy, outer_r)
        gradient.setColorAt(0.0, QColor(75, 75, 80))
        gradient.setColorAt(0.70, QColor(55, 55, 60))
        gradient.setColorAt(0.85, QColor(85, 85, 90))
        gradient.setColorAt(0.95, QColor(65, 65, 70))
        gradient.setColorAt(1.0, QColor(45, 45, 50))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante nero
        dial_r = outer_r - 3
        p.setBrush(QColor(10, 10, 12))
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # --- Scala: tacche ogni 10° da -30 a +30 ---
        tick_r = dial_r - 4
        for deg in range(-30, 35, 10):
            p.save()
            p.translate(cx, cy)
            p.rotate(deg)
            if deg == 0:
                tick_len, tick_w = 14, 2.5
                tick_color = QColor(250, 250, 250)
            else:
                tick_len, tick_w = 12, 2.0
                tick_color = QColor(245, 245, 245)
            p.setPen(QPen(tick_color, tick_w))
            p.drawLine(QPointF(0, -tick_r), QPointF(0, -tick_r + tick_len))
            p.restore()

        # Tacche minori ogni 5°
        for deg in range(-30, 35, 5):
            if deg % 10 == 0:
                continue
            p.save()
            p.translate(cx, cy)
            p.rotate(deg)
            p.setPen(QPen(QColor(160, 160, 160), 1))
            p.drawLine(QPointF(0, -tick_r), QPointF(0, -tick_r + 7))
            p.restore()

        # --- Etichette L e R ---
        p.setPen(QColor(250, 250, 250))
        lf = p.font()
        lf.setPixelSize(17)
        lf.setBold(True)
        p.setFont(lf)

        label_r = dial_r - 26
        rad_l = math.radians(-40)
        lx = cx + label_r * math.sin(rad_l)
        ly = cy - label_r * math.cos(rad_l)
        p.drawText(QRectF(lx - 14, ly - 10, 28, 20),
                   Qt.AlignmentFlag.AlignCenter, "L")

        rad_r = math.radians(40)
        rx = cx + label_r * math.sin(rad_r)
        ry = cy - label_r * math.cos(rad_r)
        p.drawText(QRectF(rx - 14, ry - 10, 28, 20),
                   Qt.AlignmentFlag.AlignCenter, "R")

        # --- Titolo ---
        p.setPen(QColor(200, 210, 220))
        tf = p.font()
        tf.setPixelSize(10)
        tf.setBold(True)
        p.setFont(tf)
        p.drawText(QRectF(cx - 65, cy + dial_r * 0.46, 130, 16),
                   Qt.AlignmentFlag.AlignCenter, "TURN COORDINATOR")

        # --- Etichetta "2 MIN" ---
        p.setPen(QColor(150, 160, 170))
        uf = p.font()
        uf.setPixelSize(8)
        uf.setBold(False)
        p.setFont(uf)
        p.drawText(QRectF(cx - 30, cy + dial_r * 0.56, 60, 12),
                   Qt.AlignmentFlag.AlignCenter, "2 MIN")

        # --- Inclinometro (tubo bianco) ---
        tube_bottom_y = cy + dial_r * 0.80
        tube_half_w = dial_r * 0.28
        tube_r = dial_r * 0.85
        tube_cy = tube_bottom_y - tube_r
        half_angle = math.degrees(math.asin(tube_half_w / tube_r))
        arc_rect = QRectF(cx - tube_r, tube_cy - tube_r, tube_r * 2, tube_r * 2)
        start_a = int((270 - half_angle) * 16)
        span_a = int(2 * half_angle * 16)

        # Corpo del tubo: arco spesso bianco
        p.setPen(QPen(QColor(235, 238, 242), 12,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect, start_a, span_a)

        # Bordi del tubo (sopra e sotto)
        outer_rect = QRectF(cx - tube_r - 6, tube_cy - tube_r - 6,
                            (tube_r + 6) * 2, (tube_r + 6) * 2)
        inner_rect = QRectF(cx - tube_r + 6, tube_cy - tube_r + 6,
                            (tube_r - 6) * 2, (tube_r - 6) * 2)
        p.setPen(QPen(QColor(80, 85, 90), 1))
        p.drawArc(outer_rect, start_a, span_a)
        p.drawArc(inner_rect, start_a, span_a)

        # Linee di riferimento (nere su bianco)
        ref_gap = 12
        p.setPen(QPen(QColor(30, 30, 35), 1.5))
        p.drawLine(QPointF(cx - ref_gap / 2, tube_bottom_y - 6),
                   QPointF(cx - ref_gap / 2, tube_bottom_y + 6))
        p.drawLine(QPointF(cx + ref_gap / 2, tube_bottom_y - 6),
                   QPointF(cx + ref_gap / 2, tube_bottom_y + 6))


        # --- Viti decorative ---
        screw_r = dial_r + 1
        for angle_deg in [45, 135, 225, 315]:
            rad = math.radians(angle_deg)
            sx = cx + screw_r * math.sin(rad)
            sy = cy - screw_r * math.cos(rad)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(60, 60, 65))
            p.drawEllipse(QPointF(sx, sy), 2.0, 2.0)
            p.setPen(QPen(QColor(35, 35, 40), 1))
            p.drawLine(QPointF(sx - 1.2, sy - 1.2), QPointF(sx + 1.2, sy + 1.2))

    # =========================================================================
    # PRIMO PIANO
    # =========================================================================

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 5

        # Tacche target turn rate
        self.draw_target_ticks(p, cx, cy, dial_r - 4)

        # Mappatura turn_rate → angolo display
        display_angle = self._turn_rate * (10.0 / 3.0)
        display_angle = max(-45.0, min(45.0, display_angle))

        # --- Lancetta di lettura scala (0° = ore 12) ---
        p.save()
        p.translate(cx, cy)
        p.rotate(display_angle)

        needle_len = dial_r - 12
        inner_r = dial_r * 0.40

        needle = QPainterPath()
        needle.moveTo(0, -needle_len)
        needle.lineTo(-3, -inner_r)
        needle.lineTo(3, -inner_r)
        needle.closeSubpath()

        p.setPen(QPen(QColor(140, 70, 30), 1))
        p.setBrush(QColor(255, 130, 40))
        p.drawPath(needle)

        p.restore()

        # --- Aereo in miniatura ---
        p.save()
        p.translate(cx, cy)
        p.rotate(display_angle)

        wing_span = dial_r * 0.52
        fuselage_h = 16

        # Ombra dell'aereo
        p.setPen(QPen(QColor(0, 0, 0, 60), 4))
        p.drawLine(QPointF(-wing_span + 1, 2), QPointF(-8, 2))
        p.drawLine(QPointF(8, 2), QPointF(wing_span - 1, 2))

        # Ali principali
        p.setPen(QPen(QColor(255, 255, 255), 3.5))
        p.drawLine(QPointF(-wing_span, 0), QPointF(-8, 0))
        p.drawLine(QPointF(8, 0), QPointF(wing_span, 0))

        # Piegatura ali
        p.setPen(QPen(QColor(255, 255, 255), 2.5))
        p.drawLine(QPointF(-wing_span, 0), QPointF(-wing_span, 7))
        p.drawLine(QPointF(wing_span, 0), QPointF(wing_span, 7))

        # Fusoliera
        p.setPen(QPen(QColor(255, 255, 255), 3))
        p.drawLine(QPointF(0, -fuselage_h / 2), QPointF(0, fuselage_h / 2))

        # Coda
        p.drawLine(QPointF(-6, fuselage_h / 2), QPointF(6, fuselage_h / 2))

        # Punto centrale
        cap_gradient = QRadialGradient(0, 0, 4)
        cap_gradient.setColorAt(0.0, QColor(255, 255, 255))
        cap_gradient.setColorAt(1.0, QColor(180, 180, 180))
        p.setBrush(QBrush(cap_gradient))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0, 0), 3.5, 3.5)

        p.restore()

        # --- Pallina inclinometro (blu scuro con effetto 3D) ---
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

        ball_gradient = QRadialGradient(ball_x - 1.5, ball_y - 1.5, ball_radius * 2)
        ball_gradient.setColorAt(0.0, QColor(90, 130, 220))
        ball_gradient.setColorAt(0.5, QColor(40, 75, 170))
        ball_gradient.setColorAt(1.0, QColor(20, 40, 100))

        p.setPen(QPen(QColor(15, 30, 70), 1))
        p.setBrush(QBrush(ball_gradient))
        p.drawEllipse(QPointF(ball_x, ball_y), ball_radius, ball_radius)

        # --- Effetto vetro ---
        p.setPen(QPen(QColor(255, 255, 255, 18), 6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        glass_r = dial_r - 4
        glass_rect = QRectF(cx - glass_r, cy - glass_r, glass_r * 2, glass_r * 2)
        p.drawArc(glass_rect, 30 * 16, 120 * 16)