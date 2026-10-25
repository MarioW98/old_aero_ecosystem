from __future__ import annotations
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from .base import BaseInstrument, UnitButtonsMixin, TurnTargetMixin, ColorSelectorMixin
from ..core.telemetry import TelemetryData
from ..core.units import AIRSPEED_UNITS, ALTITUDE_UNITS, VSI_UNITS, unit_index


# =============================================================================
# PALETTE COMFORT
# =============================================================================
# Tutte le tinte derivano dal colore primario: per una nuova variante
# basta aggiungere un RGB.

def _make_palette(rgb):
    r, g, b = rgb
    return {
        "primary":  QColor(r, g, b),
        "bright":   QColor(min(255, r + 70), min(255, g + 70), min(255, b + 70)),
        "dim":      QColor(r, g, b, 140),
        "faint":    QColor(r, g, b, 65),
        "bg_outer": QColor(18 + r // 20, 16 + g // 20, 14 + b // 20),
        "bg_inner": QColor(6 + r // 40, 6 + g // 40, 5 + b // 40),
    }


COMFORT_ORANGE = _make_palette((255, 126, 0))   # Arancione BMW
COMFORT_GREEN  = _make_palette((0, 175, 0))     # Verde HUD militare
COMFORT_BLUE = _make_palette((0, 120, 255))


# =============================================================================
# AIRSPEED COMFORT — ANALOGICO
# =============================================================================

class AirspeedComfort(ColorSelectorMixin, UnitButtonsMixin, BaseInstrument):
    """
    Anemometro analogico stile Comfort:
    - Quadrante circolare con lancetta, palette monocromatica
    - Cambio unità: pulsanti in alto a destra (UnitButtonsMixin)
    - Cambio colore: selettore in basso a destra (orange ↔ green ↔ blue)
    """

    _PALETTES = {
        "orange": COMFORT_ORANGE,
        "green":  COMFORT_GREEN,
        "blue":   COMFORT_BLUE,
    }
    _PALETTE_ORDER = ["orange", "green", "blue"]

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self.init_color_selector("orange")
        # Dati
        self._base_min = 0.0
        self._base_max = 200.0
        self._base_value = 0.0
        self._value = 0.0
        # Scala
        self._min_val = 0.0
        self._max_val = 120.0
        self._major_step = 20.0
        self._minor_per_major = 1        # Comfort: una sola tacca minore
        self._label_format = "{:.0f}"
        # Unità (default SI)
        self.init_units(AIRSPEED_UNITS, unit_index(AIRSPEED_UNITS, "M/S"))
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
        self._label_format = "{:.0f}" #% u.decimals
        self._value = self._base_value * u.factor

    def update_data(self, data: TelemetryData):
        self._base_value = max(0.0, data.airspeed)
        self._value = self._base_value * self.current_unit().factor
        self.update()

    def _value_to_rotation(self, v: float) -> float:
        n = (v - self._min_val) / max(1e-9, self._max_val - self._min_val)
        return -135.0 + max(0.0, min(1.0, n)) * 270.0

    # =========================================================================
    # DISEGNO
    # =========================================================================

    def paint_background(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4

        # Bezel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bg_outer"])
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante quasi nero
        dial_r = outer_r - 6
        p.setBrush(pal["bg_inner"])
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # Anello sottile intonato
        p.setPen(QPen(pal["dim"], 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), dial_r - 1, dial_r - 1)

        # --- Tacche e numeri ---
        tick_outer = dial_r - 5
        major_len = 14
        minor_len = 8
        label_r = tick_outer - major_len - 13

        nm = int(round((self._max_val - self._min_val) / self._major_step)) + 1
        for i in range(nm):
            val = self._min_val + i * self._major_step
            rot = self._value_to_rotation(val)

            # Tacca maggiore
            p.save()
            p.translate(cx, cy)
            p.rotate(rot)
            p.setPen(QPen(pal["primary"], 2.5))
            p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + major_len))
            p.restore()

            # Numero (monospace brillante)
            rad = math.radians(rot)
            lx = cx + label_r * math.sin(rad)
            ly = cy - label_r * math.cos(rad)
            p.setPen(pal["bright"])
            nf = p.font()
            nf.setPixelSize(13)
            nf.setBold(True)
            nf.setFamily("Consolas")
            p.setFont(nf)
            p.drawText(QRectF(lx - 24, ly - 8, 48, 16),
                       Qt.AlignmentFlag.AlignCenter,
                       self._label_format.format(val))

            # Tacche minori (una sola, stile pulito)
            if i < nm - 1:
                for m in range(1, self._minor_per_major + 1):
                    mv = val + m * (self._major_step / (self._minor_per_major + 1))
                    mr = self._value_to_rotation(mv)
                    p.save()
                    p.translate(cx, cy)
                    p.rotate(mr)
                    p.setPen(QPen(pal["faint"], 1.2))
                    p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + minor_len))
                    p.restore()

        # --- Titolo ---
        p.setPen(pal["dim"])
        tf = p.font()
        tf.setPixelSize(10)
        tf.setBold(True)
        p.setFont(tf)
        p.drawText(QRectF(cx - 50, cy + dial_r * 0.28, 100, 16),
                   Qt.AlignmentFlag.AlignCenter, "AIRSPEED")

        # --- Etichetta unità ---
        u = self.current_unit()
        p.setPen(pal["primary"])
        uf = p.font()
        uf.setPixelSize(9)
        uf.setBold(True)
        p.setFont(uf)
        p.drawText(QRectF(cx - 40, cy + dial_r * 0.48, 80, 14),
                   Qt.AlignmentFlag.AlignCenter, u.label if u else "")

    def paint_foreground(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 10
        needle_len = dial_r - 18
        rot = self._value_to_rotation(self._value)

        # Lancetta
        p.save()
        p.translate(cx, cy)
        p.rotate(rot)
        nd = QPainterPath()
        nd.moveTo(0, -needle_len)
        nd.lineTo(-3.5, 12)
        nd.lineTo(3.5, 12)
        nd.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bright"])
        p.drawPath(nd)
        p.restore()

        # Mozzo centrale
        p.setPen(QPen(pal["dim"], 1))
        p.setBrush(pal["bg_outer"])
        p.drawEllipse(QPointF(cx, cy), 7, 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["primary"])
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)


# =============================================================================
# ALTIMETER COMFORT — ANALOGICO
# =============================================================================

class AltimeterComfort(ColorSelectorMixin, UnitButtonsMixin, BaseInstrument):
    """
    Altimetro analogico a due lancette stile Comfort:
    - Lancetta lunga: centinaia (1 giro = 1000 unità)
    - Lancetta corta: migliaia (1 giro = 10000 unità)
    - Cambio unità: FEET / METERS (default METERS)
    - Cambio colore: selettore in basso a destra (orange ↔ green ↔ blue)
    """

    _PALETTES = {
        "orange": COMFORT_ORANGE,
        "green":  COMFORT_GREEN,
        "blue":   COMFORT_BLUE,
    }
    _PALETTE_ORDER = ["orange", "green", "blue"]

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self.init_color_selector("orange")
        self._altitude = 0.0
        # Unità (default SI)
        self.init_units(ALTITUDE_UNITS, 0)

    # =========================================================================
    # UNITÀ DI MISURA
    # =========================================================================

    def update_data(self, data: TelemetryData):
        self._altitude = max(0.0, data.altitude)
        self.update()

    def _display_altitude(self) -> float:
        u = self.current_unit()
        if not u:
            return self._altitude
        return self._altitude * u.factor


    # =========================================================================
    # DISEGNO
    # =========================================================================

    def paint_background(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4

        # Bezel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bg_outer"])
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante
        dial_r = outer_r - 6
        p.setBrush(pal["bg_inner"])
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # Anello sottile
        p.setPen(QPen(pal["dim"], 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), dial_r - 1, dial_r - 1)

        # --- Tacche e numeri 0-9 ---
        tick_outer = dial_r - 5
        num_r = tick_outer - 22

        for i in range(10):
            angle_deg = i * 36.0

            # Tacca principale
            p.save()
            p.translate(cx, cy)
            p.rotate(angle_deg)
            p.setPen(QPen(pal["primary"], 2.5))
            p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + 16))
            p.restore()

            # Numero
            rad = math.radians(angle_deg)
            lx = cx + num_r * math.sin(rad)
            ly = cy - num_r * math.cos(rad)
            p.setPen(pal["bright"])
            nf = p.font()
            nf.setPixelSize(16)
            nf.setBold(True)
            nf.setFamily("Consolas")
            p.setFont(nf)
            p.drawText(QRectF(lx - 14, ly - 10, 28, 20),
                       Qt.AlignmentFlag.AlignCenter, str(i))

            # Tacche minori
            for m in range(1, 5):
                minor_angle = angle_deg + m * (36.0 / 5.0)
                p.save()
                p.translate(cx, cy)
                p.rotate(minor_angle)
                p.setPen(QPen(pal["faint"], 1.2))
                p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + 8))
                p.restore()

        # --- Titolo ---
        p.setPen(pal["dim"])
        tf = p.font()
        tf.setPixelSize(10)
        tf.setBold(True)
        p.setFont(tf)
        p.drawText(QRectF(cx - 50, cy + dial_r * 0.28, 100, 16),
                   Qt.AlignmentFlag.AlignCenter, "ALT")

        # --- Etichetta unità ---
        u = self.current_unit()
        caption = f"100 {u.label}" if u else ""
        p.setPen(pal["primary"])
        uf = p.font()
        uf.setPixelSize(9)
        uf.setBold(True)
        p.setFont(uf)
        p.drawText(QRectF(cx - 45, cy + dial_r * 0.48, 90, 14),
                   Qt.AlignmentFlag.AlignCenter, caption)

    def paint_foreground(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 10
        alt = self._display_altitude()

        # Angoli lancette
        hundreds = alt % 1000.0
        hundreds_angle = (hundreds / 1000.0) * 360.0
        thousands = alt % 10000.0
        thousands_angle = (thousands / 10000.0) * 360.0

        # --- Lancetta corta (migliaia) ---
        p.save()
        p.translate(cx, cy)
        p.rotate(thousands_angle)
        short_len = dial_r * 0.55
        short_needle = QPainterPath()
        short_needle.moveTo(0, -short_len)
        short_needle.lineTo(-5, 10)
        short_needle.lineTo(5, 10)
        short_needle.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["primary"])
        p.drawPath(short_needle)
        p.restore()

        # --- Lancetta lunga (centinaia) ---
        p.save()
        p.translate(cx, cy)
        p.rotate(hundreds_angle)
        long_len = dial_r - 16
        long_needle = QPainterPath()
        long_needle.moveTo(0, -long_len)
        long_needle.lineTo(-2.5, 14)
        long_needle.lineTo(2.5, 14)
        long_needle.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bright"])
        p.drawPath(long_needle)
        p.restore()

        # --- Mozzo centrale ---
        p.setPen(QPen(pal["dim"], 1))
        p.setBrush(pal["bg_outer"])
        p.drawEllipse(QPointF(cx, cy), 8, 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["primary"])
        p.drawEllipse(QPointF(cx, cy), 3, 3)

    # =========================================================================
    # MOUSE — selettore colore
    # =========================================================================

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.color_button_rect().contains(e.pos()):
                self._color_btn_pressed = True
                self._color_was_movable = bool(
                    self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                )
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                e.accept()
                self.update()
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._color_btn_pressed:
            self._color_btn_pressed = False
            if self._color_was_movable:
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            if self.color_button_rect().contains(e.pos()):
                self._cycle_palette()
            self.update()
            e.accept()
            return
        super().mouseReleaseEvent(e)

# =============================================================================
# VSI COMFORT — ANALOGICO
# =============================================================================

class VSIComfort(ColorSelectorMixin, UnitButtonsMixin, BaseInstrument):
    """
    Variometro analogico stile Comfort:
    - Scala UP/DOWN con 0 a ore 9
    - Escursione ±170°
    - Cambio unità: FT/MIN / M/S / FT/SEC (default M/S)
    - Cambio colore: selettore in basso a destra (orange ↔ green ↔ blue)
    """

    _PALETTES = {
        "orange": COMFORT_ORANGE,
        "green":  COMFORT_GREEN,
        "blue":   COMFORT_BLUE,
    }
    _PALETTE_ORDER = ["orange", "green", "blue"]
    _SWEEP_DEG = 170.0

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self.init_color_selector("orange")
        # Dati
        self._base_max_abs = 10.0
        self._base_value = 0.0
        self._value = 0.0
        # Scala
        self._max_abs = 2000.0
        self._major_step = 500.0
        self._unit_label = "FT/MIN"
        self._label_scale = 100.0
        # Unità (default SI)
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
        self._label_scale = 100.0 if u.unit_id == "fpm" else 1.0
        self._value = self._base_value * u.factor

    def update_data(self, data: TelemetryData):
        self._base_value = data.vertical_speed
        self._value = self._base_value * self.current_unit().factor
        self.update()

    def _value_to_rotation(self, v: float) -> float:
        n = v / max(1e-9, self._max_abs)
        n = max(-1.0, min(1.0, n))
        return 270.0 + n * self._SWEEP_DEG

    # =========================================================================
    # DISEGNO
    # =========================================================================

    def paint_background(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4

        # Bezel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bg_outer"])
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante
        dial_r = outer_r - 6
        p.setBrush(pal["bg_inner"])
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # Anello sottile
        p.setPen(QPen(pal["dim"], 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), dial_r - 1, dial_r - 1)

        # --- Tacche e numeri ---
        tick_outer = dial_r - 4
        major_len = 16
        minor_len = 9
        label_r = tick_outer - major_len - 14
        num_steps = int(round(self._max_abs / self._major_step))

        for i in range(num_steps + 1):
            val = i * self._major_step

            for sign in ([1] if i == 0 else [1, -1]):
                v = val * sign
                rot = self._value_to_rotation(v)

                # Tacca maggiore
                p.save()
                p.translate(cx, cy)
                p.rotate(rot)
                p.setPen(QPen(pal["primary"], 2.5))
                p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + major_len))
                p.restore()

                # Numero
                if i > 0 or sign == 1:
                    label_val = val / self._label_scale
                    rad = math.radians(rot)
                    lx = cx + label_r * math.sin(rad)
                    ly = cy - label_r * math.cos(rad)
                    p.setPen(pal["bright"])
                    nf = p.font()
                    nf.setPixelSize(13)
                    nf.setBold(True)
                    nf.setFamily("Consolas")
                    p.setFont(nf)
                    p.drawText(QRectF(lx - 16, ly - 8, 32, 16),
                               Qt.AlignmentFlag.AlignCenter, f"{label_val:.0f}")

            # Tacche minori
            if i < num_steps:
                for m in range(1, 3):
                    frac = m / 3.0

                    mv_pos = val + frac * self._major_step
                    rot_pos = self._value_to_rotation(mv_pos)
                    p.save()
                    p.translate(cx, cy)
                    p.rotate(rot_pos)
                    p.setPen(QPen(pal["faint"], 1.2))
                    p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + minor_len))
                    p.restore()

                    mv_neg = -(val + frac * self._major_step)
                    rot_neg = self._value_to_rotation(mv_neg)
                    p.save()
                    p.translate(cx, cy)
                    p.rotate(rot_neg)
                    p.setPen(QPen(pal["faint"], 1.2))
                    p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + minor_len))
                    p.restore()

        # --- Etichette UP / DOWN ---
        p.setPen(pal["dim"])
        tf = p.font()
        tf.setPixelSize(11.5)
        tf.setBold(True)
        p.setFont(tf)
        p.drawText(QRectF(cx - 50, cy - dial_r * 0.36, 40, 16),
                   Qt.AlignmentFlag.AlignCenter, "UP")
        p.drawText(QRectF(cx - 50, cy + dial_r * 0.20, 46, 16),
                   Qt.AlignmentFlag.AlignCenter, "DOWN")

        # --- Titolo ---
        tf2 = p.font()
        tf2.setPixelSize(8.5)
        tf2.setBold(True)
        p.setFont(tf2)
        p.setPen(pal["dim"])
        p.drawText(QRectF(cx - 55, cy - dial_r * 0.18, 110, 14),
                   Qt.AlignmentFlag.AlignCenter, "VERTICAL SPEED")

        # --- Etichetta unità ---
        p.setPen(pal["primary"])
        uf = p.font()
        uf.setPixelSize(8)
        uf.setBold(True)
        p.setFont(uf)
        p.drawText(QRectF(cx - 45, cy + dial_r * 0.08, 90, 12),
                   Qt.AlignmentFlag.AlignCenter, self._unit_label)

    def paint_foreground(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 10
        needle_len = dial_r - 18
        rot = self._value_to_rotation(self._value)

        # Lancetta
        p.save()
        p.translate(cx, cy)
        p.rotate(rot)
        nd = QPainterPath()
        nd.moveTo(0, -needle_len)
        nd.lineTo(-3.5, 12)
        nd.lineTo(3.5, 12)
        nd.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bright"])
        p.drawPath(nd)
        p.restore()

        # Mozzo centrale
        p.setPen(QPen(pal["dim"], 1))
        p.setBrush(pal["bg_outer"])
        p.drawEllipse(QPointF(cx, cy), 7, 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["primary"])
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)

    # =========================================================================
    # MOUSE — selettore colore
    # =========================================================================

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.color_button_rect().contains(e.pos()):
                self._color_btn_pressed = True
                self._color_was_movable = bool(
                    self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                )
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                e.accept()
                self.update()
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._color_btn_pressed:
            self._color_btn_pressed = False
            if self._color_was_movable:
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            if self.color_button_rect().contains(e.pos()):
                self._cycle_palette()
            self.update()
            e.accept()
            return
        super().mouseReleaseEvent(e)

# =============================================================================
# HEADING COMFORT — ANALOGICO
# =============================================================================

class HeadingComfort(ColorSelectorMixin,BaseInstrument):
    """
    Indicatore di prua (bussola) stile Comfort:
    - Rosa dei venti rotante
    - Tacche ogni 5°, numeri ogni 30°
    - Cardinali N/E/S/W evidenziati
    - Lubber line fissa in alto
    - Simbolo aereo fisso al centro
    - Cambio colore: selettore in basso a destra (orange ↔ green ↔ blue)
    """

    _PALETTES = {
        "orange": COMFORT_ORANGE,
        "green":  COMFORT_GREEN,
        "blue":   COMFORT_BLUE
    }
    _PALETTE_ORDER = ["orange", "green", "blue"]

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self.init_color_selector("orange")
        self._heading = 0.0

    def update_data(self, data: TelemetryData):
        self._heading = data.heading % 360.0
        self.update()


    # =========================================================================
    # DISEGNO
    # =========================================================================

    def paint_background(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4

        # Bezel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bg_outer"])
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante
        dial_r = outer_r - 6
        p.setBrush(pal["bg_inner"])
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # Anello sottile
        p.setPen(QPen(pal["dim"], 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), dial_r - 1, dial_r - 1)

    def paint_foreground(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4
        dial_r = outer_r - 6

        # --- Rosa dei venti (ruota con l'heading) ---
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), dial_r - 2, dial_r - 2)
        p.save()
        p.setClipPath(clip)
        p.save()
        p.translate(cx, cy)
        p.rotate(-self._heading)

        card_r = dial_r - 6

        # Tacche ogni 5°
        for deg in range(0, 360, 5):
            if deg % 30 == 0:
                tick_len, tick_w = 16, 2.5
                tick_color = pal["primary"]
            elif deg % 10 == 0:
                tick_len, tick_w = 12, 1.5
                tick_color = pal["dim"]
            else:
                tick_len, tick_w = 8, 1.2
                tick_color = pal["faint"]
            p.save()
            p.rotate(deg)
            p.setPen(QPen(tick_color, tick_w))
            p.drawLine(QPointF(0, -card_r), QPointF(0, -card_r + tick_len))
            p.restore()

        # Numeri e cardinali ogni 30°
        num_r = card_r - 26
        for deg in range(0, 360, 30):
            if deg == 0:
                label, is_cardinal = "N", True
            elif deg == 90:
                label, is_cardinal = "E", True
            elif deg == 180:
                label, is_cardinal = "S", True
            elif deg == 270:
                label, is_cardinal = "W", True
            else:
                label, is_cardinal = str(deg // 10), False

            p.save()
            p.rotate(deg)
            p.translate(0, -num_r)
            p.setPen(pal["bright"] if is_cardinal else pal["primary"])
            nf = p.font()
            nf.setPixelSize(16 if is_cardinal else 12)
            nf.setBold(True)
            nf.setFamily("Consolas")
            p.setFont(nf)
            p.drawText(QRectF(-14, -9, 28, 18),
                       Qt.AlignmentFlag.AlignCenter, label)
            p.restore()

        p.restore()  # fine rotazione rosa
        p.restore()  # fine clip

        # --- Lubber line (fissa in alto) ---
        p.save()
        p.translate(cx, cy)
        lub = QPainterPath()
        lub.moveTo(0, -dial_r + 4)
        lub.lineTo(-6, -dial_r + 16)
        lub.lineTo(6, -dial_r + 16)
        lub.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bright"])
        p.drawPath(lub)
        p.restore()

        # --- Simbolo aereo (fisso al centro) ---
        p.save()
        p.translate(cx, cy)
        p.setPen(QPen(pal["bright"], 2.5))
        p.drawLine(QPointF(0, -12), QPointF(0, 12))
        p.drawLine(QPointF(-14, -2), QPointF(14, -2))
        p.drawLine(QPointF(-6, 9), QPointF(6, 9))
        p.restore()

    # =========================================================================
    # MOUSE — selettore colore
    # =========================================================================

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.color_button_rect().contains(e.pos()):
                self._color_btn_pressed = True
                self._color_was_movable = bool(
                    self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                )
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                e.accept()
                self.update()
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._color_btn_pressed:
            self._color_btn_pressed = False
            if self._color_was_movable:
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            if self.color_button_rect().contains(e.pos()):
                self._cycle_palette()
            self.update()
            e.accept()
            return
        super().mouseReleaseEvent(e)

# =============================================================================
# TURN COORDINATOR COMFORT — ANALOGICO
# =============================================================================

class TurnCoordinatorComfort(ColorSelectorMixin,TurnTargetMixin, BaseInstrument):
    """
    Virosbandometro stile Comfort:
    - Aereo in miniatura che ruota con il turn_rate
    - Scala L/R con tacche
    - Lancetta di lettura
    - Inclinometro con pallina
    - Target turn rate regolabile (TurnTargetMixin)
    - Cambio colore: selettore in basso a destra (orange ↔ green ↔ blue)
    """

    _PALETTES = {
        "orange": COMFORT_ORANGE,
        "green":  COMFORT_GREEN,
        "blue":   COMFORT_BLUE
    }
    _PALETTE_ORDER = ["orange", "green", "blue"]

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self.init_color_selector("orange")
        self._turn_rate = 0.0
        self._roll = 0.0
        self.init_turn_target(3.0)
        # Selettore colore
        self._palette_key = "orange"
        self._palette = self._PALETTES[self._palette_key]
        self._color_btn_pressed = False
        self._color_was_movable = True

    def update_data(self, data: TelemetryData):
        self._turn_rate = data.turn_rate
        self._roll = data.roll
        self.update()

    # =========================================================================
    # SELETTORE COLORE (basso a destra)
    # =========================================================================

    def color_button_rect(self) -> QRectF:
        br = self.boundingRect()
        size = 18.0
        return QRectF(br.right() - size - 6.0, br.bottom() - size - 6.0, size, size)

    def _cycle_palette(self):
        idx = self._PALETTE_ORDER.index(self._palette_key)
        self._palette_key = self._PALETTE_ORDER[(idx + 1) % len(self._PALETTE_ORDER)]
        self._palette = self._PALETTES[self._palette_key]
        self._bg_cache = None
        self.update()

    def _paint_color_button(self, p: QPainter):
        r = self.color_button_rect()
        pal = self._palette

        p.setPen(QPen(pal["dim"], 1))
        p.setBrush(QColor(16, 16, 20, 235))
        p.drawEllipse(r)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["primary"])
        p.drawEllipse(r.adjusted(4, 4, -4, -4))

        if self._color_btn_pressed:
            p.setPen(QPen(pal["bright"], 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r.adjusted(1, 1, -1, -1))

    # =========================================================================
    # OVERRIDE PULSANTI TARGET (colori palette)
    # =========================================================================

    def paint_target_buttons(self, p: QPainter):
        pal = self._palette
        inc = self.target_inc_button_rect()
        dec = self.target_dec_button_rect()

        for r in (inc, dec):
            p.setPen(QPen(pal["dim"], 1))
            p.setBrush(QColor(16, 16, 20, 235))
            p.drawRoundedRect(r, 3, 3)

        # Frecce
        for rect, up in ((inc, True), (dec, False)):
            cx2 = rect.center().x()
            cy2 = rect.center().y()
            s = rect.width() * 0.28
            tri = QPainterPath()
            if up:
                tri.moveTo(cx2, cy2 - s)
                tri.lineTo(cx2 - s, cy2 + s * 0.7)
                tri.lineTo(cx2 + s, cy2 + s * 0.7)
            else:
                tri.moveTo(cx2, cy2 + s)
                tri.lineTo(cx2 - s, cy2 - s * 0.7)
                tri.lineTo(cx2 + s, cy2 - s * 0.7)
            tri.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal["bright"])
            p.drawPath(tri)

        # Readout target
        p.setPen(pal["primary"])
        rf = p.font()
        rf.setPixelSize(9)
        rf.setBold(True)
        p.setFont(rf)
        readout_rect = QRectF(inc.left() - 8, dec.bottom() + 3,
                              inc.width() + 16, 12)
        p.drawText(readout_rect, Qt.AlignmentFlag.AlignCenter,
                   f"{self._target_rate:.1f}")

    # =========================================================================
    # DISEGNO
    # =========================================================================

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        self._paint_color_button(painter)

    def paint_background(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4

        # Bezel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bg_outer"])
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante
        dial_r = outer_r - 6
        p.setBrush(pal["bg_inner"])
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # Anello sottile
        p.setPen(QPen(pal["dim"], 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), dial_r - 1, dial_r - 1)

        # --- Tacche scala bank angle ---
        tick_r = dial_r - 4
        for deg in [-30, -20, -10, 0, 10, 20, 30]:
            p.save()
            p.translate(cx, cy)
            p.rotate(deg)
            if deg == 0:
                tick_len, tick_w = 14, 2.5
                tick_color = pal["bright"]
            elif abs(deg) == 10:
                tick_len, tick_w = 10, 1.5
                tick_color = pal["primary"]
            else:
                tick_len, tick_w = 12, 2.0
                tick_color = pal["primary"]
            p.setPen(QPen(tick_color, tick_w))
            p.drawLine(QPointF(0, -tick_r), QPointF(0, -tick_r + tick_len))
            p.restore()

        # --- Etichette L e R ---
        p.setPen(pal["bright"])
        lf = p.font()
        lf.setPixelSize(16)
        lf.setBold(True)
        lf.setFamily("Consolas")
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

        # --- Titolo ---
        p.setPen(pal["dim"])
        tf = p.font()
        tf.setPixelSize(9)
        tf.setBold(True)
        p.setFont(tf)
        p.drawText(QRectF(cx - 60, cy + dial_r * 0.32, 120, 14),
                   Qt.AlignmentFlag.AlignCenter, "TURN COORDINATOR")

        # --- Etichetta "2 MIN" ---
        p.setPen(pal["faint"])
        uf = p.font()
        uf.setPixelSize(8)
        uf.setBold(False)
        p.setFont(uf)
        p.drawText(QRectF(cx - 30, cy + dial_r * 0.47, 60, 12),
                   Qt.AlignmentFlag.AlignCenter, "2 MIN")

        # --- Inclinometro (tubo) ---
        tube_bottom_y = cy + dial_r * 0.80
        tube_half_w = dial_r * 0.28
        tube_r = dial_r * 0.85
        tube_cy = tube_bottom_y - tube_r
        half_angle = math.degrees(math.asin(tube_half_w / tube_r))
        arc_rect = QRectF(cx - tube_r, tube_cy - tube_r, tube_r * 2, tube_r * 2)
        start_a = int((270 - half_angle) * 16)
        span_a = int(2 * half_angle * 16)

        # Corpo del tubo
        p.setPen(QPen(pal["dim"], 10,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect, start_a, span_a)

        # Bordi del tubo
        outer_rect = QRectF(cx - tube_r - 5, tube_cy - tube_r - 5,
                            (tube_r + 5) * 2, (tube_r + 5) * 2)
        inner_rect = QRectF(cx - tube_r + 5, tube_cy - tube_r + 5,
                            (tube_r - 5) * 2, (tube_r - 5) * 2)
        p.setPen(QPen(pal["faint"], 1))
        p.drawArc(outer_rect, start_a, span_a)
        p.drawArc(inner_rect, start_a, span_a)

        # Linee di riferimento
        ref_gap = 12
        p.setPen(QPen(pal["primary"], 1.5))
        p.drawLine(QPointF(cx - ref_gap / 2, tube_bottom_y - 5),
                   QPointF(cx - ref_gap / 2, tube_bottom_y + 5))
        p.drawLine(QPointF(cx + ref_gap / 2, tube_bottom_y - 5),
                   QPointF(cx + ref_gap / 2, tube_bottom_y + 5))

    def paint_foreground(self, p: QPainter):
        pal = self._palette
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 10

        # Tacche target turn rate (bug simmetrici)
        self.draw_target_ticks(p, cx, cy, dial_r - 4, color=pal["dim"])

        # Mappatura turn_rate → angolo display
        display_angle = self._turn_rate * (10.0 / 3.0)
        display_angle = max(-45.0, min(45.0, display_angle))

        # --- Aereo in miniatura ---
        p.save()
        p.translate(cx, cy)
        p.rotate(display_angle)
        wing_span = dial_r * 0.55
        p.setPen(QPen(pal["primary"], 3))
        p.drawLine(QPointF(-wing_span, 0), QPointF(-8, 0))
        p.drawLine(QPointF(8, 0), QPointF(wing_span, 0))
        p.drawLine(QPointF(-wing_span, 0), QPointF(-wing_span, 6))
        p.drawLine(QPointF(wing_span, 0), QPointF(wing_span, 6))
        p.drawLine(QPointF(0, -7), QPointF(0, 7))
        p.drawLine(QPointF(-5, 7), QPointF(5, 7))
        p.setBrush(pal["primary"])
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0, 0), 3, 3)
        p.restore()

        # --- Lancetta di lettura scala ---
        p.save()
        p.translate(cx, cy)
        p.rotate(display_angle)
        needle_len = dial_r - 12
        needle = QPainterPath()
        needle.moveTo(0, -needle_len)
        needle.lineTo(-3, 8)
        needle.lineTo(3, 8)
        needle.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal["bright"])
        p.drawPath(needle)
        p.restore()

        # --- Pallina inclinometro ---
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

        p.setPen(QPen(pal["primary"], 1))
        p.setBrush(pal["bright"])
        p.drawEllipse(QPointF(ball_x, ball_y), 5.0, 5.0)

    # =========================================================================
    # MOUSE — selettore colore + target (chain)
    # =========================================================================

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.color_button_rect().contains(e.pos()):
                self._color_btn_pressed = True
                self._color_was_movable = bool(
                    self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                )
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                e.accept()
                self.update()
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._color_btn_pressed:
            self._color_btn_pressed = False
            if self._color_was_movable:
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            if self.color_button_rect().contains(e.pos()):
                self._cycle_palette()
            self.update()
            e.accept()
            return
        super().mouseReleaseEvent(e)


