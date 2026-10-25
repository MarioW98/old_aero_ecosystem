"""
simulator/dynamics/propulsion/powerplant.py

Powerplant: compone motore + elica e produce forze/momenti totali.

D3.1 refactored: questo è il punto di ingresso per la propulsione.
Il resto del simulatore usa solo questa classe.

Flusso:
    throttle → EngineModel → (potenza, RPM)
                                  ↓
                  PropellerModel → (spinta, momenti)
                                  ↓
                  Powerplant     → forze/momenti nel body frame
"""

from __future__ import annotations

import numpy as np

from .engine import EngineModel, EngineConfig
from .propeller import PropellerModel, PropellerConfig


class Powerplant:
    """
    Powerplant: motore + elica.

    Uso:
        pp = Powerplant(engine, propeller)
        forces, moments, telemetry = pp.compute(throttle, velocity, alpha)
    """

    def __init__(self, engine: EngineModel, propeller: PropellerModel):
        """
        Args:
            engine: modello del motore.
            propeller: modello dell'elica.
        """
        self.engine = engine
        self.propeller = propeller

    def compute(self, throttle: float, velocity: float,
                alpha: float = 0.0) -> tuple:
        """
        Calcola forze e momenti totali della propulsione.

        Args:
            throttle: comando gas [0, 1].
            velocity: velocità del velivolo [m/s].
            alpha: angolo di attacco [rad].

        Returns:
            (forces_body, moments_body, telemetry_dict):
            - forces_body: np.array [Fx, Fy, Fz] [N]
            - moments_body: np.array [Mx, My, Mz] [N·m]
            - telemetry_dict: dict con dati per telemetria
        """
        # Motore: potenza e RPM
        power, torque, rpm = self.engine.compute(throttle)

        # Elica: spinta e momenti
        thrust, moments_body = self.propeller.compute(power, velocity, alpha)

        # Forza lungo x_body (avanti)
        forces_body = np.array([thrust, 0.0, 0.0])

        # Telemetria
        telemetry_dict = {
            'thrust': thrust,
            'throttle': throttle,
            'rpm': rpm,
            'power': power,
            'torque': torque,
        }

        return forces_body, moments_body, telemetry_dict


# ======================================================================
# CONFIGURAZIONI PREDEFINITE (composizioni complete)
# ======================================================================

def make_c172_powerplant() -> Powerplant:
    """Powerplant tipo Cessna 172."""
    from .engine import make_c172_engine
    from .propeller import make_c172_propeller
    engine = EngineModel(make_c172_engine())
    propeller = PropellerModel(make_c172_propeller())
    return Powerplant(engine, propeller)


def make_generic_powerplant() -> Powerplant:
    """Powerplant generico per test."""
    from .engine import make_generic_engine
    from .propeller import make_generic_propeller
    engine = EngineModel(make_generic_engine())
    propeller = PropellerModel(make_generic_propeller())
    return Powerplant(engine, propeller)