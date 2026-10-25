from __future__ import annotations
from dataclasses import dataclass, field

from PySide6.QtGui import QColor


# =============================================================================
# CLASSE TEMA
# =============================================================================

@dataclass
class InstrumentTheme:
    """
    Parametri visivi per la scena e la selezione.
    
    I colori degli strumenti sono gestiti internamente da ogni strumento
    (vedi classi in instruments/). Il tema controlla solo:
    - Sfondo della scena
    - Colore della griglia
    - Colore del rettangolo di selezione
    """

    # --- Identificazione ---
    theme_id: str
    display_name: str
    family: str = ""
    description: str = ""

    # --- Scena ---
    scene_background: QColor = field(default_factory=lambda: QColor(15, 18, 25))
    grid_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 18))

    # --- Selezione ---
    selection_color: QColor = field(default_factory=lambda: QColor(255, 193, 7))


# =============================================================================
# REGISTRY DEI TEMI
# =============================================================================

class ThemeRegistry:
    """Catalogo dei temi disponibili."""

    def __init__(self) -> None:
        self._themes: dict[str, InstrumentTheme] = {}
        self._order: list[str] = []
        self._default_id: str | None = None

    def register(self, theme: InstrumentTheme, is_default: bool = False) -> None:
        if theme.theme_id in self._themes:
            raise ValueError(f"Tema già registrato: {theme.theme_id}")
        self._themes[theme.theme_id] = theme
        self._order.append(theme.theme_id)
        if is_default or self._default_id is None:
            self._default_id = theme.theme_id

    def get(self, theme_id: str) -> InstrumentTheme | None:
        return self._themes.get(theme_id)

    def default(self) -> InstrumentTheme | None:
        if self._default_id:
            return self._themes.get(self._default_id)
        return next(iter(self._themes.values()), None) if self._themes else None

    def themes(self) -> list[InstrumentTheme]:
        return [self._themes[tid] for tid in self._order]

    def theme_ids(self) -> tuple[str, ...]:
        return tuple(self._order)

    def set_default(self, theme_id: str) -> None:
        if theme_id in self._themes:
            self._default_id = theme_id


# =============================================================================
# TEMA BASE
# =============================================================================

def _theme_base() -> InstrumentTheme:
    """Tema Base: sfondo canapa chiaro."""
    return InstrumentTheme(
        theme_id="base",
        display_name="Base",
        family="base",
        description="Stile originale del simulatore",
        scene_background=QColor(230, 218, 188),  # Canapa
        grid_color=QColor(180, 168, 145),         # Canapa scuro
        selection_color=QColor(0, 120, 215),      # Blu
    )


# =============================================================================
# TEMA NIGHT (alternativa di test)
# =============================================================================

def _theme_night() -> InstrumentTheme:
    """
    Tema Night: sfondo scuro con griglia sottile.
    """
    return InstrumentTheme(
        theme_id="night",
        display_name="Night",
        family="night",
        description="Tema notturno",
        scene_background=QColor(15, 18, 25),      # Scuro
        grid_color=QColor(40, 45, 55),            # Grigio scuro
        selection_color=QColor(0, 200, 200),      # Ciano
    )


# =============================================================================
# COSTRUZIONE DEFAULT
# =============================================================================

def build_default_themes() -> ThemeRegistry:
    """Crea il registry con i temi disponibili."""
    registry = ThemeRegistry()
    registry.register(_theme_base(), is_default=True)
    registry.register(_theme_night())
    return registry