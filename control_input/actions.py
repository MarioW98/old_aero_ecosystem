"""
control_input/actions.py

Catalogo delle azioni di volo disponibili.

Ogni azione ha un tipo che determina come viene gestita:
- INCREMENTAL: tenere premuto cambia continuamente il valore (throttle)
- POSITIONAL: tenere premuto imposta un valore, rilascio torna a 0 (stick)
- MOMENTARY: pressione singola scatena un evento (pause, reset)

Il catalogo è estendibile: aggiungere nuove azioni qui le rende
automaticamente disponibili nel KeyBindingManager e nella UI.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass


class ActionType(Enum):
    """Tipo di azione, determina il comportamento dell'input."""
    INCREMENTAL = "incremental"   # Hold → cambia continuamente
    POSITIONAL = "positional"     # Hold → valore attivo, release → 0
    MOMENTARY = "momentary"       # Press → evento singolo


@dataclass(frozen=True)
class ActionDef:
    """Definizione di un'azione di volo."""
    action_id: str          # Identificatore univoco (es. "throttle_up")
    display_name: str       # Nome per la UI (es. "Throttle +")
    action_type: ActionType # Tipo di comportamento
    category: str           # Categoria per raggruppamento UI


# ======================================================================
# CATALOGO AZIONI
# ======================================================================
# Per aggiungere una nuova azione, aggiungere una riga qui.
# Il KeyBindingManager e la UI la riconosceranno automaticamente.

ACTIONS: dict[str, ActionDef] = {
    # --- Motore ---
    "throttle_up": ActionDef(
        action_id="throttle_up",
        display_name="Throttle +",
        action_type=ActionType.INCREMENTAL,
        category="Motore",
    ),
    "throttle_down": ActionDef(
        action_id="throttle_down",
        display_name="Throttle −",
        action_type=ActionType.INCREMENTAL,
        category="Motore",
    ),

    # --- Volo (stick) ---
    "pitch_up": ActionDef(
        action_id="pitch_up",
        display_name="Pitch Up (Naso Su)",
        action_type=ActionType.POSITIONAL,
        category="Volo",
    ),
    "pitch_down": ActionDef(
        action_id="pitch_down",
        display_name="Pitch Down (Naso Giù)",
        action_type=ActionType.POSITIONAL,
        category="Volo",
    ),
    "roll_left": ActionDef(
        action_id="roll_left",
        display_name="Roll Sinistra",
        action_type=ActionType.POSITIONAL,
        category="Volo",
    ),
    "roll_right": ActionDef(
        action_id="roll_right",
        display_name="Roll Destra",
        action_type=ActionType.POSITIONAL,
        category="Volo",
    ),
    "yaw_left": ActionDef(
        action_id="yaw_left",
        display_name="Yaw Sinistra",
        action_type=ActionType.POSITIONAL,
        category="Volo",
    ),
    "yaw_right": ActionDef(
        action_id="yaw_right",
        display_name="Yaw Destra",
        action_type=ActionType.POSITIONAL,
        category="Volo",
    ),

    # --- Sistema ---
    "pause": ActionDef(
        action_id="pause",
        display_name="Pausa Simulazione",
        action_type=ActionType.MOMENTARY,
        category="Sistema",
    ),
    "reset": ActionDef(
        action_id="reset",
        display_name="Reset Simulazione",
        action_type=ActionType.MOMENTARY,
        category="Sistema",
    ),
}


def get_action(action_id: str) -> ActionDef | None:
    """Ritorna la definizione di un'azione per ID."""
    return ACTIONS.get(action_id)


def get_actions_by_category() -> dict[str, list[ActionDef]]:
    """Raggruppa le azioni per categoria (utile per la UI)."""
    categories: dict[str, list[ActionDef]] = {}
    for action in ACTIONS.values():
        categories.setdefault(action.category, []).append(action)
    return categories