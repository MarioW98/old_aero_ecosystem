"""
control_input/input_state.py

Stato normalizzato dei comandi di volo.

È l'output comune di tutte le sorgenti di input (tastiera, joystick).
Il simulatore e il flight controller lavorano solo con questo formato.

Convenzioni:
- throttle: [0, 1], 0 = minimo, 1 = massima potenza
- pitch_stick: [-1, 1], positivo = muso su
- roll_stick: [-1, 1], positivo = rollio destro
- yaw_stick: [-1, 1], positivo = imbardata destra
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class InputState:
    """Stato normalizzato dei comandi di volo."""

    throttle: float = 0.0       # [0, 1]
    pitch_stick: float = 0.0    # [-1, 1], positivo = muso su
    roll_stick: float = 0.0     # [-1, 1], positivo = roll destro
    yaw_stick: float = 0.0      # [-1, 1], positivo = yaw destro

    def clamp(self) -> 'InputState':
        """Restituisce una copia con i valori clampati nei range validi."""
        return InputState(
            throttle=max(0.0, min(1.0, self.throttle)),
            pitch_stick=max(-1.0, min(1.0, self.pitch_stick)),
            roll_stick=max(-1.0, min(1.0, self.roll_stick)),
            yaw_stick=max(-1.0, min(1.0, self.yaw_stick)),
        )