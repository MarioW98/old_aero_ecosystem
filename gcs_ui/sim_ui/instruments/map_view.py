"""
gcs_ui/sim_ui/instruments/map_view.py

Strumento di visualizzazione mappa 2D (navigazione).

È un BaseInstrument standalone posizionabile nell'hangar come gli altri
strumenti. Delega il disegno al MapRenderer (logica pura riusabile),
così la stessa logica potrà in futuro essere montata anche nel PFD_test,
nel viewport o in un renderer 3D intercambiabile.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QMenu

from .base import BaseInstrument
from ..core.telemetry import TelemetryData
from ..core.map_renderer import MapRenderer


class MapViewInstrument(BaseInstrument):
    """
    Strumento mappa 2D di navigazione.

    Mostra la mappa aircraft-centered con orientamento north-up:
    il velivolo resta al centro, la griglia scorre in base alla
    posizione (pos_north / pos_east), dando percezione del movimento.
    """

    # Colori cornice (stile coerente con gli altri display scuri)
    _BEZEL_COLOR = QColor(15, 18, 25)
    _BEZEL_BORDER = QColor(60, 70, 85)

    def __init__(self, prototype, parent=None):
        super().__init__(prototype, parent)
        # Renderer della mappa: logica pura di disegno, riusabile.
        # In futuro potrà essere sostituito con un renderer 3D.
        self._renderer = MapRenderer(pixels_per_meter=0.4, grid_spacing=100.0)
        # Dato di default: velivolo fermo all'origine (griglia statica)
        self._data = TelemetryData()

    def update_data(self, data: TelemetryData):
        """Riceve la telemetria e richiede il ridisegno."""
        self._data = data
        self.update()

    # ==================================================================
    # RENDERING
    # ==================================================================
    def paint_background(self, painter: QPainter):
        """Cornice/bezel dello strumento (statico, viene cachato)."""
        w, h = self._prototype.width, self._prototype.height
        painter.setPen(QPen(self._BEZEL_BORDER, 1.5))
        painter.setBrush(self._BEZEL_COLOR)
        painter.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)

    def paint_foreground(self, painter: QPainter):
        """Disegna la mappa delegando al MapRenderer."""
        w, h = self._prototype.width, self._prototype.height
        margin = 6.0
        rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)
        # Il renderer disegna sfondo, griglia, velivolo, nord e bordo
        self._renderer.render(painter, rect, self._data)

    def get_map_scale_menu(self):
        """Restituisce il sottomenu Scala Mappa (sempre disponibile)."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu("Scala Mappa")
        for label, distance in MapRenderer.SCALE_PRESETS:
            action = menu.addAction(label)
            action.triggered.connect(
                lambda checked, d=distance: self._apply_scale_preset(d))
        return menu

    def _apply_scale_preset(self, distance: float):
        """Applica un preset di scala e ridisegna."""
        self._renderer.set_scale_preset(distance)
        self.update()

    def mousePressEvent(self, event):
        """Gestisce il click sui pulsanti zoom del bilanciere."""
        if event.button() == Qt.MouseButton.LeftButton:
            w, h = self._prototype.width, self._prototype.height
            margin = 6.0
            rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)
            zoom_out_rect, zoom_in_rect = self._renderer.zoom_button_rects(rect)
            if zoom_in_rect.contains(event.pos()):
                self._renderer.zoom_in()
                self.update()
                event.accept()
                return
            if zoom_out_rect.contains(event.pos()):
                self._renderer.zoom_out()
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)