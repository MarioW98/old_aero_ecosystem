from __future__ import annotations
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from .base import BaseInstrument
from ..core.telemetry import TelemetryData


class CircularGauge(BaseInstrument):
    # Palette interna dello strumento (non dipende dal tema)
    _BEZEL_COLOR = QColor(40, 40, 45)
    _BEZEL_RING_COLOR = QColor(30, 30, 34)
    _DIAL_COLOR = QColor(20, 22, 28)
    _TICK_MAJOR_COLOR = QColor(220, 220, 220)
    _TICK_MINOR_COLOR = QColor(160, 160, 160)
    _TICK_MAJOR_WIDTH = 2.0
    _TICK_MINOR_WIDTH = 1.0
    _TEXT_COLOR = QColor(220, 220, 220)
    _TEXT_SECONDARY_COLOR = QColor(180, 190, 200)
    _TEXT_TERTIARY_COLOR = QColor(140, 150, 160)
    _NEEDLE_COLOR = QColor(255, 255, 255)
    _NEEDLE_HUB_COLOR = QColor(90, 90, 95)

    def __init__(self, proto, parent=None):
        super().__init__(proto, parent)
        self._value = 0.0
        self._min_val = 0.0
        self._max_val = 100.0
        self._major_step = 20.0
        self._minor_per_major = 4
        self._unit_label = ""
        self._label_format = "{:.0f}"

    def value_to_rotation(self, v: float) -> float:
        n = (v - self._min_val) / max(1e-9, self._max_val - self._min_val)
        return -135.0 + max(0.0, min(1.0, n)) * 270.0

    def update_data(self, data: TelemetryData):
        pass

    def paint_background(self, p):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        outer_r = min(cx, cy) - 4

        # Bezel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._BEZEL_COLOR)
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Quadrante
        dial_r = outer_r - 6
        p.setBrush(self._DIAL_COLOR)
        p.setPen(QPen(self._BEZEL_RING_COLOR, 3))
        p.drawEllipse(QPointF(cx, cy), dial_r, dial_r)

        # Tacche e numeri
        tick_outer = dial_r - 4
        nm = int((self._max_val - self._min_val) / self._major_step) + 1
        for i in range(nm):
            val = self._min_val + i * self._major_step
            rot = self.value_to_rotation(val)
            p.save()
            p.translate(cx, cy)
            p.rotate(rot)
            p.setPen(QPen(self._TICK_MAJOR_COLOR, self._TICK_MAJOR_WIDTH))
            p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + 14))
            p.restore()

            # Numero
            rad = math.radians(rot)
            lx = cx + (tick_outer - 22) * math.sin(rad)
            ly = cy - (tick_outer - 22) * math.cos(rad)
            p.setPen(self._TEXT_COLOR)
            p.drawText(QRectF(lx - 16, ly - 8, 32, 16),
                       Qt.AlignmentFlag.AlignCenter, f"{val:.0f}")

            # Tacche minori
            if i < nm - 1:
                for m in range(1, self._minor_per_major + 1):
                    mv = val + m * (self._major_step / self._minor_per_major)
                    mr = self.value_to_rotation(mv)
                    p.save()
                    p.translate(cx, cy)
                    p.rotate(mr)
                    p.setPen(QPen(self._TICK_MINOR_COLOR, self._TICK_MINOR_WIDTH))
                    p.drawLine(QPointF(0, -tick_outer), QPointF(0, -tick_outer + 8))
                    p.restore()

        # Titolo
        p.setPen(self._TEXT_SECONDARY_COLOR)
        p.drawText(QRectF(cx - 50, cy + 20, 100, 16),
                   Qt.AlignmentFlag.AlignCenter, self._prototype.display_name)

        # Etichetta unità
        p.setPen(self._TEXT_TERTIARY_COLOR)
        p.drawText(QRectF(cx - 40, cy + 40, 80, 14),
                   Qt.AlignmentFlag.AlignCenter, self._unit_label)

    def paint_foreground(self, p):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        dial_r = min(cx, cy) - 10

        rot = self.value_to_rotation(self._value)
        p.save()
        p.translate(cx, cy)
        p.rotate(rot)

        # Lancetta
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._NEEDLE_COLOR)
        needle = QPainterPath()
        needle.moveTo(0, -dial_r + 14)
        needle.lineTo(-4, 8)
        needle.lineTo(4, 8)
        needle.closeSubpath()
        p.drawPath(needle)
        p.restore()

        # Mozzo
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._NEEDLE_HUB_COLOR)
        p.drawEllipse(QPointF(cx, cy), 6, 6)