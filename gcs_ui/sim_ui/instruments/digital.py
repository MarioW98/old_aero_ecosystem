from __future__ import annotations
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from .base import BaseInstrument, UnitButtonsMixin
from ..core.telemetry import TelemetryData
from ..core.units import ALTITUDE_UNITS, VSI_UNITS, unit_index


# =============================================================================
# DIGITAL ALTIMETER
# =============================================================================

class DigitalAltimeter(UnitButtonsMixin, BaseInstrument):
    """
    Altimetro digitale compatto con cambio unità:
    FEET → METERS
    """

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._altitude = 0.0
        self._prev_altitude = 0.0
        self._px_per_step = 24.0
        self._step = 100.0
        self.init_units(ALTITUDE_UNITS, unit_index(ALTITUDE_UNITS, "METERS"))

    def update_data(self, data: TelemetryData):
        self._prev_altitude = self._altitude
        self._altitude = max(0.0, data.altitude)
        self.update()

    def _display_altitude(self) -> float:
        u = self.current_unit()
        if not u:
            return self._altitude
        return self._altitude * u.factor

    def _display_prev_altitude(self) -> float:
        u = self.current_unit()
        if not u:
            return self._prev_altitude
        return self._prev_altitude * u.factor

    def paint_background(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(40, 40, 45))
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 8, 8)
        painter.setBrush(QColor(20, 22, 28))
        painter.drawRoundedRect(QRectF(4, 4, w - 8, h - 8), 5, 5)

    def paint_foreground(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        tape_top = 6
        tape_bottom = h - 6
        tape_cy = (tape_top + tape_bottom) / 2
        alt = self._display_altitude()
        prev_alt = self._display_prev_altitude()

        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(
            QRectF(5, tape_top, w - 10, tape_bottom - tape_top), 4, 4
        )
        painter.setClipPath(clip)

        base_alt = int(alt / self._step) * self._step
        for offset in range(-5, 6):
            alt_value = base_alt + offset * self._step
            if alt_value < 0:
                continue
            y_pos = tape_cy - (alt_value - alt) / self._step * self._px_per_step
            if y_pos < tape_top - 16 or y_pos > tape_bottom + 16:
                continue
            distance = abs(offset)
            if distance <= 1:
                alpha, font_size = 200, 12
            elif distance <= 2:
                alpha, font_size = 120, 11
            else:
                alpha, font_size = 60, 10
            painter.setPen(QColor(220, 220, 220, alpha))
            nf = painter.font()
            nf.setPixelSize(font_size)
            nf.setFamily("Consolas")
            painter.setFont(nf)
            painter.drawText(
                QRectF(4, y_pos - 7, w - 18, 14),
                Qt.AlignmentFlag.AlignCenter,
                str(int(alt_value))
            )
        painter.restore()

        box_w = w - 14
        box_h = 32
        box_x = 7
        box_y = tape_cy - box_h / 2
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.setBrush(QBrush(QColor(35, 38, 45)))
        painter.drawRoundedRect(QRectF(box_x, box_y, box_w, box_h), 4, 4)

        painter.setPen(QColor(255, 255, 255))
        vf = painter.font()
        vf.setPixelSize(22)
        vf.setBold(True)
        vf.setFamily("Consolas")
        painter.setFont(vf)
        painter.drawText(
            QRectF(box_x, box_y, box_w, box_h),
            Qt.AlignmentFlag.AlignCenter,
            f"{int(alt)}"
        )

        delta = alt - prev_alt
        if abs(delta) > 0.5:
            tri_x = w - 11
            tri_y = tape_cy + 25
            tri_size = 5
            if delta > 0.5:
                tri_color = QColor(100, 220, 120)
            elif delta < -0.5:
                tri_color = QColor(240, 130, 100)
            else:
                tri_color = QColor(255, 255, 255)
            tri = QPainterPath()
            if delta > 0:
                tri.moveTo(tri_x, tri_y - tri_size)
                tri.lineTo(tri_x - tri_size, tri_y + tri_size)
                tri.lineTo(tri_x + tri_size, tri_y + tri_size)
            else:
                tri.moveTo(tri_x, tri_y + tri_size)
                tri.lineTo(tri_x - tri_size, tri_y - tri_size)
                tri.lineTo(tri_x + tri_size, tri_y - tri_size)
            tri.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tri_color)
            painter.drawPath(tri)


# =============================================================================
# DIGITAL VSI
# =============================================================================

class DigitalVSI(UnitButtonsMixin, BaseInstrument):
    """
    Variometro digitale compatto con:
    - Numero grande con segno
    - Nastro scorrevole
    - Triangolo direzionale
    - Cambio unità (FT/MIN / M/S / FT/S)
    """

    _THRESHOLDS = {
        "ms":   0.1,       # m/s (base SI)
        "fpm":  10.0,      # ft/min
        "fps":  0.3,       # ft/s
    }

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._vsi = 0.0
        self._prev_vsi = 0.0
        self._px_per_step = 20.0
        self._step = 200.0
        self._decimals = 0
        self._threshold = 10.0
        self.init_units(VSI_UNITS, unit_index(VSI_UNITS, "M/S"))
        self._apply_step()

    def _on_unit_changed(self):
        self._apply_step()
        super()._on_unit_changed()

    def _apply_step(self):
        u = self.current_unit()
        if not u:
            return
        if u.unit_id == "ms":
            self._step = 1.0        # m/s
        elif u.unit_id == "fpm":
            self._step = 200.0      # ft/min
        else:
            self._step = 5.0        # ft/s
        self._decimals = u.decimals
        self._threshold = self._THRESHOLDS.get(u.unit_id, 0.1)

    def update_data(self, data: TelemetryData):
        self._prev_vsi = self._vsi
        self._vsi = data.vertical_speed
        self.update()

    def _display_vsi(self) -> float:
        u = self.current_unit()
        if not u:
            return self._vsi
        return self._vsi * u.factor

    def _display_prev_vsi(self) -> float:
        u = self.current_unit()
        if not u:
            return self._prev_vsi
        return self._prev_vsi * u.factor

    def paint_background(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(40, 40, 45))
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 8, 8)
        painter.setBrush(QColor(20, 22, 28))
        painter.drawRoundedRect(QRectF(4, 4, w - 8, h - 8), 5, 5)

    def paint_foreground(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        tape_top = 6
        tape_bottom = h - 6
        tape_cy = (tape_top + tape_bottom) / 2
        vsi = self._display_vsi()

        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(5, tape_top, w - 10, tape_bottom - tape_top), 4, 4)
        painter.setClipPath(clip)

        base_val = round(vsi / self._step) * self._step
        for offset in range(-5, 6):
            tape_value = base_val + offset * self._step
            y_pos = tape_cy - (tape_value - vsi) / self._step * self._px_per_step
            if y_pos < tape_top - 16 or y_pos > tape_bottom + 16:
                continue
            distance = abs(offset)
            if distance <= 1:
                alpha, font_size = 180, 11
            elif distance <= 2:
                alpha, font_size = 110, 10
            else:
                alpha, font_size = 55, 9
            painter.setPen(QColor(220, 220, 220, alpha))
            nf = painter.font()
            nf.setPixelSize(font_size)
            nf.setFamily("Consolas")
            painter.setFont(nf)
            painter.drawText(
                QRectF(4, y_pos - 7, w - 18, 14),
                Qt.AlignmentFlag.AlignCenter,
                f"{int(tape_value)}"
            )
        painter.restore()

        box_w = w - 14
        box_h = 30
        box_x = 7
        box_y = tape_cy - box_h / 2
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.setBrush(QBrush(QColor(35, 38, 45)))
        painter.drawRoundedRect(QRectF(box_x, box_y, box_w, box_h), 4, 4)

        if vsi > self._threshold:
            text_color = QColor(100, 220, 120)
        elif vsi < -self._threshold:
            text_color = QColor(240, 130, 100)
        else:
            text_color = QColor(255, 255, 255)

        painter.setPen(text_color)
        vf = painter.font()
        vf.setPixelSize(18)
        vf.setBold(True)
        vf.setFamily("Consolas")
        painter.setFont(vf)
        sign = "+" if vsi >= 0 else ""
        painter.drawText(
            QRectF(box_x, box_y, box_w, box_h),
            Qt.AlignmentFlag.AlignCenter,
            f"{sign}{vsi:.{self._decimals}f}"
        )

        u = self.current_unit()
        painter.setPen(QColor(140, 150, 160))
        uf = painter.font()
        uf.setPixelSize(8)
        uf.setBold(False)
        painter.setFont(uf)
        painter.drawText(
            QRectF(0, h - 16, w, 12),
            Qt.AlignmentFlag.AlignCenter,
            u.label if u else ""
        )

        if abs(vsi) > self._threshold:
            tri_x = w - 11
            tri_y = tape_cy - 20
            tri_size = 5
            tri = QPainterPath()
            if vsi > 0:
                tri.moveTo(tri_x, tri_y - tri_size)
                tri.lineTo(tri_x - tri_size, tri_y + tri_size)
                tri.lineTo(tri_x + tri_size, tri_y + tri_size)
            else:
                tri.moveTo(tri_x, tri_y + tri_size)
                tri.lineTo(tri_x - tri_size, tri_y - tri_size)
                tri.lineTo(tri_x + tri_size, tri_y - tri_size)
            tri.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(text_color)
            painter.drawPath(tri)