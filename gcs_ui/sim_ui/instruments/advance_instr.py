from __future__ import annotations
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen,
    QLinearGradient, QRadialGradient, QFont,
)
from .base import BaseInstrument, UnitButtonsMixin
from ..core.telemetry import TelemetryData
from ..core.units import AIRSPEED_UNITS, ALTITUDE_UNITS, unit_index
from ..core.map_renderer import MapRenderer

# =============================================================================
# GARMIN GI 275 — ATTITUDE INDICATOR AVANZATO (High Fidelity Style)
# =============================================================================
class AttitudeAdvance(UnitButtonsMixin, BaseInstrument):
    """
    Orizzonte artificiale avanzato ispirato al Garmin GI 275:
    - Display rettangolare con angoli arrotondati
    - Sfera cielo/terra con gradienti realistici
    - Scala beccheggio numerata (tacche 5°, numeri 10°)
    - Arco rollio con tacche (0, ±10, ±20, ±30, ±45, ±60)
    - Puntatore rollio ambra
    - Simbolo aereo fisso (chevron)
    - Indicatore slip/skid
    - Tape velocità (airspeed) a sinistra con archi operativi
    - Readout digitali pitch, roll e airspeed
    """

    # --- Archi operativi velocità (valori generici, regolabili) ---
    _VS0 = 40    # Stall speed flaps down (inizio arco bianco)
    _VS1 = 50    # Stall speed flaps up (inizio arco verde)
    _VNO = 120   # Max structural cruising speed (fine verde / inizio giallo)
    _VNE = 160   # Never exceed speed (linea rossa)

    # --- Passi tacche tape per unità: (minor, major) in unità visualizzate ---
    _TAPE_STEPS = {
        "KNOTS": (5.0, 10.0),
        "KM/H":  (10.0, 20.0),
        "MPH":   (5.0, 10.0),
        "M/S":   (2.5, 5.0),
    }

    def _tape_steps(self):
        u = self.current_unit()
        label = u.label if u else "KNOTS"
        return self._TAPE_STEPS.get(label, (5.0, 10.0))

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._pitch = 0.0
        self._roll = 0.0
        self._turn_rate = 0.0
        self._airspeed = 0.0
        self._px_per_deg = 3.5   # pixel per grado di beccheggio
        self._px_per_kt = 2.2    # pixel per nodo di velocità
        self.init_units(AIRSPEED_UNITS, unit_index(AIRSPEED_UNITS, "M/S"))

    def update_data(self, data: TelemetryData):
        self._pitch = data.pitch
        self._roll = data.roll
        self._turn_rate = getattr(data, "turn_rate", 0.0)
        self._airspeed = getattr(data, "airspeed", 0.0)
        self.update()

    # =========================================================================
    # PULSANTI UNITÀ — riposizionati in alto a sinistra
    # =========================================================================

    def unit_round_button_rect(self) -> QRectF:
        br = self.boundingRect()
        size = 16.0
        return QRectF(br.left() + 6.0, br.top() + 6.0, size, size)

    def unit_menu_button_rect(self) -> QRectF:
        r = self.unit_round_button_rect()
        w = 12.0
        return QRectF(r.center().x() - w / 2, r.bottom() + 4.0, w, 8.0)



    # =========================================================================
    # GEOMETRIA COMUNI
    # =========================================================================
    def _display_rect(self):
        w, h = self._prototype.width, self._prototype.height
        m = 10
        return QRectF(m, m, w - 2 * m, h - 2 * m)

    # =========================================================================
    # SFONDO STATICO (Bezel e Cornice)
    # =========================================================================
    def paint_background(self, p: QPainter):
        p.setRenderHints(QPainter.RenderHint.Antialiasing | 
                         QPainter.RenderHint.TextAntialiasing | 
                         QPainter.RenderHint.SmoothPixmapTransform)

        w, h = self._prototype.width, self._prototype.height
        corner = 16

        # --- Bezel esterno con gradiente ---
        bezel_grad = QRadialGradient(w / 2, h / 2, max(w, h) / 1.5)
        bezel_grad.setColorAt(0.0, QColor(60, 60, 65))
        bezel_grad.setColorAt(0.8, QColor(30, 30, 35))
        bezel_grad.setColorAt(1.0, QColor(15, 15, 18))
        
        p.setPen(QPen(QColor(80, 80, 85), 1))
        p.setBrush(QBrush(bezel_grad))
        p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), corner, corner)

        # --- Cornice display interna ---
        m3 = 10
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(5, 5, 8))
        p.drawRoundedRect(QRectF(m3, m3, w - 2 * m3, h - 2 * m3), corner - 4, corner - 4)

        # --- Etichetta modo "ATT" ---
        p.setPen(QColor(0, 220, 120))
        lf = p.font()
        lf.setPixelSize(10)
        lf.setBold(True)
        p.setFont(lf)
        p.drawText(QRectF(w - m3 - 48, m3 + 6, 40, 14),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "ATT")

    # =========================================================================
    # PRIMO PIANO DINAMICO
    # =========================================================================
    def paint_foreground(self, p: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2
        disp = self._display_rect()
        corner = 12
        att_r = (min(w, h) / 2) - 20

        # =====================================================================
        # 1. SFERA CIELO/TERRA + SCALA BECCHEGGIO (clippata al display)
        # =====================================================================
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(disp, corner, corner)
        p.setClipPath(clip)
        p.translate(cx, cy)
        p.rotate(-self._roll)
        pitch_offset = self._pitch * self._px_per_deg
        large = max(w, h) * 2

        # Cielo
        sky_grad = QLinearGradient(0, -large + pitch_offset, 0, pitch_offset)
        sky_grad.setColorAt(0.0, QColor(10, 40, 100))
        sky_grad.setColorAt(0.7, QColor(40, 110, 200))
        sky_grad.setColorAt(1.0, QColor(80, 150, 230))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(sky_grad))
        p.drawRect(QRectF(-large, -large + pitch_offset, large * 2, large))

        # Terra
        gnd_grad = QLinearGradient(0, pitch_offset, 0, large + pitch_offset)
        gnd_grad.setColorAt(0.0, QColor(140, 90, 40))
        gnd_grad.setColorAt(0.3, QColor(100, 60, 20))
        gnd_grad.setColorAt(1.0, QColor(50, 30, 10))
        p.setBrush(QBrush(gnd_grad))
        p.drawRect(QRectF(-large, pitch_offset, large * 2, large))

        # Linea orizzonte
        p.setPen(QPen(QColor(255, 255, 255), 2.5))
        p.drawLine(QPointF(-large, pitch_offset), QPointF(large, pitch_offset))

        # --- Scala beccheggio ---
        pf = p.font()
        pf.setPixelSize(11)
        pf.setBold(True)
        p.setFont(pf)

        for deg in range(-30, 35, 5):
            if deg == 0:
                continue
            y = pitch_offset - deg * self._px_per_deg
            
            if deg % 10 == 0:
                half_w = 35
                pen_style = Qt.PenStyle.SolidLine
                is_numbered = True
            else:
                half_w = 18
                pen_style = Qt.PenStyle.DashLine
                is_numbered = False

            p.setPen(QPen(QColor(255, 255, 255), 2.0, pen_style))
            p.drawLine(QPointF(-half_w, y), QPointF(half_w, y))

            if is_numbered:
                label = str(abs(deg))
                p.setPen(QColor(255, 255, 255))
                p.drawText(QRectF(-half_w - half_w/2, y - 8, 20, 16),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
                p.drawText(QRectF(half_w + half_w/2-20, y - 8, 20, 16),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        p.restore()

        # =====================================================================
        # 2. ARCO ROLLIO (fisso, sopra la sfera)
        # =====================================================================
        p.save()
        p.setPen(QPen(QColor(255, 255, 255), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        arc_rect = QRectF(cx - att_r, cy - att_r, att_r * 2, att_r * 2)
        p.drawArc(arc_rect, 30 * 16, 120 * 16)

        roll_marks = [0, 10, 20, 30, 45, 60]
        for angle in roll_marks:
            signs = [1] if angle == 0 else [1, -1]
            for sign in signs:
                deg = angle * sign
                p.save()
                p.translate(cx, cy)
                p.rotate(deg)
                
                if angle == 0:
                    tl, tw = 14, 3.0
                elif angle in (10, 20, 30):
                    tl, tw = 10, 2.0
                else:
                    tl, tw = 12, 2.0
                    
                p.setPen(QPen(QColor(255, 255, 255), tw))
                p.drawLine(QPointF(0, -att_r), QPointF(0, -att_r + tl))
                p.restore()
        p.restore()

        # Riferimento zero rollio
        p.save()
        p.translate(cx, cy)
        zero = QPainterPath()
        zero.moveTo(0, -att_r + 16)
        zero.lineTo(-6, -att_r + 2)
        zero.lineTo(6, -att_r + 2)
        zero.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawPath(zero)
        p.restore()

        # =====================================================================
        # 3. PUNTATORE ROLLIO (ambra, ruota con il roll)
        # =====================================================================
        p.save()
        p.translate(cx, cy)
        p.rotate(self._roll)
        ptr = QPainterPath()
        ptr.moveTo(0, -att_r + 18)
        ptr.lineTo(-7, -att_r + 32)
        ptr.lineTo(7, -att_r + 32)
        ptr.closeSubpath()
        
        p.setPen(QPen(QColor(180, 120, 0), 1.5))
        p.setBrush(QColor(255, 180, 0))
        p.drawPath(ptr)
        p.restore()

        # =====================================================================
        # 4. SIMBOLO AEREO (Chevron ambra)
        # =====================================================================
        p.save()
        p.translate(cx, cy)
        
        sym_color = QColor(255, 180, 0)
        p.setPen(QPen(sym_color, 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)

        wings = QPainterPath()
        wing_span = att_r * 0.45
        wing_drop = att_r * 0.08
        center_gap = att_r * 0.12
        
        wings.moveTo(-center_gap, 0)
        wings.lineTo(-wing_span, wing_drop)
        wings.moveTo(center_gap, 0)
        wings.lineTo(wing_span, wing_drop)
        
        p.drawPath(wings)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sym_color)
        p.drawEllipse(QPointF(0, 0), 4, 4)
        p.restore()

        # =====================================================================
        # 5. TAPE VELOCITÀ (Airspeed) - Lato sinistro
        # =====================================================================
        self._draw_airspeed_tape(p, disp, cy)

        # =====================================================================
        # 6. SLIP/SKID
        # =====================================================================
        coordinated_rate = self._roll * 0.16
        slip_skid = self._turn_rate - coordinated_rate
        slip_px = max(-20, min(20, slip_skid * 4.0))

        p.save()
        p.translate(cx, cy)
        
        track_rect = QRectF(-24, att_r * 0.18, 48, 8)
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(track_rect, 3, 3)

        skid_rect = QRectF(slip_px - 6, att_r * 0.18 + 1, 12, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 20, 20))
        p.drawRoundedRect(skid_rect, 2, 2)
        p.restore()

        # =====================================================================
        # 7. READOUT DIGITALI (Pitch e Roll in basso)
        # =====================================================================
        self._draw_readout(p, disp.left() + 17, disp.bottom() - 30, "Pitch", self._pitch)
        self._draw_readout(p, disp.right() - 73, disp.bottom() - 30, "Roll", self._roll)

    # =========================================================================
    # TAPE VELOCITÀ (Airspeed Tape) - Integrata nel bordo sinistro
    # =========================================================================
    # def _draw_airspeed_tape(self, p: QPainter, disp: QRectF, cy: float):
    #     """Disegna la tape della velocità integrata nel bordo sinistro stile GI 275."""
    #     tape_w = 28 
    #     tape_h = disp.height() * 0.35 # Altezza numeri che scorrono
    #     tape_x = disp.left()        # Posizione x
    #     tape_y = cy - tape_h / 2 -4   # Posizione y
        
    #     tape_rect = QRectF(tape_x, tape_y, tape_w, tape_h)
        
    #     # --- Sfondo tape (nero solido, integrato nel display) ---
    #     p.save()
    #     p.setPen(Qt.PenStyle.NoPen)  # Nessun bordo visibile
    #     p.setBrush(QBrush(QColor(8, 8, 10, 150)))  # Scuro trasparente
    #     p.drawRect(tape_rect)  # Rettangolo semplice, non arrotondato
        
    #     # --- Clipping per evitare overflow ---
    #     clip_path = QPainterPath()
    #     clip_path.addRect(tape_rect)
    #     p.setClipPath(clip_path)
        
    #     # --- Archi operativi colorati (lato destro della tape) ---
    #     arc_w = 3  
    #     arc_x = tape_x + tape_w - arc_w - 1
        
    #     # Bianco (VS0 to VNO)
    #     white_top = cy - (self._VNO - self._airspeed) * self._px_per_kt
    #     white_bot = cy - (self._VS0 - self._airspeed) * self._px_per_kt
    #     p.setPen(Qt.PenStyle.NoPen)
    #     p.setBrush(QColor(255, 255, 255, 180))
    #     p.drawRect(QRectF(arc_x, white_top, arc_w, white_bot - white_top))
        
    #     # Verde (VS1 to VNO)
    #     green_top = cy - (self._VNO - self._airspeed) * self._px_per_kt
    #     green_bot = cy - (self._VS1 - self._airspeed) * self._px_per_kt
    #     p.setBrush(QColor(0, 220, 120, 180))
    #     p.drawRect(QRectF(arc_x, green_top, arc_w, green_bot - green_top))
        
    #     # Giallo (VNO to VNE)
    #     yellow_top = cy - (self._VNE - self._airspeed) * self._px_per_kt
    #     yellow_bot = cy - (self._VNO - self._airspeed) * self._px_per_kt
    #     p.setBrush(QColor(255, 200, 0, 180))
    #     p.drawRect(QRectF(arc_x, yellow_top, arc_w, yellow_bot - yellow_top))
        
    #     # Linea rossa a VNE messa dopo
        
    #     # --- Tacche e numeri ---
    #     min_kt = int(self._airspeed - 50)
    #     max_kt = int(self._airspeed + 50)
    #     min_kt = max(0, min_kt - (min_kt % 10))
    #     max_kt = max_kt + (10 - max_kt % 10)
        
    #     pf = p.font()
    #     pf.setPixelSize(8)  # Ridotto da 12 a 11
    #     pf.setBold(True)
    #     pf.setFamily("Consolas")
    #     p.setFont(pf)
        
    #     for kt in range(min_kt, max_kt + 1, 5):
    #         y = cy - (kt - self._airspeed) * self._px_per_kt
            
    #         if kt % 10 == 0:
    #             tick_len = 8  # Ridotto da 10 a 8
    #             p.setPen(QPen(QColor(255, 255, 255), 1.8))
    #             p.drawLine(QPointF(tape_x + tape_w - 6, y), 
    #                       QPointF(tape_x + tape_w - 3, y))
                
    #             # Numero (posizionato più a sinistra per stare nella tape più stretta)
    #             p.setPen(QColor(255, 255, 255))
    #             p.drawText(QRectF(tape_x + 6, y - 7, tape_w - 14, 14),
    #                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    #                       str(kt))
    #         else:
    #             tick_len = 5  # Ridotto da 6 a 5
    #             p.setPen(QPen(QColor(200, 200, 200), 1.2))
    #             p.drawLine(QPointF(tape_x + tape_w - 4, y), 
    #                       QPointF(tape_x + tape_w - 2, y))


    #     # Linea rossa a VNE
    #     vne_y = cy - (self._VNE - self._airspeed) * self._px_per_kt
    #     p.setPen(QPen(QColor(255, 50, 50), 2.0))
    #     p.drawLine(QPointF(arc_x - 4, vne_y), QPointF(arc_x + arc_w + 1, vne_y))   
        
    #     p.restore()
        
    #     # --- Readout digitale centrale (ridimensionato per tape più stretta) ---
    #     readout_w = 34 
    #     readout_h = 20  # Ridotto da 22 a 20
    #     readout_x = tape_x + (tape_w - readout_w) / 2
    #     readout_y = cy - readout_h / 2
        
    #     # Sfondo nero con bordo ambra
    #     p.setPen(QPen(QColor(255, 180, 0), 1.8))  # Bordo più sottile
    #     p.setBrush(QBrush(QColor(5, 5, 8, 240)))
    #     p.drawRoundedRect(QRectF(readout_x, readout_y, readout_w, readout_h), 3, 3)
        
    #     # Valore velocità
    #     vf = p.font()
    #     vf.setPixelSize(12)  # Ridotto da 14 a 13
    #     vf.setBold(True)
    #     vf.setFamily("Consolas")
    #     p.setFont(vf)
    #     p.setPen(QColor(255, 255, 255))
    #     p.drawText(QRectF(readout_x, readout_y, readout_w, readout_h),
    #               Qt.AlignmentFlag.AlignCenter,
    #               f"{self._airspeed:.0f}")

    def _draw_airspeed_tape(self, p: QPainter, disp: QRectF, cy: float):
        """Tape velocità con supporto cambio unità (KNOTS/KM-H/MPH/M-S)."""
        u = self.current_unit()
        factor = u.factor if u else 1.0
        # Scala inversamente proporzionale al fattore: la tape mostra
        # sempre lo stesso intervallo FISICO di velocità, solo rinumerato
        px_per_unit = self._px_per_kt / factor
        speed = self._airspeed * factor
        minor_step, major_step = self._tape_steps()
        ratio = int(round(major_step / minor_step))

        tape_w = 28
        tape_h = disp.height() * 0.35
        tape_x = disp.left()
        tape_y = cy - tape_h / 2 - 4
        tape_rect = QRectF(tape_x, tape_y, tape_w, tape_h)

        def v_y(v_base: float) -> float:
            """Posizione y di una velocità espressa in nodi (unità base)."""
            return cy - (v_base * factor - speed) * px_per_unit

        # --- Sfondo tape ---
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(8, 8, 10, 150)))
        p.drawRect(tape_rect)

        clip_path = QPainterPath()
        clip_path.addRect(tape_rect)
        p.setClipPath(clip_path)

        # --- Archi operativi (V-speed convertite automaticamente) ---
        arc_w = 3
        arc_x = tape_x + tape_w - arc_w - 1

        # Bianco (VS0 → VNO)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 180))
        p.drawRect(QRectF(arc_x, v_y(self._VNO), arc_w,
                          v_y(self._VS0) - v_y(self._VNO)))

        # Verde (VS1 → VNO)
        p.setBrush(QColor(0, 220, 120, 180))
        p.drawRect(QRectF(arc_x, v_y(self._VNO), arc_w,
                          v_y(self._VS1) - v_y(self._VNO)))

        # Giallo (VNO → VNE)
        p.setBrush(QColor(255, 200, 0, 180))
        p.drawRect(QRectF(arc_x, v_y(self._VNE), arc_w,
                          v_y(self._VNO) - v_y(self._VNE)))

        # --- Tacche e numeri ---
        pf = p.font()
        pf.setPixelSize(8)
        pf.setBold(True)
        pf.setFamily("Consolas")
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
                # Tacca maggiore + numero
                p.setPen(QPen(QColor(255, 255, 255), 1.8))
                p.drawLine(QPointF(tape_x + tape_w - 6, y),
                           QPointF(tape_x + tape_w - 3, y))
                p.setPen(QColor(255, 255, 255))
                p.drawText(QRectF(tape_x + 2, y - 7, tape_w - 10, 14),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           f"{v:.0f}")
            else:
                # Tacca minore
                p.setPen(QPen(QColor(200, 200, 200), 1.2))
                p.drawLine(QPointF(tape_x + tape_w - 4, y),
                           QPointF(tape_x + tape_w - 2, y))

        # --- Linea rossa VNE ---
        vne_y = v_y(self._VNE)
        p.setPen(QPen(QColor(255, 50, 50), 2.0))
        p.drawLine(QPointF(arc_x - 4, vne_y), QPointF(arc_x + arc_w + 1, vne_y))
        p.restore()

        # --- Readout digitale centrale ---
        readout_w = 34
        readout_h = 20
        readout_x = tape_x + (tape_w - readout_w) / 2
        readout_y = cy - readout_h / 2

        p.setPen(QPen(QColor(255, 180, 0), 1.8))
        p.setBrush(QBrush(QColor(5, 5, 8, 240)))
        p.drawRoundedRect(QRectF(readout_x, readout_y, readout_w, readout_h), 3, 3)

        vf = p.font()
        vf.setPixelSize(12)
        vf.setBold(True)
        vf.setFamily("Consolas")
        p.setFont(vf)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(readout_x, readout_y, readout_w, readout_h),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{speed:.0f}")

        # --- Etichetta unità sotto la tape ---
        if u:
            lbl_w = 30.0
            lbl_x = tape_x + (tape_w - lbl_w) / 2
            lbl_y = tape_rect.bottom() + 3
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(5, 5, 8, 200))
            p.drawRoundedRect(QRectF(lbl_x, lbl_y, lbl_w, 11), 2, 2)
            uf = p.font()
            uf.setPixelSize(7)
            uf.setBold(True)
            p.setFont(uf)
            p.setPen(QColor(0, 220, 120))
            p.drawText(QRectF(lbl_x, lbl_y, lbl_w, 11),
                       Qt.AlignmentFlag.AlignCenter, u.label)



    def _draw_readout(self, p: QPainter, x: float, y: float,
                      label: str, value: float):
        """Disegna un piccolo readout digitale con etichetta e valore."""
        box = QRectF(x, y, 56, 18)

        # Sfondo scuro con bordo sottile
        p.setPen(QPen(QColor(80, 80, 85), 1))
        p.setBrush(QBrush(QColor(15, 15, 18, 220)))
        p.drawRoundedRect(box, 4, 4)

        # Etichetta (verde fosforescente)
        p.setPen(QColor(0, 220, 120))
        lf = p.font()
        lf.setPixelSize(8)
        lf.setBold(True)
        p.setFont(lf)
        p.drawText(QRectF(x + 2, y, 20, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   label)
        # Valore (bianco, font monospace)          
        p.setPen(QColor(255, 255, 255))
        vf = p.font()
        vf.setPixelSize(9.5)
        vf.setBold(True)
        vf.setFamily("Consolas")
        p.setFont(vf)
        p.drawText(QRectF(x + 25, y, 30, 18),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{value:+.1f}°")

# =============================================================================
# PRIMARY FLIGHT DISPLAY (G500/G600 style)
# =============================================================================

class PrimaryFlightDisplay(BaseInstrument):
    """
    Primary Flight Display ispirato al Gulfstream G500/G600.
    Dimensioni: 960×720 (formato 4:3)
    
    Features:
    - Attitude indicator centrale
    - Airspeed tape (sinistra) con cambio unità
    - Altitude tape (destra)
    - Roll indicator, boresight, aircraft symbol
    """

    # Colori PFD (fissi, non usano il tema)
    _SKY_COLOR = QColor(20, 60, 140)
    _GROUND_COLOR = QColor(90, 50, 20)
    _HORIZON_COLOR = QColor(255, 255, 255)
    _PITCH_LADDER_COLOR = QColor(255, 255, 255)
    _AIRCRAFT_SYMBOL_COLOR = QColor(255, 180, 0)  # Ambra
    _BORESIGHT_COLOR = QColor(255, 255, 255)
    _BEZEL_COLOR = QColor(10, 10, 12)
    _TAPE_BG = QColor(0, 0, 0, 180)
    _TAPE_BORDER = QColor(255, 255, 255, 100)
    _UNIT_BTN_COLOR = QColor(40, 40, 45, 220)
    _UNIT_BTN_BORDER = QColor(255, 126, 0)  # Ambra

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._pitch = 0.0
        self._roll = 0.0
        self._airspeed = 0.0  # m/s (SI)
        self._altitude = 0.0  # m (SI)
        self._heading = 0.0 # gradi
        self._px_per_deg = 6.0
        
        # Airspeed tape
        self._tape_width = 45
        self._px_per_unit = 8.0  # pixel per unità (m/s)
        
        # Gestione unità
        self._units = AIRSPEED_UNITS
        self._unit_idx = 0  # Inizia con M/S (indice 0)
        self._unit_btn_rect = QRectF()  # Rettangolo del pulsante per hit-test
        
        # Altitude tape
        self._px_per_foot = 0.5

        # Gestione unità altitudine
        self._altitude_units = ALTITUDE_UNITS
        self._altitude_unit_idx = 0  # Inizia con METERS (indice 0)
        self._altitude_btn_rect = QRectF()  # Rettangolo pulsante altitudine

        
        # Geometria arco bussola (centro sotto il bordo => curvatura dolce)
        self._hdg_center_below = 170   # quanto il centro sta sotto h
        self._hdg_radius = 320         # raggio bordo esterno
        self._hdg_band = 50            # spessore nastro
        self._hdg_span = 50            # ± gradi visibili

    def update_data(self, data: TelemetryData):
        self._pitch = data.pitch
        self._roll = data.roll
        self._airspeed = data.airspeed
        self._altitude = data.altitude
        self._heading = data.heading       
        self.update()

    def _current_unit(self):
        """Restituisce l'unità corrente."""
        return self._units[self._unit_idx]

    def _next_unit(self):
        """Passa all'unità successiva ciclicamente."""
        self._unit_idx = (self._unit_idx + 1) % len(self._units)
        self.update()

    def _current_altitude_unit(self):
        """Restituisce l'unità corrente per l'altitudine."""
        return self._altitude_units[self._altitude_unit_idx]

    def _next_altitude_unit(self):
        """Passa all'unità successiva per l'altitudine."""
        self._altitude_unit_idx = (self._altitude_unit_idx + 1) % len(self._altitude_units)
        self.update()
        
    def unit_state(self) -> dict:
        """Restituisce lo stato serializzabile delle unità correnti (airspeed + altitude)."""
        airspeed_unit = self._current_unit()
        altitude_unit = self._current_altitude_unit()
        return {
            "airspeed_unit": airspeed_unit.unit_id if airspeed_unit else "ms",
            "altitude_unit": altitude_unit.unit_id if altitude_unit else "m",
        }

    def restore_unit_state(self, state: dict):
        """Ripristina le unità da uno stato salvato."""
        # Ripristina airspeed
        airspeed_id = state.get("airspeed_unit")
        if airspeed_id:
            for idx, u in enumerate(self._units):
                if u.unit_id == airspeed_id:
                    self._unit_idx = idx
                    break
        
        # Ripristina altitude
        altitude_id = state.get("altitude_unit")
        if altitude_id:
            for idx, u in enumerate(self._altitude_units):
                if u.unit_id == altitude_id:
                    self._altitude_unit_idx = idx
                    break
        
        self.update()
    def mousePressEvent(self, event):
        """Gestisce il click sui pulsanti unità."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._unit_btn_rect.contains(event.pos()):
                self._next_unit()
                event.accept()
                return
            if self._altitude_btn_rect.contains(event.pos()):
                self._next_altitude_unit()
                event.accept()
                return
        super().mousePressEvent(event)

    # =========================================================================
    # DISEGNO
    # =========================================================================

    def paint_background(self, painter: QPainter):
        """Disegna il bezel nero del PFD."""
        w, h = self._prototype.width, self._prototype.height
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._BEZEL_COLOR)
        painter.drawRect(0, 0, w, h)

    def paint_foreground(self, painter: QPainter):
        """Disegna l'attitude indicator + airspeed tape + altitude tape."""
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.TextAntialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        w, h = self._prototype.width, self._prototype.height
        cx = w / 2
        cy = h / 2

        # --- 1. ATTITUDE INDICATOR (con clipping) ---
        painter.save()
        clip_path = QPainterPath()
        clip_path.addRect(0, 0, w, h)
        painter.setClipPath(clip_path)

        # Rotazione e pitch
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._roll)
        pitch_offset = self._pitch * self._px_per_deg

        # Cielo e terra
        large = max(w, h) * 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._SKY_COLOR)
        painter.drawRect(QRectF(-large, -large + pitch_offset, large * 2, large))
        painter.setBrush(self._GROUND_COLOR)
        painter.drawRect(QRectF(-large, pitch_offset, large * 2, large))

        # Linea orizzonte
        painter.setPen(QPen(self._HORIZON_COLOR, 2))
        painter.drawLine(QPointF(-large, pitch_offset), QPointF(large, pitch_offset))

        # Pitch ladder
        painter.setPen(QPen(self._PITCH_LADDER_COLOR, 1))
        font = painter.font()
        font.setPixelSize(14)
        font.setBold(True)
        font.setFamily("Consolas")
        painter.setFont(font)

        for deg in range(-90, 95, 5):
            if deg == 0:
                continue
            y_pos = pitch_offset - deg * self._px_per_deg
            if y_pos < -large or y_pos > large:
                continue

            if deg % 10 == 0:
                half_w = 50
                draw_number = True
            else:
                half_w = 25
                draw_number = False

            painter.drawLine(QPointF(-half_w, y_pos), QPointF(half_w, y_pos))

            if draw_number:
                label = str(abs(deg))
                painter.setPen(self._PITCH_LADDER_COLOR)
                painter.drawText(QRectF(-half_w - 30, y_pos - 8, 28, 16),
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
                painter.drawText(QRectF(half_w + 2, y_pos - 8, 28, 16),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
                painter.setPen(QPen(self._PITCH_LADDER_COLOR, 1))

        painter.restore()  # Fine rotazione

        # Zero pitch reference line
        painter.setPen(QPen(self._HORIZON_COLOR, 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(cx - 80, cy), QPointF(cx + 80, cy))

        painter.restore()  # Fine clipping

        # --- 2. AIRSPEED TAPE ---
        self._draw_airspeed_tape(painter, cx, cy, h)

        # --- 3. ALTITUDE TAPE ---
        self._draw_altitude_tape(painter, cx, cy, h)

        # --- HEADING ARC (basso) ---
        self._draw_heading_arc(painter, cx, cy, h)

        # --- 4. AIRCRAFT SYMBOL ---
        painter.save()
        painter.translate(cx, cy)
        painter.setPen(QPen(self._AIRCRAFT_SYMBOL_COLOR, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(-60, 0), QPointF(-20, 0))
        painter.drawLine(QPointF(20, 0), QPointF(60, 0))
        painter.setBrush(self._AIRCRAFT_SYMBOL_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 4, 4)
        painter.restore()

        # --- 5. BORESIGHT ---
        painter.save()
        painter.translate(cx, cy)
        boresight_y = -h / 2 + 40
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._BORESIGHT_COLOR)
        triangle = QPainterPath()
        triangle.moveTo(0, boresight_y)
        triangle.lineTo(-8, boresight_y - 12)
        triangle.lineTo(8, boresight_y - 12)
        triangle.closeSubpath()
        painter.drawPath(triangle)
        painter.restore()

        # --- 6. ROLL INDICATOR ---
        painter.save()
        painter.translate(cx, cy)
        arc_radius = h / 2 - 30
        painter.setPen(QPen(self._HORIZON_COLOR, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc_rect = QRectF(-arc_radius, -arc_radius, arc_radius * 2, arc_radius * 2)
        painter.drawArc(arc_rect, 30 * 16, 120 * 16)
        
        roll_marks = [0, 10, 20, 30, 45, 60]
        for angle in roll_marks:
            signs = [1] if angle == 0 else [1, -1]
            for sign in signs:
                deg = angle * sign
                painter.save()
                painter.rotate(deg)
                if angle == 0:
                    tick_len = 12
                    tick_w = 2
                elif angle in (10, 20, 30):
                    tick_len = 8
                    tick_w = 1.5
                else:
                    tick_len = 10
                    tick_w = 1.5
                painter.setPen(QPen(self._HORIZON_COLOR, tick_w))
                painter.drawLine(QPointF(0, -arc_radius), QPointF(0, -arc_radius + tick_len))
                painter.restore()
        painter.restore()
    
    # =========================================================================
    # AIRSPEED TAPE CON PULSANTE UNITÀ
    # =========================================================================

    def _draw_airspeed_tape(self, painter: QPainter, cx: float, cy: float, h: float):
        """Disegna la tape dell'airspeed con pulsante cambio unità."""
        w = self._tape_width
        left = 0
        top = 0
        
        # Unità corrente e fattore di conversione
        unit = self._current_unit()
        factor = unit.factor  # es. 1.0 per M/S, 1.94384 per KNOTS
        
        # Valore convertito per la visualizzazione
        airspeed_display = self._airspeed * factor
        
        # Scala adattata: mantieni la stessa scala fisica
        px_per_display_unit = self._px_per_unit / factor
        
        # Offset per centrare il valore attuale al centro verticale
        offset = cy - airspeed_display * px_per_display_unit
        
        # Sfondo nero semi-trasparente
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._TAPE_BG)
        painter.drawRect(QRectF(left, top, w, h))
        
        # Bordo destro
        painter.setPen(QPen(self._TAPE_BORDER, 1))
        painter.drawLine(QPointF(w, top), QPointF(w, h))
        
        # Clip alla zona tape
        clip_path = QPainterPath()
        clip_path.addRect(QRectF(left, top, w, h))
        painter.save()
        painter.setClipPath(clip_path)
        
        # Tacche e numeri
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        font.setFamily("Consolas")
        painter.setFont(font)
        
        # Calcola range visibile
        visible_range = (h / 2) / px_per_display_unit
        start_val = int((airspeed_display - visible_range) / 5) * 5
        end_val = int((airspeed_display + visible_range) / 5) * 5
        
        # Disegna le tacche
        step = 5
        for val in range(start_val, end_val + 1, step):
            y = cy - (val - airspeed_display) * px_per_display_unit
            
            if y < top - 20 or y > h + 20:
                continue
            
            is_major = (val % 10 == 0) and (val >= 0)
            
            if is_major:
                # Tacca maggiore
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.drawLine(QPointF(w - 10, y), QPointF(w, y))
                
                # Numero
                painter.setPen(QColor(255, 255, 255,100))
                painter.drawText(QRectF(13, y - 10, w - 25, 20),
                               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                               str(val))
            else:
                # Tacca minore
                painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
                painter.drawLine(QPointF(w - 10, y), QPointF(w, y))
        
        painter.restore()
        
        # Readout digitale AL CENTRO
        readout_h = 35
        readout_y = cy - readout_h / 2
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(QColor(0, 0, 0, 220))
        painter.drawRect(QRectF(5, readout_y, w - 10, readout_h))
        
        font.setPixelSize(15)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(5, readout_y, w - 10, readout_h),
                        Qt.AlignmentFlag.AlignCenter,
                        f"{int(airspeed_display)}")
        
        # --- PULSANTE UNITÀ (sopra il readout) ---
        btn_w = 36
        btn_h = 16
        btn_x = (w - btn_w) / 2
        btn_y = h - btn_h - 8 
        self._unit_btn_rect = QRectF(btn_x, btn_y, btn_w, btn_h)
        
        painter.setPen(QPen(self._UNIT_BTN_BORDER, 1.5))
        painter.setBrush(self._UNIT_BTN_COLOR)
        painter.drawRoundedRect(QRectF(btn_x, btn_y, btn_w, btn_h), 3, 3)
        
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QColor(255, 126, 0))
        painter.drawText(QRectF(btn_x, btn_y, btn_w, btn_h),
                        Qt.AlignmentFlag.AlignCenter, unit.label)
        

    # =========================================================================
    # ALTITUDE TAPE
    # =========================================================================

    def _draw_altitude_tape(self, painter: QPainter, cx: float, cy: float, h: float):
        """Disegna la tape dell'altitudine sul lato destro con pulsante cambio unità."""
        w = self._tape_width + 10
        left = self._prototype.width - w
        top = 0
        
        # Unità corrente e fattore di conversione
        unit = self._current_altitude_unit()
        factor = unit.factor  # 1.0 per METERS, 3.28084 per FEET
        
        # Valore convertito per la visualizzazione
        altitude_display = self._altitude * factor
        
        # Scala adattata
        px_per_display_unit = self._px_per_foot / factor
        
        # Offset per centrare il valore attuale al centro verticale
        offset = cy - altitude_display * px_per_display_unit
        
        # Sfondo nero semi-trasparente
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._TAPE_BG)
        painter.drawRect(QRectF(left, top, w, h))
        
        # Bordo sinistro
        painter.setPen(QPen(self._TAPE_BORDER, 1))
        painter.drawLine(QPointF(left, top), QPointF(left, h))
        
        # Clip alla zona tape
        clip_path = QPainterPath()
        clip_path.addRect(QRectF(left, top, w, h))
        painter.save()
        painter.setClipPath(clip_path)
        
        # Tacche e numeri
        font = painter.font()
        font.setPixelSize(12)
        font.setBold(True)
        font.setFamily("Consolas")
        painter.setFont(font)
        
        # Calcola range visibile
        visible_range = (h / 2) / px_per_display_unit
        start_val = int((altitude_display - visible_range) / 50) * 50
        end_val = int((altitude_display + visible_range) / 50) * 50
        
        # Disegna da start_val a end_val
        for val in range(start_val, end_val + 1, 50):
            y = cy - (val - altitude_display) * px_per_display_unit
            
            if y < top - 20 or y > h + 20:
                continue
            
            is_major = (val % 100 == 0) and (val >= 0)
            
            if is_major:
                # Tacca maggiore
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.drawLine(QPointF(left, y), QPointF(left + 10, y))
                
                # Numero
                painter.setPen(QColor(255, 255, 255,100))
                painter.drawText(QRectF(left + 12, y - 10, w - 27, 20),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                               str(val))
            else:
                # Tacca minore
                painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
                painter.drawLine(QPointF(left, y), QPointF(left + 10, y))
        
        painter.restore()
        
        # Readout digitale AL CENTRO
        readout_h = 35
        readout_y = cy - readout_h / 2
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(QColor(0, 0, 0, 220))
        painter.drawRect(QRectF(left + 5, readout_y, w - 10, readout_h))
        
        font.setPixelSize(15)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(left + 5, readout_y, w - 10, readout_h),
                        Qt.AlignmentFlag.AlignCenter,
                        f"{int(altitude_display)}")
        
        # --- PULSANTE UNITÀ IN BASSO (al posto dell'etichetta) ---
        btn_w = 40
        btn_h = 16
        btn_x = left + (w - btn_w) / 2
        btn_y = h - btn_h - 8
        self._altitude_btn_rect = QRectF(btn_x, btn_y, btn_w, btn_h)
        
        painter.setPen(QPen(QColor(255, 126, 0), 1.5))
        painter.setBrush(QColor(40, 40, 45, 220))
        painter.drawRoundedRect(QRectF(btn_x, btn_y, btn_w, btn_h), 3, 3)
        
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QColor(255, 126, 0))
        painter.drawText(QRectF(btn_x, btn_y, btn_w, btn_h),
                        Qt.AlignmentFlag.AlignCenter, unit.label)


    # =========================================================================
    # HEADING INDICATOR
    # =========================================================================


    def _draw_heading_arc(self, painter: QPainter, cx: float, cy: float, h: float):
        """Arco bussola in basso. Autonomo: disattiva il clip, quantizza, normalizza il wrap."""
        painter.save()
        painter.setClipping(False)          # ← nessuna eredità di clip dalle tape/attitude
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r_out = float(self._hdg_radius)
        band  = float(self._hdg_band)
        r_in  = r_out - band
        span  = float(self._hdg_span)
        arc_cx = float(cx)
        arc_cy = float(h) + float(self._hdg_center_below)   # centro fuori dal bordo basso

        # In Qt: 0°=3 o'clock, CCW+, 90°=alto. rel=0 -> alto (sotto il lubber).
        start_qt = 90.0 - span
        span_qt  = 2.0 * span

        # --- Banda (tratto spesso, capi piatti) ---
        mid_r = (r_out + r_in) / 2.0
        rect_mid = QRectF(arc_cx - mid_r, arc_cy - mid_r, mid_r * 2, mid_r * 2)
        painter.setPen(QPen(QColor(0, 0, 0, 190), band,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.BevelJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(rect_mid, int(start_qt * 16), int(span_qt * 16))

        # --- Bordi banda ---
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for rr in (r_out, r_in):
            rect = QRectF(arc_cx - rr, arc_cy - rr, rr * 2, rr * 2)
            painter.drawArc(rect, int(start_qt * 16), int(span_qt * 16))

        # --- Tacche e numeri ---
        font = painter.font()
        font.setFamily("Consolas")
        font.setBold(True)
        font.setPixelSize(14)
        painter.setFont(font)

        hdg = self._heading % 360.0
        # ciclo su multipli di 5 attorno a hdg (deg può uscire da 0..360: il %360 normalizza la label)
        first = int(math.floor((hdg - span) / 5.0)) * 5
        last  = int(math.ceil((hdg + span) / 5.0)) * 5

        for deg in range(first, last + 1, 5):
            rel = deg - hdg
            if abs(rel) > span:
                continue
            rad = math.radians(90.0 - rel)
            ux = math.cos(rad)
            uy = -math.sin(rad)             # y schermo: 90° -> -1 (alto)

            ox = arc_cx + r_out * ux
            oy = arc_cy + r_out * uy
            ix, iy = -ux, -uy               # verso il centro dell'arco

            is_major = (deg % 10 == 0)
            tick = 16.0 if is_major else 9.0
            pen_w = 2.0 if is_major else 1.2

            painter.setPen(QPen(QColor(255, 255, 255), pen_w))
            painter.drawLine(
                QPointF(round(ox), round(oy)),
                QPointF(round(ox + ix * tick), round(oy + iy * tick)),
            )

            if is_major:
                d3 = deg % 360
                if d3 == 0:
                    label, col = "N", QColor(255, 70, 70)
                elif d3 == 90:
                    label, col = "E", QColor(255, 255, 255)
                elif d3 == 180:
                    label, col = "S", QColor(255, 255, 255)
                elif d3 == 270:
                    label, col = "W", QColor(255, 255, 255)
                else:
                    label, col = str(d3), QColor(255, 255, 255)

                tx = round(arc_cx + (r_out - 40.0) * ux)
                ty = round(arc_cy + (r_out - 40.0) * uy)
                painter.setPen(col)
                painter.drawText(QRectF(tx - 18, ty - 9, 36, 18),
                                 Qt.AlignmentFlag.AlignCenter, label)

        # --- Lubber pointer (ambra) ---
        tip_y = round(arc_cy - r_out)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 180, 0))
        tri = QPainterPath()
        tri.moveTo(arc_cx, tip_y + 2)
        tri.lineTo(arc_cx - 8, tip_y - 12)
        tri.lineTo(arc_cx + 8, tip_y - 12)
        tri.closeSubpath()
        painter.drawPath(tri)

        # --- Readout digitale ---
        box_w, box_h = 56, 26
        box_x = round(arc_cx - box_w / 2)
        box_y = tip_y - 12 - box_h - 2
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.setBrush(QColor(0, 0, 0, 230))
        painter.drawRoundedRect(QRectF(box_x, box_y, box_w, box_h), 3, 3)
        font.setPixelSize(16)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(box_x, box_y, box_w, box_h),
                         Qt.AlignmentFlag.AlignCenter, f"{int(hdg):03d}")

        painter.restore()


class PFDTestWindow(PrimaryFlightDisplay):
    """
    PFD di test: replica PrimaryFlightDisplay aggiungendo un toggle che
    scambia l'orizzonte artificiale con la mappa 2D nella zona centrale.
    Tape, heading arc, roll indicator, boresight e aircraft symbol restano.
    Il genitore PrimaryFlightDisplay NON viene modificato.
    """

    # Colori pulsante toggle
    _MAP_TOGGLE_ON = QColor(0, 220, 120)    # verde = mappa attiva
    _MAP_TOGGLE_OFF = QColor(255, 126, 0)   # ambra = attitude attivo

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._show_map = False
        self._map_renderer = MapRenderer(pixels_per_meter=0.4, grid_spacing=100.0)
        self._last_data = None
        self._map_toggle_btn_rect = QRectF()

    # ------------------------------------------------------------------
    # Dati: salva anche l'intero oggetto per il MapRenderer
    # ------------------------------------------------------------------
    def update_data(self, data: TelemetryData):
        super().update_data(data)
        self._last_data = data

    # ------------------------------------------------------------------
    # PRIMO PIANO: attitude oppure mappa + tutto il resto del PFD
    # ------------------------------------------------------------------
    def paint_foreground(self, painter: QPainter):
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.TextAntialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        w, h = self._prototype.width, self._prototype.height
        cx = w / 2
        cy = h / 2

        # --- 1. ATTITUDE INDICATOR oppure MAPPA 2D ---
        if self._show_map and self._last_data is not None:
            self._draw_map(painter, w, h)
        else:
            self._draw_attitude(painter, cx, cy, w, h)

        # --- 2. AIRSPEED TAPE ---
        self._draw_airspeed_tape(painter, cx, cy, h)
        # --- 3. ALTITUDE TAPE ---
        self._draw_altitude_tape(painter, cx, cy, h)
        # --- HEADING ARC ---
        self._draw_heading_arc(painter, cx, cy, h)

        # --- 4. AIRCRAFT SYMBOL ---
        painter.save()
        painter.translate(cx, cy)
        painter.setPen(QPen(self._AIRCRAFT_SYMBOL_COLOR, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(-60, 0), QPointF(-20, 0))
        painter.drawLine(QPointF(20, 0), QPointF(60, 0))
        painter.setBrush(self._AIRCRAFT_SYMBOL_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 4, 4)
        painter.restore()

        # --- 5. BORESIGHT ---
        painter.save()
        painter.translate(cx, cy)
        boresight_y = -h / 2 + 40
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._BORESIGHT_COLOR)
        triangle = QPainterPath()
        triangle.moveTo(0, boresight_y)
        triangle.lineTo(-8, boresight_y - 12)
        triangle.lineTo(8, boresight_y - 12)
        triangle.closeSubpath()
        painter.drawPath(triangle)
        painter.restore()

        # --- 6. ROLL INDICATOR ---
        painter.save()
        painter.translate(cx, cy)
        arc_radius = h / 2 - 30
        painter.setPen(QPen(self._HORIZON_COLOR, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc_rect = QRectF(-arc_radius, -arc_radius, arc_radius * 2, arc_radius * 2)
        painter.drawArc(arc_rect, 30 * 16, 120 * 16)
        roll_marks = [0, 10, 20, 30, 45, 60]
        for angle in roll_marks:
            signs = [1] if angle == 0 else [1, -1]
            for sign in signs:
                deg = angle * sign
                painter.save()
                painter.rotate(deg)
                if angle == 0:
                    tick_len = 12
                    tick_w = 2
                elif angle in (10, 20, 30):
                    tick_len = 8
                    tick_w = 1.5
                else:
                    tick_len = 10
                    tick_w = 1.5
                painter.setPen(QPen(self._HORIZON_COLOR, tick_w))
                painter.drawLine(QPointF(0, -arc_radius),
                                 QPointF(0, -arc_radius + tick_len))
                painter.restore()
        painter.restore()

        # --- 7. PULSANTE TOGGLE MAPPA/ATTITUDE ---
        self._draw_map_toggle_button(painter)

    # ------------------------------------------------------------------
    # ATTITUDE INDICATOR (codice originale del PFD, isolato in un metodo)
    # ------------------------------------------------------------------
    def _draw_attitude(self, painter: QPainter, cx: float, cy: float,
                       w: float, h: float):
        painter.save()
        clip_path = QPainterPath()
        clip_path.addRect(0, 0, w, h)
        painter.setClipPath(clip_path)

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._roll)
        pitch_offset = self._pitch * self._px_per_deg

        large = max(w, h) * 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._SKY_COLOR)
        painter.drawRect(QRectF(-large, -large + pitch_offset, large * 2, large))
        painter.setBrush(self._GROUND_COLOR)
        painter.drawRect(QRectF(-large, pitch_offset, large * 2, large))

        painter.setPen(QPen(self._HORIZON_COLOR, 2))
        painter.drawLine(QPointF(-large, pitch_offset), QPointF(large, pitch_offset))

        painter.setPen(QPen(self._PITCH_LADDER_COLOR, 1))
        font = painter.font()
        font.setPixelSize(14)
        font.setBold(True)
        font.setFamily("Consolas")
        painter.setFont(font)
        for deg in range(-90, 95, 5):
            if deg == 0:
                continue
            y_pos = pitch_offset - deg * self._px_per_deg
            if y_pos < -large or y_pos > large:
                continue
            if deg % 10 == 0:
                half_w = 50
                draw_number = True
            else:
                half_w = 25
                draw_number = False
            painter.drawLine(QPointF(-half_w, y_pos), QPointF(half_w, y_pos))
            if draw_number:
                label = str(abs(deg))
                painter.setPen(self._PITCH_LADDER_COLOR)
                painter.drawText(QRectF(-half_w - 30, y_pos - 8, 28, 16),
                                 Qt.AlignmentFlag.AlignRight |
                                 Qt.AlignmentFlag.AlignVCenter, label)
                painter.drawText(QRectF(half_w + 2, y_pos - 8, 28, 16),
                                 Qt.AlignmentFlag.AlignLeft |
                                 Qt.AlignmentFlag.AlignVCenter, label)
                painter.setPen(QPen(self._PITCH_LADDER_COLOR, 1))
        painter.restore()  # Fine rotazione

        # Zero pitch reference line
        painter.setPen(QPen(self._HORIZON_COLOR, 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(cx - 80, cy), QPointF(cx + 80, cy))
        painter.restore()  # Fine clipping

    # ------------------------------------------------------------------
    # MAPPA 2D (al posto dell'attitude)
    # ------------------------------------------------------------------
    def _draw_map(self, painter: QPainter, w: float, h: float):
        painter.save()
        clip = QPainterPath()
        clip.addRect(0, 0, w, h)
        painter.setClipPath(clip)
        # Margine per non coprire le tape laterali
        margin_x = self._tape_width + 12
        rect = QRectF(margin_x, 10, w - 2 * margin_x, h - 20)
        self._map_renderer.render(painter, rect, self._last_data)
        painter.restore()

    def get_map_scale_menu(self):
        """Sottomenu Scala Mappa: disponibile solo quando la mappa è attiva."""
        if not self._show_map:
            return None
        from PySide6.QtWidgets import QMenu
        menu = QMenu("Scala Mappa")
        for label, distance in MapRenderer.SCALE_PRESETS:
            action = menu.addAction(label)
            action.triggered.connect(
                lambda checked, d=distance: self._apply_map_scale_preset(d))
        return menu

    def _apply_map_scale_preset(self, distance: float):
        """Applica un preset di scala alla mappa e ridisegna."""
        self._map_renderer.set_scale_preset(distance)
        self.update()

    # ------------------------------------------------------------------
    # PULSANTE TOGGLE
    # ------------------------------------------------------------------
    def _draw_map_toggle_button(self, painter: QPainter):
        w = self._prototype.width
        btn_w, btn_h = 60, 18
        btn_x = w - btn_w - 8
        btn_y = 8
        self._map_toggle_btn_rect = QRectF(btn_x, btn_y, btn_w, btn_h)

        color = self._MAP_TOGGLE_ON if self._show_map else self._MAP_TOGGLE_OFF
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(QColor(10, 10, 14, 220))
        painter.drawRoundedRect(self._map_toggle_btn_rect, 3, 3)

        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(color)
        label = "MAP" if self._show_map else "ATT"
        painter.drawText(self._map_toggle_btn_rect,
                         Qt.AlignmentFlag.AlignCenter, label)

    # ------------------------------------------------------------------
    # MOUSE: toggle + pulsanti unità ereditati
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        """Gestisce toggle mappa/attitude + pulsanti zoom del bilanciere."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Toggle mappa/attitude
            if self._map_toggle_btn_rect.contains(event.pos()):
                self._show_map = not self._show_map
                self.update()
                event.accept()
                return
            # Pulsanti zoom (solo quando la mappa è attiva)
            if self._show_map:
                w, h = self._prototype.width, self._prototype.height
                margin_x = self._tape_width + 12
                rect = QRectF(margin_x, 10, w - 2 * margin_x, h - 20)
                zoom_out_rect, zoom_in_rect = self._map_renderer.zoom_button_rects(rect)
                if zoom_in_rect.contains(event.pos()):
                    self._map_renderer.zoom_in()
                    self.update()
                    event.accept()
                    return
                if zoom_out_rect.contains(event.pos()):
                    self._map_renderer.zoom_out()
                    self.update()
                    event.accept()
                    return
        super().mousePressEvent(event)



















