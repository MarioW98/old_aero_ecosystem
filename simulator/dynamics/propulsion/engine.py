"""
simulator/dynamics/propulsion/engine.py

Modello del motore (solo generazione di potenza).

D3.1 refactored: il motore genera potenza e coppia all'albero.
NON calcola spinta né effetti aerodinamici: quelli sono
responsabilità dell'elica (propeller.py).

Modello lineare e stazionario:
- Potenza: P = P_max · throttle
- RPM: rpm = rpm_idle + (rpm_max - rpm_idle) · throttle
- Coppia: τ = P / ω
"""

from __future__ import annotations

import math


class EngineConfig:
    """Configurazione del motore."""

    def __init__(self,
                 P_max: float,
                 rpm_max: float = 2700.0,
                 rpm_idle: float = 700.0):
        """
        Args:
            P_max: potenza massima [W].
            rpm_max: giri massimi [giri/min].
            rpm_idle: giri al minimo [giri/min].
        """
        self.P_max = P_max
        self.rpm_max = rpm_max
        self.rpm_idle = rpm_idle


class EngineModel:
    """
    Modello del motore: genera potenza e coppia all'albero.

    Uso:
        engine = EngineModel(config)
        power, torque, rpm = engine.compute(throttle)
    """

    def __init__(self, config: EngineConfig):
        self.config = config

    def compute(self, throttle: float) -> tuple:
        """
        Calcola potenza, coppia e RPM del motore.

        Args:
            throttle: comando gas [0, 1].

        Returns:
            (power, torque, rpm):
            - power: potenza all'albero [W]
            - torque: coppia all'albero [N·m]
            - rpm: giri motore [giri/min]
        """
        throttle = max(0.0, min(1.0, throttle))
        cfg = self.config

        # Potenza (modello lineare)
        power = cfg.P_max * throttle

        # RPM
        rpm = cfg.rpm_idle + (cfg.rpm_max - cfg.rpm_idle) * throttle

        # Coppia: τ = P / ω
        omega = rpm * 2.0 * math.pi / 60.0  # rad/s
        torque = power / omega if omega > 1e-6 else 0.0

        return power, torque, rpm


# ======================================================================
# CONFIGURAZIONI PREDEFINITE
# ======================================================================

def make_c172_engine() -> EngineConfig:
    """Cessna 172: Lycoming O-320, 160 HP ≈ 119 kW."""
    return EngineConfig(
        P_max=119000.0,   # W (160 HP)
        rpm_max=2700.0,
        rpm_idle=700.0,
    )


def make_generic_engine() -> EngineConfig:
    """Motore generico per test."""
    return EngineConfig(
        P_max=150000.0,
        rpm_max=3000.0,
        rpm_idle=800.0,
    )