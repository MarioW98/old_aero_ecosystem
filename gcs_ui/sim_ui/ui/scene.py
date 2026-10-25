from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene

from ..core.constants import DEFAULT_GRID_SIZE


class InstrumentScene(QGraphicsScene):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snap_enabled = False
        self._grid_size = DEFAULT_GRID_SIZE
        self._grid_color = QColor(100, 100, 100, 60)
        self._center_color = QColor(200, 80, 80, 120)

    # =========================================================================
    # SETTER
    # =========================================================================

    def set_snap_enabled(self, enabled: bool):
        self._snap_enabled = enabled
        self.invalidate()

    def set_grid_size(self, size: float):
        self._grid_size = size
        self.invalidate()

    def set_grid_color(self, color):
        self._grid_color = QColor(color)
        self.invalidate()

    # =========================================================================
    # DISEGNO SFONDO
    # =========================================================================

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)

        # Griglia e linee centrali solo con snap attivo
        if self._snap_enabled and self._grid_size > 0:
            self._draw_grid(painter, rect)
            self._draw_center_lines(painter, self.sceneRect())

    # =========================================================================
    # GRIGLIA
    # =========================================================================

    def _draw_grid(self, painter: QPainter, rect: QRectF):
        grid = self._grid_size
        painter.setPen(QPen(self._grid_color, 1))

        x = (rect.left() // grid) * grid
        while x <= rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += grid

        y = (rect.top() // grid) * grid
        while y <= rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += grid

    # =========================================================================
    # LINEE CENTRALI (solo con snap)
    # =========================================================================

    def _draw_center_lines(self, painter: QPainter, scene_rect: QRectF):
        cx = scene_rect.center().x()
        cy = scene_rect.center().y()

        painter.setPen(QPen(self._center_color, 1.5, Qt.PenStyle.DashDotLine))
        painter.drawLine(QPointF(scene_rect.left(), cy),
                         QPointF(scene_rect.right(), cy))
        painter.drawLine(QPointF(cx, scene_rect.top()),
                         QPointF(cx, scene_rect.bottom()))