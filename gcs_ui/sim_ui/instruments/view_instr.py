from __future__ import annotations

import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen, QFont
)

from .base import BaseInstrument, UnitButtonsMixin
from ..core.telemetry import TelemetryData
from ..core.units import AIRSPEED_UNITS, ALTITUDE_UNITS, unit_index


class AirspeedTape(UnitButtonsMixin, BaseInstrument):
    """Anemometro a nastro verticale (stile PFD digitale)."""

    _VS0 = 40
    _VS1 = 50
    _VNO = 120
    _VNE = 160


    _TAPE_STEPS = {
        "kt":  (5.0, 10.0),
        "kmh": (10.0, 20.0),
        "mph": (5.0, 10.0),
        "ms":  (2.5, 5.0),
    }

    def _tape_steps(self):
        u = self.current_unit()
        uid = u.unit_id if u else "ms"
        return self._TAPE_STEPS.get(uid, (5.0, 10.0))

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._airspeed = 0.0
        self._px_per_unit = 2.2
        self.init_units(AIRSPEED_UNITS, unit_index(AIRSPEED_UNITS, "M/S"))

    def update_data(self, data: TelemetryData):
        self._airspeed = data.airspeed
        self.update()

    def paint_background(self, p: QPainter):
        p.setRenderHints(QPainter.RenderHint.Antialiasing |
                         QPainter.RenderHint.TextAntialiasing)
        w, h = self._prototype.width, self._prototype.height
        p.setPen(QPen(QColor(60, 60, 65), 2))
        p.setBrush(QBrush(QColor(15, 15, 18,180)))
        p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 8, 8)

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cy = h / 2

        u = self.current_unit()
        factor = u.factor if u else 1.0
        px_per_unit = self._px_per_unit / factor
        speed = self._airspeed * factor
        minor_step, major_step = self._tape_steps()
        ratio = int(round(major_step / minor_step))

        tape_w = w - 16
        tape_h = h - 40
        tape_x = 8
        tape_y = 20
        tape_rect = QRectF(tape_x, tape_y, tape_w, tape_h)

        def v_y(v_base: float) -> float:
            return cy - (v_base * factor - speed) * px_per_unit

        p.save()
        clip_path = QPainterPath()
        clip_path.addRect(tape_rect)
        p.setClipPath(clip_path)

        arc_w = 4
        arc_x = tape_x + tape_w - arc_w - 2

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 180))
        p.drawRect(QRectF(arc_x, v_y(self._VNO), arc_w,
                          v_y(self._VS0) - v_y(self._VNO)))

        p.setBrush(QColor(0, 220, 120, 180))
        p.drawRect(QRectF(arc_x, v_y(self._VNO), arc_w,
                          v_y(self._VS1) - v_y(self._VNO)))

        p.setBrush(QColor(255, 200, 0, 180))
        p.drawRect(QRectF(arc_x, v_y(self._VNE), arc_w,
                          v_y(self._VNO) - v_y(self._VNE)))

        pf = QFont("Consolas", 11)
        pf.setBold(True)
        p.setFont(pf)

        half_range = (tape_h / 2) / px_per_unit + major_step
        start_i = int(math.floor((speed - half_range) / minor_step))
        end_i = int(math.ceil((speed + half_range) / minor_step))

        for i in range(start_i, end_i + 1):
            v = i * minor_step
            if v < 0:
                continue
            y = cy - (v - speed) * px_per_unit

            if i % ratio == 0:
                p.setPen(QPen(QColor(255, 255, 255), 2))
                p.drawLine(QPointF(tape_x + tape_w - 8, y),
                           QPointF(tape_x + tape_w - 2, y))
                p.setPen(QColor(255, 255, 255))
                p.drawText(QRectF(tape_x + 4, y - 10, tape_w - 20, 20),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           f"{v:.0f}")
            else:
                p.setPen(QPen(QColor(200, 200, 200), 1.5))
                p.drawLine(QPointF(tape_x + tape_w - 6, y),
                           QPointF(tape_x + tape_w - 2, y))

        vne_y = v_y(self._VNE)
        p.setPen(QPen(QColor(255, 50, 50), 2.5))
        p.drawLine(QPointF(arc_x - 6, vne_y), QPointF(arc_x + arc_w + 2, vne_y))

        p.restore()

        readout_w = tape_w - 10
        readout_h = 28
        readout_x = tape_x + (tape_w - readout_w) / 2
        readout_y = cy - readout_h / 2

        p.setPen(QPen(QColor(255, 180, 0), 2))
        p.setBrush(QBrush(QColor(5, 5, 8, 240)))
        p.drawRoundedRect(QRectF(readout_x, readout_y, readout_w, readout_h), 4, 4)

        vf = QFont("Consolas", 16)
        vf.setBold(True)
        p.setFont(vf)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(readout_x, readout_y, readout_w, readout_h),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{speed:.0f}")

        if u:
            lbl_w = 40.0
            lbl_h = 14
            lbl_x = tape_x + (tape_w - lbl_w) / 2
            lbl_y = tape_rect.bottom() + 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(5, 5, 8, 200))
            p.drawRoundedRect(QRectF(lbl_x, lbl_y, lbl_w, lbl_h), 3, 3)
            uf = QFont("Consolas", 9)
            uf.setBold(True)
            p.setFont(uf)
            p.setPen(QColor(0, 220, 120))
            p.drawText(QRectF(lbl_x, lbl_y, lbl_w, lbl_h),
                       Qt.AlignmentFlag.AlignCenter, u.label)


class AltimeterTape(UnitButtonsMixin, BaseInstrument):
    """Altimetro a nastro verticale (stile PFD digitale)."""

    _TAPE_STEPS = {
        "METERS": (50.0, 100.0),
        "FEET":   (100.0, 500.0),
    }

    def _tape_steps(self):
        u = self.current_unit()
        label = u.label if u else "METERS"
        return self._TAPE_STEPS.get(label, (50.0, 100.0))

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._altitude = 0.0
        self._px_per_unit = 0.8
        self.init_units(ALTITUDE_UNITS, unit_index(ALTITUDE_UNITS, "METERS"))

    def update_data(self, data: TelemetryData):
        self._altitude = data.altitude
        self.update()

    def paint_background(self, p: QPainter):
        p.setRenderHints(QPainter.RenderHint.Antialiasing |
                         QPainter.RenderHint.TextAntialiasing)
        w, h = self._prototype.width, self._prototype.height
        p.setPen(QPen(QColor(60, 60, 65), 2))
        p.setBrush(QBrush(QColor(15, 15, 18, 180)))
        p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 8, 8)

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cy = h / 2

        u = self.current_unit()
        factor = u.factor if u else 1.0
        px_per_unit = self._px_per_unit / factor
        alt = self._altitude * factor
        minor_step, major_step = self._tape_steps()
        ratio = int(round(major_step / minor_step))

        tape_w = w - 16
        tape_h = h - 40
        tape_x = 8
        tape_y = 20
        tape_rect = QRectF(tape_x, tape_y, tape_w, tape_h)

        def alt_y(alt_base: float) -> float:
            return cy - (alt_base * factor - alt) * px_per_unit

        p.save()
        clip_path = QPainterPath()
        clip_path.addRect(tape_rect)
        p.setClipPath(clip_path)

        pf = QFont("Consolas", 11)
        pf.setBold(True)
        p.setFont(pf)

        half_range = (tape_h / 2) / px_per_unit + major_step
        start_i = int(math.floor((alt - half_range) / minor_step))
        end_i = int(math.ceil((alt + half_range) / minor_step))

        for i in range(start_i, end_i + 1):
            v = i * minor_step
            if v < 0:
                continue
            y = cy - (v - alt) * px_per_unit

            if i % ratio == 0:
                p.setPen(QPen(QColor(255, 255, 255), 2))
                p.drawLine(QPointF(tape_x + tape_w - 8, y),
                           QPointF(tape_x + tape_w - 2, y))
                p.setPen(QColor(255, 255, 255))
                p.drawText(QRectF(tape_x + 4, y - 10, tape_w - 20, 20),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           f"{v:.0f}")
            else:
                p.setPen(QPen(QColor(200, 200, 200), 1.5))
                p.drawLine(QPointF(tape_x + tape_w - 6, y),
                           QPointF(tape_x + tape_w - 2, y))

        p.restore()

        readout_w = tape_w - 10
        readout_h = 28
        readout_x = tape_x + (tape_w - readout_w) / 2
        readout_y = cy - readout_h / 2

        p.setPen(QPen(QColor(255, 180, 0), 2))
        p.setBrush(QBrush(QColor(5, 5, 8, 240)))
        p.drawRoundedRect(QRectF(readout_x, readout_y, readout_w, readout_h), 4, 4)

        vf = QFont("Consolas", 16)
        vf.setBold(True)
        p.setFont(vf)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(readout_x, readout_y, readout_w, readout_h),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{alt:.0f}")

        if u:
            lbl_w = 40.0
            lbl_h = 14
            lbl_x = tape_x + (tape_w - lbl_w) / 2
            lbl_y = tape_rect.bottom() + 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(5, 5, 8, 200))
            p.drawRoundedRect(QRectF(lbl_x, lbl_y, lbl_w, lbl_h), 3, 3)
            uf = QFont("Consolas", 9)
            uf.setBold(True)
            p.setFont(uf)
            p.setPen(QColor(0, 220, 120))
            p.drawText(QRectF(lbl_x, lbl_y, lbl_w, lbl_h),
                       Qt.AlignmentFlag.AlignCenter, u.label)

class HeadingTape(BaseInstrument):
    """
    Bussola a nastro orizzontale (stile PFD digitale / sottomarino).
    Il nastro scorre orizzontalmente con wrap-around a 360°.
    """

    # Etichette cardinali
    _CARDINAL = {
        0: "N", 45: "NE", 90: "E", 135: "SE",
        180: "S", 225: "SW", 270: "W", 315: "NW",
    }

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._heading = 0.0
        self._px_per_deg = 3.0  # pixel per grado

    def update_data(self, data: TelemetryData):
        self._heading = data.heading % 360.0
        self.update()

    def paint_background(self, p: QPainter):
        p.setRenderHints(QPainter.RenderHint.Antialiasing |
                         QPainter.RenderHint.TextAntialiasing)
        w, h = self._prototype.width, self._prototype.height
        p.setPen(QPen(QColor(60, 60, 65), 2))
        p.setBrush(QBrush(QColor(15, 15, 18,180)))
        p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 8, 8)

    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx = w / 2
        cy = h / 2

        # Area tape
        tape_w = w - 16
        tape_h = h - 24
        tape_x = 8
        tape_y = 4
        tape_rect = QRectF(tape_x, tape_y, tape_w, tape_h)

        # --- Clipping ---
        p.save()
        clip_path = QPainterPath()
        clip_path.addRect(tape_rect)
        p.setClipPath(clip_path)

        # --- Tacche e numeri ---
        pf = QFont("Consolas", 10)
        pf.setBold(True)
        p.setFont(pf)

        # Calcolo range visibile con wrap-around
        half_range = (tape_w / 2) / self._px_per_deg + 10
        start_deg = int(self._heading - half_range)
        end_deg = int(self._heading + half_range)

        for deg in range(start_deg, end_deg + 1):
            # Wrap-around
            deg_mod = deg % 360
            offset = deg - self._heading
            x = cx + offset * self._px_per_deg

            # Tacche ogni 5°
            if deg_mod % 5 == 0:
                if deg_mod % 10 == 0:
                    # Tacca maggiore
                    p.setPen(QPen(QColor(255, 255, 255), 2))
                    p.drawLine(QPointF(x, tape_rect.bottom() - 2),
                               QPointF(x, tape_rect.bottom() - 12))

                    # Etichetta: cardinale o numero
                    if deg_mod in self._CARDINAL:
                        label = self._CARDINAL[deg_mod]
                        p.setPen(QColor(0, 220, 120))  # Verde per cardinali
                        p.drawText(QRectF(x - 15, tape_y + 2, 30, 16),
                                   Qt.AlignmentFlag.AlignCenter, label)
                    else:
                        label = f"{deg_mod:03d}"
                        p.setPen(QColor(255, 255, 255))
                        p.drawText(QRectF(x - 15, tape_y + 2, 30, 16),
                                   Qt.AlignmentFlag.AlignCenter, label)
                else:
                    # Tacca minore
                    p.setPen(QPen(QColor(200, 200, 200), 1.5))
                    p.drawLine(QPointF(x, tape_rect.bottom() - 2),
                               QPointF(x, tape_rect.bottom() - 8))

        p.restore()

        # --- Readout digitale centrale (in basso) ---
        readout_w = 50
        readout_h = 20
        readout_x = cx - readout_w / 2
        readout_y = tape_rect.bottom() - 6

        p.setPen(QPen(QColor(255, 180, 0), 2))
        p.setBrush(QBrush(QColor(5, 5, 8, 180)))
        p.drawRoundedRect(QRectF(readout_x, readout_y, readout_w, readout_h), 4, 4)

        vf = QFont("Consolas", 13)
        vf.setBold(True)
        p.setFont(vf)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(readout_x, readout_y, readout_w, readout_h),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{self._heading:03.0f}°")

        # --- Indicatore triangolare in alto (punta verso il nastro) ---
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 180, 0))
        triangle = QPainterPath()
        triangle.moveTo(cx, tape_y + 10)
        triangle.lineTo(cx - 6, tape_y - 5)
        triangle.lineTo(cx + 6, tape_y - 5)
        triangle.closeSubpath()
        p.drawPath(triangle)




