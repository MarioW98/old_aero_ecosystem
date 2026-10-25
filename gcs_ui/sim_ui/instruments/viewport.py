from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QLinearGradient, QFont

from .base import BaseInstrument
from ..core.telemetry import TelemetryData


class SimulatorViewport(BaseInstrument):
    """
    Finestra di visualizzazione del simulatore.
    Mostra cielo e terra con pitch e roll.
    Opzionalmente mostra la scala di beccheggio (pitch ladder).
    """

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        self._pitch = 0.0      # gradi (positivo = naso su)
        self._roll = 0.0       # gradi (positivo = ala destra giù)
        self._px_per_deg = 3.0  # pixel per grado di pitch
        self._show_pitch_ladder = False  # Toggle scala beccheggio

    def update_data(self, data: TelemetryData):
        self._pitch = data.pitch
        self._roll = data.roll
        self.update()

    # =========================================================================
    # PULSANTE TOGGLE SCALA BECCHEGGIO
    # =========================================================================

    def _toggle_button_rect(self) -> QRectF:
        """Rettangolo del pulsante toggle in basso a sinistra."""
        w, h = self._prototype.width, self._prototype.height
        size = 24.0
        return QRectF(8, h - size - 8, size, size)

    def _draw_toggle_button(self, p: QPainter):
        """Disegna il pulsante toggle per la scala di beccheggio."""
        rect = self._toggle_button_rect()
        
        # Sfondo pulsante
        if self._show_pitch_ladder:
            p.setBrush(QColor(0, 220, 120, 180))  # Verde quando attivo
        else:
            p.setBrush(QColor(80, 80, 85, 180))   # Grigio quando disattivo
        
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        p.drawRoundedRect(rect, 4, 4)
        
        # Icona: linee orizzontali (simbolo scala)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        cx, cy = rect.center().x(), rect.center().y()
        for i in range(-1, 2):
            y = cy + i * 5
            p.drawLine(QPointF(cx - 6, y), QPointF(cx + 6, y))

    # =========================================================================
    # INTERAZIONE MOUSE
    # =========================================================================

    def mouseReleaseEvent(self, event):
        """Gestisce il click sul pulsante toggle al rilascio del mouse."""
        if event.button() == Qt.MouseButton.LeftButton:
            btn_rect = self._toggle_button_rect()
            # Usa event.pos() invece di event.position() per compatibilità
            local_pos = event.pos()
            if btn_rect.contains(local_pos):
                self._show_pitch_ladder = not self._show_pitch_ladder
                self.update()
                event.accept()
                return
        super().mouseReleaseEvent(event)

    # =========================================================================
    # RENDERING
    # =========================================================================

    def paint_background(self, painter: QPainter):
        # Sfondo nero (bordo)
        w, h = self._prototype.width, self._prototype.height
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 20, 25, 180))  # Trasparenza 180
        painter.drawRect(QRectF(0, 0, w, h))

    def paint_foreground(self, painter: QPainter):
        w, h = self._prototype.width, self._prototype.height
        cx, cy = w / 2, h / 2

        # Margine interno
        margin = 8
        view_w = w - 2 * margin
        view_h = h - 2 * margin

        # Clipping al rettangolo interno
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(margin, margin, view_w, view_h), 12, 12)
        painter.setClipPath(clip)

        # Trasla al centro e ruota per roll
        painter.translate(cx, cy)
        painter.rotate(-self._roll)

        # Offset verticale per pitch
        pitch_offset = self._pitch * self._px_per_deg

        # Dimensioni grandi per coprire tutto durante la rotazione
        large = max(view_w, view_h) * 2

        # Cielo (sopra l'orizzonte)
        sky_gradient = QLinearGradient(0, -large + pitch_offset, 0, pitch_offset)
        sky_gradient.setColorAt(0, QColor(80, 140, 220))   # blu scuro in alto
        sky_gradient.setColorAt(1, QColor(160, 200, 240))  # blu chiaro all'orizzonte
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sky_gradient)
        painter.drawRect(QRectF(-large, -large + pitch_offset, large * 2, large))

        # Terra (sotto l'orizzonte)
        ground_gradient = QLinearGradient(0, pitch_offset, 0, large + pitch_offset)
        ground_gradient.setColorAt(0, QColor(140, 110, 80))   # marrone chiaro all'orizzonte
        ground_gradient.setColorAt(1, QColor(80, 60, 40))     # marrone scuro in basso
        painter.setBrush(ground_gradient)
        painter.drawRect(QRectF(-large, pitch_offset, large * 2, large))

        # Linea dell'orizzonte
        painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
        painter.drawLine(QPointF(-large, pitch_offset), QPointF(large, pitch_offset))

        # =====================================================================
        # SCALA DI BECCHEGGIO (Pitch Ladder) - se abilitata
        # =====================================================================
        if self._show_pitch_ladder:
            self._draw_pitch_ladder(painter, pitch_offset)

        painter.restore()

        # Bordo arrotondato
        painter.setPen(QPen(QColor(60, 60, 65), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(margin, margin, view_w, view_h), 12, 12)

        # Simbolo aereo fisso al centro (chevron stile PFD digitale)
        painter.save()
        painter.translate(cx, cy)
        
        # Colore ambra classico per strumenti digitali
        amber = QColor(255, 180, 0)
        painter.setPen(QPen(amber, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Ali principali (linee orizzontali con piega verso il basso)
        # Ala sinistra
        painter.drawLine(QPointF(-60, 0), QPointF(-20, 0))
        painter.drawLine(QPointF(-20, 0), QPointF(-15, 6))  # piega giù
        
        # Ala destra
        painter.drawLine(QPointF(20, 0), QPointF(60, 0))
        painter.drawLine(QPointF(20, 0), QPointF(15, 6))  # piega giù
        
        # Rombo centrale (tipico dei PFD)
        painter.setPen(QPen(amber, 3))
        painter.setBrush(amber)
        diamond_size = 6
        diamond = QPainterPath()
        diamond.moveTo(0, -diamond_size)
        diamond.lineTo(diamond_size, 0)
        diamond.lineTo(0, diamond_size)
        diamond.lineTo(-diamond_size, 0)
        diamond.closeSubpath()
        painter.drawPath(diamond)
        
        painter.restore()

        # Pulsante toggle scala beccheggio (in basso a sinistra)
        self._draw_toggle_button(painter)

    # =========================================================================
    # SCALA DI BECCHEGGIO
    # =========================================================================

    def _draw_pitch_ladder(self, p: QPainter, pitch_offset: float):
        """Disegna la scala di beccheggio (pitch ladder) stile PFD."""
        # Font per i numeri
        pf = p.font()
        pf.setPixelSize(11)
        pf.setBold(True)
        p.setFont(pf)

        # Disegna da -30° a +30° ogni 5°
        for deg in range(-30, 35, 5):
            if deg == 0:
                continue  # Salta la linea dell'orizzonte (già disegnata)
            
            y = pitch_offset - deg * self._px_per_deg
            
            if deg % 10 == 0:
                # Tacca maggiore: linea continua + numero
                half_w = 40
                p.setPen(QPen(QColor(255, 255, 255), 2.0, Qt.PenStyle.SolidLine))
                p.drawLine(QPointF(-half_w, y), QPointF(half_w, y))
                
                # Numeri ai lati
                label = str(abs(deg))
                p.setPen(QColor(255, 255, 255))
                # Numero sinistro
                p.drawText(QRectF(-half_w - 25, y - 8, 20, 16),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           label)
                # Numero destro
                p.drawText(QRectF(half_w + 5, y - 8, 20, 16),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           label)
            else:
                # Tacca minore: linea tratteggiata
                half_w = 20
                p.setPen(QPen(QColor(255, 255, 255, 180), 1.5, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(-half_w, y), QPointF(half_w, y))