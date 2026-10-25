"""
gcs_ui/sim_ui/core/map_renderer.py

Renderer di mappa 2D stile navigatore (north-up, aircraft-centered).

NON è un QGraphicsItem né un QWidget: è pura logica di disegno che sa
renderizzare la mappa dentro un QRectF arbitrario usando un QPainter
fornito dal chiamante. Questo lo rende integrabile in qualsiasi
strumento (PFD, viewport, strumento dedicato) e riusabile nel simulatore.

Coordinate: NED in metri (pos_north, pos_east), prua in gradi (0=Nord).

M4: trail (scia del percorso con fade) e readout di posizione.
M5: ottimizzazione trail a blocchi, barra di scala distanza,
    indicatori direzionali E/S/W.
"""

from __future__ import annotations

import math
from collections import deque

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen


class MapRenderer:
    """
    Disegna una mappa 2D aircraft-centered con orientamento north-up.

    Il velivolo è sempre al centro del rettangolo; la griglia scorre
    sotto di lui in base alla posizione, dando percezione del movimento.
    """

    # --- Colori stile navigatore notturno ---
    _BG_COLOR = QColor(12, 18, 28)          # sfondo blu molto scuro
    _GRID_MINOR = QColor(35, 45, 60)        # griglia secondaria
    _GRID_MAJOR = QColor(60, 75, 95)        # griglia principale
    _AIRCRAFT_COLOR = QColor(255, 180, 0)   # ambra (coerente col progetto)
    _NORTH_COLOR = QColor(0, 220, 120)      # verde
    _BORDER_COLOR = QColor(70, 80, 95)      # bordo
    _TRAIL_COLOR = QColor(0, 220, 120)      # verde per il trail
    _READOUT_BG = QColor(10, 14, 20, 200)   # sfondo readout
    _READOUT_TEXT = QColor(0, 220, 120)     # testo readout
    _COMPASS_DIM = QColor(160, 170, 185, 120)  # E/S/W attenuati

    # --- Parametri trail ---
    _TRAIL_MAX_POINTS = 240        # numero massimo di punti nel buffer
    _TRAIL_JUMP_THRESHOLD = 50.0   # metri: soglia per rilevare un salto
    _TRAIL_CHUNKS = 4              # blocchi per il fade (M5)

    # --- Parametri scala distanza (M5) ---
    _SCALE_BAR_TARGET_PX = 100     # lunghezza obiettivo della barra in pixel
    _SCALE_NICE_STEPS = (10, 25, 50, 100, 250, 500,
                         1000, 2500, 5000, 10000, 25000, 50000)
    # --- Preset di scala ---
    SCALE_PRESETS = (
        ("100 m", 100.0),
        ("250 m", 250.0),
        ("1 km", 1000.0),
    )
    # --- Parametri zoom (bilanciere) ---
    _ZOOM_FACTOR = 1.25          # fattore moltiplicativo per step
    _ZOOM_MIN_PPM = 0.05         # pixels_per_meter minimo
    _ZOOM_MAX_PPM = 10.0         # pixels_per_meter massimo
    _ZOOM_BTN_BG = QColor(40, 50, 65, 220)
    _ZOOM_BTN_BORDER = QColor(0, 220, 120)
    _ZOOM_BTN_TEXT = QColor(0, 220, 120)


    def __init__(self, pixels_per_meter: float = 0.4, grid_spacing: float = 100.0):
        """
        Args:
            pixels_per_meter: scala di rendering (pixel per metro).
            grid_spacing: spaziatura della griglia in metri.
        """
        self._pixels_per_meter = max(0.01, pixels_per_meter)
        self._grid_spacing = max(1.0, grid_spacing)
        # Stato trail
        self._trail: deque = deque(maxlen=self._TRAIL_MAX_POINTS)
        self._last_pos = None
        # Flag per abilitare/disabilitare trail e readout
        self._show_trail = True
        self._show_readout = True
        # Flag M5
        self._show_scale_bar = True
        self._show_compass = True

    # ------------------------------------------------------------------
    # Configurazione
    # ------------------------------------------------------------------
    def set_scale(self, pixels_per_meter: float) -> None:
        """Imposta la scala (pixel per metro)."""
        self._pixels_per_meter = max(0.01, pixels_per_meter)

    def set_grid_spacing(self, spacing_meters: float) -> None:
        """Imposta la spaziatura della griglia in metri."""
        self._grid_spacing = max(1.0, spacing_meters)

    def set_show_trail(self, enabled: bool) -> None:
        """Abilita/disabilita il disegno del trail."""
        self._show_trail = enabled

    def set_show_readout(self, enabled: bool) -> None:
        """Abilita/disabilita il readout di posizione."""
        self._show_readout = enabled

    def set_show_scale_bar(self, enabled: bool) -> None:
        """Abilita/disabilita la barra di scala distanza (M5)."""
        self._show_scale_bar = enabled

    def set_show_compass(self, enabled: bool) -> None:
        """Abilita/disabilita gli indicatori E/S/W (M5)."""
        self._show_compass = enabled

    def reset_trail(self) -> None:
        """Svuota manualmente il buffer del trail."""
        self._trail.clear()
        self._last_pos = None

    # ------------------------------------------------------------------
    # Gestione trail
    # ------------------------------------------------------------------
    def _update_trail(self, pos_n: float, pos_e: float) -> None:
        """
        Aggiunge la posizione al trail. Se la distanza dall'ultimo punto
        supera la soglia di salto, il buffer viene svuotato (gestisce il
        cambio di traiettoria senza linee di collegamento errate).
        """
        if self._last_pos is not None:
            last_n, last_e = self._last_pos
            dist = math.hypot(pos_n - last_n, pos_e - last_e)
            if dist > self._TRAIL_JUMP_THRESHOLD:
                self._trail.clear()
        self._trail.append((pos_n, pos_e))
        self._last_pos = (pos_n, pos_e)

    # ------------------------------------------------------------------
    # Trasformazione mondo -> schermo
    # ------------------------------------------------------------------
    def _world_to_screen(self, rect: QRectF, pos_n: float, pos_e: float,
                         n: float, e: float):
        """Converte coordinate mondo (n, e) in coordinate schermo."""
        cx = rect.center().x()
        cy = rect.center().y()
        ppm = self._pixels_per_meter
        sx = cx + (e - pos_e) * ppm
        sy = cy - (n - pos_n) * ppm
        return sx, sy

    # ------------------------------------------------------------------
    # Rendering principale
    # ------------------------------------------------------------------
    def render(self, painter: QPainter, rect: QRectF, data) -> None:
        """
        Disegna la mappa dentro `rect` usando i dati di telemetria.

        `data` deve esporre: pos_north (m), pos_east (m), heading (gradi).
        Usa getattr con default così funziona anche con dati privi di
        posizione (es. mock sinusoidale): il velivolo resta fermo al centro.
        """
        if rect.width() <= 0 or rect.height() <= 0:
            return

        pos_n = getattr(data, "pos_north", 0.0)
        pos_e = getattr(data, "pos_east", 0.0)
        heading = getattr(data, "heading", 0.0)

        # Aggiorna il trail con la posizione corrente
        if self._show_trail:
            self._update_trail(pos_n, pos_e)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(rect)

        self._draw_background(painter, rect)
        self._draw_grid(painter, rect, pos_n, pos_e)
        if self._show_trail:
            self._draw_trail(painter, rect, pos_n, pos_e)
        self._draw_aircraft(painter, rect, heading)
        self._draw_north_indicator(painter, rect)
        if self._show_compass:
            self._draw_compass_indicators(painter, rect)
        if self._show_readout:
            self._draw_readout(painter, rect, pos_n, pos_e, heading)
        if self._show_scale_bar:
            self._draw_scale_bar(painter, rect)
        if self._show_scale_bar:
            self._draw_scale_bar(painter, rect)

        #bilanciere zoom
        self._draw_zoom_buttons(painter, rect)
        self._draw_border(painter, rect)

        self._draw_border(painter, rect)

        painter.restore()

    # ------------------------------------------------------------------
    # Sfondo
    # ------------------------------------------------------------------
    def _draw_background(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._BG_COLOR)
        painter.drawRect(rect)

    # ------------------------------------------------------------------
    # Griglia scorrevole
    # ------------------------------------------------------------------
    def _draw_grid(self, painter: QPainter, rect: QRectF,
                   pos_n: float, pos_e: float) -> None:
        """
        Disegna la griglia ancorata al mondo: il centro dello schermo
        corrisponde alla posizione attuale, quindi la griglia scorre
        quando la posizione cambia.
        """
        cx = rect.center().x()
        cy = rect.center().y()
        ppm = self._pixels_per_meter
        spacing = self._grid_spacing

        half_w_m = (rect.width() / 2.0) / ppm
        half_h_m = (rect.height() / 2.0) / ppm

        n_min, n_max = pos_n - half_h_m, pos_n + half_h_m
        e_min, e_max = pos_e - half_w_m, pos_e + half_w_m

        # Linee orizzontali (nord costante)
        k_start = math.ceil(n_min / spacing)
        k_end = math.floor(n_max / spacing)
        for k in range(k_start, k_end + 1):
            n = k * spacing
            y = cy - (n - pos_n) * ppm
            major = (k % 5 == 0)
            pen = QPen(self._GRID_MAJOR if major else self._GRID_MINOR,
                       1.5 if major else 1.0)
            painter.setPen(pen)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        # Linee verticali (est costante)
        k_start = math.ceil(e_min / spacing)
        k_end = math.floor(e_max / spacing)
        for k in range(k_start, k_end + 1):
            e = k * spacing
            x = cx + (e - pos_e) * ppm
            major = (k % 5 == 0)
            pen = QPen(self._GRID_MAJOR if major else self._GRID_MINOR,
                       1.5 if major else 1.0)
            painter.setPen(pen)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

    # ------------------------------------------------------------------
    # Zoom (bilanciere [-] [+])
    # ------------------------------------------------------------------
    def zoom_in(self) -> None:
        """Aumenta lo zoom (più pixel per metro)."""
        self._pixels_per_meter = min(
            self._ZOOM_MAX_PPM,
            self._pixels_per_meter * self._ZOOM_FACTOR)

    def zoom_out(self) -> None:
        """Diminuisce lo zoom (meno pixel per metro)."""
        self._pixels_per_meter = max(
            self._ZOOM_MIN_PPM,
            self._pixels_per_meter / self._ZOOM_FACTOR)
        
    def set_scale_preset(self, distance_meters: float) -> None:
        """
        Imposta la scala in base a un preset di distanza.
        La distanza indica quanti metri corrispondono alla lunghezza
        obiettivo della barra di scala (_SCALE_BAR_TARGET_PX).
        """
        if distance_meters <= 0:
            return
        ppm = self._SCALE_BAR_TARGET_PX / distance_meters
        self._pixels_per_meter = max(
            self._ZOOM_MIN_PPM,
            min(self._ZOOM_MAX_PPM, ppm))

    def zoom_button_rects(self, rect: QRectF):
        """
        Restituisce i rettangoli (zoom_out, zoom_in) dei pulsanti del
        bilanciere, posizionati in basso al centro del rettangolo mappa.
        """
        btn_size = 20.0
        gap = 2.0
        pad = 10.0
        total_w = btn_size * 2 + gap
        bx = rect.center().x() - total_w / 2
        by = rect.bottom() - pad - btn_size
        zoom_out_rect = QRectF(bx, by, btn_size, btn_size)
        zoom_in_rect = QRectF(bx + btn_size + gap, by, btn_size, btn_size)
        return zoom_out_rect, zoom_in_rect

    def _draw_zoom_buttons(self, painter: QPainter, rect: QRectF) -> None:
        """Disegna il bilanciere [-] [+] in stile telefono."""
        zoom_out_rect, zoom_in_rect = self.zoom_button_rects(rect)

        # Contenitore arrotondato che avvolge i due pulsanti
        container = zoom_out_rect.united(zoom_in_rect).adjusted(-3, -3, 3, 3)
        painter.setPen(QPen(self._ZOOM_BTN_BORDER, 1.0))
        painter.setBrush(QColor(15, 20, 28, 200))
        painter.drawRoundedRect(container, 5, 5)

        # --- Pulsante zoom-out [-] ---
        painter.setPen(QPen(self._ZOOM_BTN_BORDER, 1.0))
        painter.setBrush(self._ZOOM_BTN_BG)
        painter.drawRoundedRect(zoom_out_rect, 3, 3)
        painter.setPen(QPen(self._ZOOM_BTN_TEXT, 2.0))
        cx = zoom_out_rect.center().x()
        cy = zoom_out_rect.center().y()
        painter.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))

        # --- Pulsante zoom-in [+] ---
        painter.setPen(QPen(self._ZOOM_BTN_BORDER, 1.0))
        painter.setBrush(self._ZOOM_BTN_BG)
        painter.drawRoundedRect(zoom_in_rect, 3, 3)
        painter.setPen(QPen(self._ZOOM_BTN_TEXT, 2.0))
        cx = zoom_in_rect.center().x()
        cy = zoom_in_rect.center().y()
        painter.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
        painter.drawLine(QPointF(cx, cy - 5), QPointF(cx, cy + 5))

    # ------------------------------------------------------------------
    # Trail (scia del percorso) — ottimizzato a blocchi (M5)
    # ------------------------------------------------------------------
    def _draw_trail(self, painter: QPainter, rect: QRectF,
                    pos_n: float, pos_e: float) -> None:
        """
        Disegna la scia con opacità decrescente verso i punti più vecchi.
        Ottimizzazione M5: invece di un draw call per segmento, il trail
        viene diviso in pochi blocchi, ciascuno disegnato con un QPainterPath.
        """
        n = len(self._trail)
        if n < 2:
            return

        num_chunks = min(self._TRAIL_CHUNKS, n - 1)
        chunk_size = max(1, (n - 1) // num_chunks)

        for chunk_idx in range(num_chunks):
            start_i = chunk_idx * chunk_size
            end_i = min(start_i + chunk_size + 1, n)  # +1 per continuità
            if start_i >= n or end_i <= start_i + 1:
                continue

            # Opacità proporzionale: blocchi più recenti più visibili
            alpha = int(255 * ((chunk_idx + 1) / num_chunks))
            alpha = max(20, alpha)

            color = QColor(self._TRAIL_COLOR)
            color.setAlpha(alpha)
            painter.setPen(QPen(color, 2.0))

            # Costruisci il path per questo blocco
            path = QPainterPath()
            n0, e0 = self._trail[start_i]
            x0, y0 = self._world_to_screen(rect, pos_n, pos_e, n0, e0)
            path.moveTo(x0, y0)

            for i in range(start_i + 1, end_i):
                ni, ei = self._trail[i]
                xi, yi = self._world_to_screen(rect, pos_n, pos_e, ni, ei)
                path.lineTo(xi, yi)

            painter.drawPath(path)

    # ------------------------------------------------------------------
    # Simbolo velivolo
    # ------------------------------------------------------------------
    def _draw_aircraft(self, painter: QPainter, rect: QRectF,
                       heading: float) -> None:
        """Simbolo velivolo al centro, ruotato secondo la prua (0=Nord=alto)."""
        cx = rect.center().x()
        cy = rect.center().y()

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(heading)

        size = 16.0
        path = QPainterPath()
        path.moveTo(0.0, -size)                 # prua (punta in alto a hdg=0)
        path.lineTo(-size * 0.6, size * 0.6)
        path.lineTo(0.0, size * 0.35)           # rientro per forma a freccia
        path.lineTo(size * 0.6, size * 0.6)
        path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._AIRCRAFT_COLOR)
        painter.drawPath(path)
        painter.restore()

    # ------------------------------------------------------------------
    # Riferimento Nord
    # ------------------------------------------------------------------
    def _draw_north_indicator(self, painter: QPainter, rect: QRectF) -> None:
        """Indicatore 'N' in alto (mappa north-up)."""
        painter.setPen(self._NORTH_COLOR)
        font = painter.font()
        font.setPixelSize(14)
        font.setBold(True)
        painter.setFont(font)

        x = rect.center().x()
        y = rect.top() + 6.0
        painter.drawText(QRectF(x - 20.0, y, 40.0, 18.0),
                         Qt.AlignmentFlag.AlignCenter, "N")

    # ------------------------------------------------------------------
    # Indicatori direzionali E/S/W (M5)
    # ------------------------------------------------------------------
    def _draw_compass_indicators(self, painter: QPainter, rect: QRectF) -> None:
        """
        Aggiunge le lettere E, S, W ai bordi della mappa.
        La N è già gestita da _draw_north_indicator.
        """
        cx = rect.center().x()
        cy = rect.center().y()

        painter.setPen(self._COMPASS_DIM)
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)

        # E (destra)
        painter.drawText(QRectF(rect.right() - 22, cy - 8, 18, 16),
                         Qt.AlignmentFlag.AlignCenter, "E")
        # S (basso)
        painter.drawText(QRectF(cx - 9, rect.bottom() - 22, 18, 16),
                         Qt.AlignmentFlag.AlignCenter, "S")
        # W (sinistra)
        painter.drawText(QRectF(rect.left() + 4, cy - 8, 18, 16),
                         Qt.AlignmentFlag.AlignCenter, "W")

    # ------------------------------------------------------------------
    # Readout posizione
    # ------------------------------------------------------------------
    def _draw_readout(self, painter: QPainter, rect: QRectF,
                      pos_n: float, pos_e: float, heading: float) -> None:
        """Pannello in basso a sinistra con posizione N/E e prua."""
        pad = 8.0
        box_w = 130.0
        box_h = 46.0
        box_x = rect.left() + pad
        box_y = rect.bottom() - box_h - pad
        box = QRectF(box_x, box_y, box_w, box_h)

        painter.setPen(QPen(self._BORDER_COLOR, 1.0))
        painter.setBrush(self._READOUT_BG)
        painter.drawRoundedRect(box, 4, 4)

        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        font.setFamily("Consolas")
        painter.setFont(font)
        painter.setPen(self._READOUT_TEXT)

        line_h = 13.0
        ty = box_y + 6.0
        painter.drawText(QRectF(box_x + 6, ty, box_w - 12, line_h),
                         Qt.AlignmentFlag.AlignLeft,
                         f"N: {pos_n:+8.0f} m")
        painter.drawText(QRectF(box_x + 6, ty + line_h, box_w - 12, line_h),
                         Qt.AlignmentFlag.AlignLeft,
                         f"E: {pos_e:+8.0f} m")
        painter.drawText(QRectF(box_x + 6, ty + 2 * line_h, box_w - 12, line_h),
                         Qt.AlignmentFlag.AlignLeft,
                         f"HDG: {int(heading % 360):03d}\u00b0")

    # ------------------------------------------------------------------
    # Barra di scala distanza (M5)
    # ------------------------------------------------------------------
    def _draw_scale_bar(self, painter: QPainter, rect: QRectF) -> None:
        """
        Disegna una barra di scala in basso a destra che indica la
        distanza corrispondente a una lunghezza fissa in pixel.
        Si adatta automaticamente al livello di zoom corrente.
        """
        ppm = self._pixels_per_meter

        # Scegli una distanza "bella" vicina all'obiettivo in pixel
        raw_distance = self._SCALE_BAR_TARGET_PX / ppm
        distance = min(self._SCALE_NICE_STEPS,
                       key=lambda d: abs(d - raw_distance))

        # Lunghezza effettiva in pixel della barra
        bar_px = distance * ppm
        if bar_px < 20 or bar_px > rect.width() * 0.6:
            return  # Non disegnare se troppo piccola o troppo grande

        # Posizione: in basso a destra, sopra il bordo
        pad = 10.0
        bar_y = rect.bottom() - pad - 14
        bar_x = rect.right() - pad - bar_px

        # Linea della barra
        painter.setPen(QPen(self._NORTH_COLOR, 2))
        painter.drawLine(QPointF(bar_x, bar_y), QPointF(bar_x + bar_px, bar_y))
        # Tacche terminali
        tick_h = 4.0
        painter.drawLine(QPointF(bar_x, bar_y - tick_h),
                         QPointF(bar_x, bar_y + tick_h))
        painter.drawLine(QPointF(bar_x + bar_px, bar_y - tick_h),
                         QPointF(bar_x + bar_px, bar_y + tick_h))

        # Etichetta
        if distance >= 1000:
            label = f"{distance / 1000:.0f} km"
        else:
            label = f"{distance:.0f} m"

        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self._NORTH_COLOR)
        painter.drawText(QRectF(bar_x, bar_y - 18, bar_px, 14),
                         Qt.AlignmentFlag.AlignCenter, label)

    # ------------------------------------------------------------------
    # Bordo
    # ------------------------------------------------------------------
    def _draw_border(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(self._BORDER_COLOR, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))