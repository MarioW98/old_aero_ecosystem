from __future__ import annotations
import math
import uuid

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QMenu

from ..core.constants import DEFAULT_GRID_SIZE
from ..core.prototype import InstrumentPrototype
from ..core.telemetry import TelemetryData
from ..core.theme import InstrumentTheme, _theme_base


class BaseInstrument(QGraphicsObject):
    def __init__(self, prototype: InstrumentPrototype, parent=None):
        super().__init__(parent)
        self._prototype = prototype
        self._instance_id = str(uuid.uuid4())
        self._bg_cache: QPixmap | None = None
        

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._snap_enabled = False
        self._grid_size = DEFAULT_GRID_SIZE
        self._theme: InstrumentTheme | None = None

    @property
    def prototype(self): return self._prototype

    @property
    def instance_id(self): return self._instance_id

    def set_instance_id(self, v: str): self._instance_id = v

    def set_snap_enabled(self, e: bool): self._snap_enabled = e

    def set_grid_size(self, g: float): self._grid_size = max(1.0, g)

    def update_data(self, data: TelemetryData): pass

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._prototype.width, self._prototype.height)

    def _render_bg(self):
        w, h = int(self._prototype.width), int(self._prototype.height)
        px = QPixmap(w, h)
        if px.isNull():
            return
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        if not p.isActive():
            return
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            self.paint_background(p)
        finally:
            p.end()
        self._bg_cache = px

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self._bg_cache is None:
            self._render_bg()
        if self._bg_cache:
            painter.drawPixmap(0, 0, self._bg_cache)
        self.paint_foreground(painter)
        if self.isSelected():
            painter.setPen(QPen(self.theme().selection_color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1), 8, 8)

    def paint_background(self, p: QPainter): pass
    def paint_foreground(self, p: QPainter): pass

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and self._snap_enabled and self._grid_size > 0):
            pos = value
            g = self._grid_size
            x, y = round(pos.x() / g) * g, round(pos.y() / g) * g
            s = self.scene()
            if s:
                sr = s.sceneRect()
                w = self.boundingRect().width() * self.scale()
                h = self.boundingRect().height() * self.scale()
                x = max(sr.left(), min(x, sr.right() - w))
                y = max(sr.top(), min(y, sr.bottom() - h))
            return QPointF(x, y)
        return super().itemChange(change, value)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(e)

    def set_theme(self, theme: InstrumentTheme):
        self._theme = theme
        self._bg_cache = None   # invalida la cache dello sfondo
        self.update()

    def theme(self) -> InstrumentTheme:
        """Restituisce il tema attivo, con fallback su un tema base di sicurezza."""
        if self._theme is None:
            self._theme = _theme_base()
        return self._theme

    # =========================================================================
    # STATO SERIALIZZABILE (unificato per tutti i mixin)
    # =========================================================================

    def save_state(self) -> dict:
        """Raccoglie lo stato serializzabile da tutti i mixin presenti."""
        state = {}
        if hasattr(self, "unit_state"):
            state.update(self.unit_state())
        if hasattr(self, "target_state"):
            state.update(self.target_state())
        if hasattr(self, "palette_state"):
            state.update(self.palette_state())
        return state

    def restore_state(self, state: dict):
        """Ripristina lo stato salvato su tutti i mixin presenti."""
        if not state:
            return
        if hasattr(self, "restore_unit_state"):
            self.restore_unit_state(state)
        if hasattr(self, "restore_target_state"):
            self.restore_target_state(state)
        if hasattr(self, "restore_palette_state"):
            self.restore_palette_state(state)


class PlaceholderInstrument(BaseInstrument):
    # Palette interna (non dipende dal tema)
    _BORDER_COLOR = QColor(220, 220, 220)
    _TEXT_COLOR = QColor(220, 220, 220)

    def paint_background(self, p):
        r = self.boundingRect().adjusted(2, 2, -2, -2)
        p.setPen(QPen(self._BORDER_COLOR, 2))
        p.setBrush(QBrush(QColor(self._prototype.color)))
        p.drawRoundedRect(r, 12, 12)
        p.setPen(self._TEXT_COLOR)
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        p.drawText(r.adjusted(8, 8, -8, -8),
                   Qt.AlignmentFlag.AlignCenter,
                   self._prototype.display_name)

class UnitButtonsMixin:
    """Aggiunge pulsanti per il cambio unità di misura."""

    def init_units(self, units, unit_index: int = 0):
        self._units = list(units)
        self._unit_index = unit_index % max(1, len(self._units))
        self._unit_pressed = None
        self._unit_was_movable = True

    def current_unit(self):
        if not getattr(self, "_units", None):
            return None
        return self._units[self._unit_index]

    def cycle_unit(self):
        if not getattr(self, "_units", None):
            return
        self._unit_index = (self._unit_index + 1) % len(self._units)
        self._on_unit_changed()

    def set_unit_index(self, idx: int):
        if 0 <= idx < len(self._units):
            self._unit_index = idx
            self._on_unit_changed()

    def _on_unit_changed(self):
        if hasattr(self, "_bg_cache"):
            self._bg_cache = None
        self.update()

    def unit_round_button_rect(self) -> QRectF:
        br = self.boundingRect()
        size = 16.0
        return QRectF(br.right() - size - 6.0, br.top() + 6.0, size, size)

    def unit_menu_button_rect(self) -> QRectF:
        r = self.unit_round_button_rect()
        return QRectF(r.left() + 2.0, r.bottom() + 4.0, r.width() - 4.0, 10.0)

    def _unit_button_at(self, pos: QPointF):
        if not getattr(self, "_units", None):
            return None
        if self.unit_round_button_rect().contains(pos):
            return "cycle"
        if self.unit_menu_button_rect().contains(pos):
            return "menu"
        return None

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if getattr(self, "_units", None):
            self.paint_unit_buttons(painter)

    def paint_unit_buttons(self, p: QPainter):
        rr = self.unit_round_button_rect()
        mr = self.unit_menu_button_rect()

        p.setPen(QPen(QColor(160, 170, 180), 1))
        p.setBrush(QColor(52, 58, 66))
        p.drawEllipse(rr)

        icon = rr.adjusted(4, 4, -4, -4)
        p.setPen(QPen(QColor(225, 230, 235), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(icon, 40 * 16, 280 * 16)

        c = rr.center()
        radius = icon.width() / 2.0
        ang = math.radians(40)
        ax = c.x() + radius * math.cos(ang)
        ay = c.y() - radius * math.sin(ang)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(225, 230, 235))

        arrow = QPainterPath()
        arrow.moveTo(ax + 3.0, ay)
        arrow.lineTo(ax - 1.0, ay - 2.5)
        arrow.lineTo(ax - 1.0, ay + 2.5)
        arrow.closeSubpath()
        p.drawPath(arrow)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(225, 230, 235))

        tri = QPainterPath()
        tri.moveTo(mr.left(), mr.top())
        tri.lineTo(mr.right(), mr.top())
        tri.lineTo(mr.center().x(), mr.bottom())
        tri.closeSubpath()
        p.drawPath(tri)

    def show_unit_menu(self):
        if not getattr(self, "_units", None):
            return
        menu = QMenu()
        for i, u in enumerate(self._units):
            act = menu.addAction(u.label)
            act.setCheckable(True)
            act.setChecked(i == self._unit_index)
            act.triggered.connect(
                lambda checked=False, idx=i: self.set_unit_index(idx)
            )
        view = None
        if self.scene() and self.scene().views():
            view = self.scene().views()[0]
        if view:
            scene_pos = self.mapToScene(self.unit_menu_button_rect().center())
            view_pos = view.mapFromScene(scene_pos)
            menu.exec(view.mapToGlobal(view_pos))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and getattr(self, "_units", None):
            action = self._unit_button_at(e.pos())
            if action:
                self._unit_pressed = action
                self._unit_was_movable = bool(
                    self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                )
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                e.accept()
                self.update()
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and getattr(self, "_unit_pressed", None):
            pressed = self._unit_pressed
            action = self._unit_button_at(e.pos())
            self._unit_pressed = None
            if self._unit_was_movable:
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            if action == pressed:
                if pressed == "cycle":
                    self.cycle_unit()
                elif pressed == "menu":
                    self.show_unit_menu()
            self.update()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    # =========================================================================
    # SERIALIZZAZIONE STATO UNITÀ
    # =========================================================================

    def unit_state(self) -> dict:
        """Restituisce lo stato serializzabile dell'unità corrente."""
        u = self.current_unit()
        if u:
            return {"unit_id": u.unit_id}
        return {}

    def restore_unit_state(self, state: dict):
        """Ripristina l'unità da uno stato salvato."""
        unit_id = state.get("unit_id")
        if not unit_id:
            return
        units = getattr(self, "_units", None)
        if not units:
            return
        for i, u in enumerate(units):
            if u.unit_id == unit_id:
                self._unit_index = i
                self._on_unit_changed()
                self.update()
                return

class TurnTargetMixin:
    """
    Aggiunge un target di turn rate regolabile:
    - Due tacche simmetriche (bug) che indicano il target
    - Due pulsanti a freccia (▲ aumenta / ▼ diminuisce)
    """

    def init_turn_target(self, default_rate: float = 3.0):
        self._target_rate = default_rate
        self._target_min = 0.5
        self._target_max = 9.0
        self._target_step = 0.5
        self._target_pressed = None
        self._target_was_movable = True

    # =========================================================================
    # VALORE TARGET
    # =========================================================================

    def target_rate(self) -> float:
        return self._target_rate

    def target_display_angle(self) -> float:
        # 3°/sec = 10° sul display
        return self._target_rate * (10.0 / 3.0)

    def _increase_target(self):
        self._target_rate = min(self._target_max, self._target_rate + self._target_step)
        self.update()

    def _decrease_target(self):
        self._target_rate = max(self._target_min, self._target_rate - self._target_step)
        self.update()

    # =========================================================================
    # GEOMETRIA PULSANTI
    # =========================================================================

    def target_inc_button_rect(self) -> QRectF:
        br = self.boundingRect()
        size = 16.0
        return QRectF(br.right() - size - 6.0, br.top() + 6.0, size, size)

    def target_dec_button_rect(self) -> QRectF:
        r = self.target_inc_button_rect()
        return QRectF(r.left(), r.bottom() + 4.0, r.width(), r.height())

    def _target_button_at(self, pos: QPointF):
        if self.target_inc_button_rect().contains(pos):
            return "inc"
        if self.target_dec_button_rect().contains(pos):
            return "dec"
        return None

    # =========================================================================
    # DISEGNO PULSANTI + READOUT
    # =========================================================================

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        self.paint_target_buttons(painter)

    def paint_target_buttons(self, p: QPainter):
        inc = self.target_inc_button_rect()
        dec = self.target_dec_button_rect()

        # Sfondo pulsanti
        for r in (inc, dec):
            p.setPen(QPen(QColor(160, 170, 180), 1))
            p.setBrush(QColor(52, 58, 66))
            p.drawRoundedRect(r, 3, 3)

        self._draw_arrow(p, inc, up=True)
        self._draw_arrow(p, dec, up=False)

        # Readout del valore target
        p.setPen(QColor(0, 220, 255))
        rf = p.font()
        rf.setPixelSize(9)
        rf.setBold(True)
        p.setFont(rf)
        readout_rect = QRectF(inc.left() - 8, dec.bottom() + 3, inc.width() + 16, 12)
        p.drawText(readout_rect, Qt.AlignmentFlag.AlignCenter, f"{self._target_rate:.1f}")

    def _draw_arrow(self, p: QPainter, rect: QRectF, up: bool):
        cx = rect.center().x()
        cy = rect.center().y()
        s = rect.width() * 0.28
        tri = QPainterPath()
        if up:
            tri.moveTo(cx, cy - s)
            tri.lineTo(cx - s, cy + s * 0.7)
            tri.lineTo(cx + s, cy + s * 0.7)
        else:
            tri.moveTo(cx, cy + s)
            tri.lineTo(cx - s, cy - s * 0.7)
            tri.lineTo(cx + s, cy - s * 0.7)
        tri.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(225, 230, 235))
        p.drawPath(tri)

    # =========================================================================
    # TACCHE TARGET (da chiamare in paint_foreground)
    # =========================================================================

    def draw_target_ticks(self, p: QPainter, cx: float, cy: float,
                          tick_r: float, color=None):
        if color is None:
            color = QColor(0, 220, 255)
        angle = self.target_display_angle()
        for sign in (-1, 1):
            deg = sign * angle
            p.save()
            p.translate(cx, cy)
            p.rotate(deg)
            bug = QPainterPath()
            bug.moveTo(0, -tick_r)
            bug.lineTo(-5, -tick_r + 10)
            bug.lineTo(5, -tick_r + 10)
            bug.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPath(bug)
            p.restore()

    # =========================================================================
    # GESTIONE MOUSE
    # =========================================================================

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            action = self._target_button_at(e.pos())
            if action:
                self._target_pressed = action
                self._target_was_movable = bool(
                    self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                )
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                e.accept()
                self.update()
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and getattr(self, "_target_pressed", None):
            pressed = self._target_pressed
            action = self._target_button_at(e.pos())
            self._target_pressed = None
            if self._target_was_movable:
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            if action == pressed:
                if pressed == "inc":
                    self._increase_target()
                elif pressed == "dec":
                    self._decrease_target()
            self.update()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    # =========================================================================
    # SERIALIZZAZIONE STATO TARGET
    # =========================================================================

    def target_state(self) -> dict:
        """Restituisce lo stato serializzabile del target turn rate."""
        return {"target_rate": self._target_rate}

    def restore_target_state(self, state: dict):
        """Ripristina il target turn rate da uno stato salvato."""
        rate = state.get("target_rate")
        if rate is None:
            return
        self._target_rate = max(self._target_min,
                                min(self._target_max, float(rate)))
        self.update()

class ColorSelectorMixin:
    """
    Aggiunge un selettore di palette in basso a destra.
    La classe concreta deve definire:
      - _PALETTES: dict {chiave: palette_dict}
      - _PALETTE_ORDER: lista di chiavi per il ciclo
    E chiamare init_color_selector(default_key) in __init__.
    """

    _PALETTES = {}
    _PALETTE_ORDER = []

    def init_color_selector(self, default_key: str = "orange"):
        self._palette_key = default_key
        self._palette = self._PALETTES[default_key]
        self._color_btn_pressed = False
        self._color_was_movable = True

    def current_palette(self) -> dict:
        return self._palette

    # =========================================================================
    # GEOMETRIA PULSANTE
    # =========================================================================

    def color_button_rect(self):
        br = self.boundingRect()
        size = 18.0
        return QRectF(br.right() - size - 6.0, br.bottom() - size - 6.0, size, size)

    # =========================================================================
    # LOGICA
    # =========================================================================

    def _cycle_palette(self):
        idx = self._PALETTE_ORDER.index(self._palette_key)
        self._palette_key = self._PALETTE_ORDER[(idx + 1) % len(self._PALETTE_ORDER)]
        self._palette = self._PALETTES[self._palette_key]
        self._bg_cache = None
        self.update()

    # =========================================================================
    # DISEGNO
    # =========================================================================

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

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        self._paint_color_button(painter)

    # =========================================================================
    # MOUSE
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

    # =========================================================================
    # SERIALIZZAZIONE STATO PALETTE
    # =========================================================================

    def palette_state(self) -> dict:
        """Restituisce lo stato serializzabile della palette corrente."""
        return {"palette_key": self._palette_key}

    def restore_palette_state(self, state: dict):
        """Ripristina la palette da uno stato salvato."""
        key = state.get("palette_key")
        if not key or key not in self._PALETTES:
            return
        self._palette_key = key
        self._palette = self._PALETTES[key]
        self._bg_cache = None
        self.update()




