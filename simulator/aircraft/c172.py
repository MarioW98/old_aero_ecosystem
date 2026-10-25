"""
simulator/aircraft/c172.py

Configurazione tipo Cessna 172.

Dati approssimativi basati su letteratura pubblica.
Non è un modello fedele al 100%, ma è sufficiente per validare
l'architettura del simulatore.
"""

from __future__ import annotations

from .config import AircraftConfig
from dynamics.aero.coefficients import make_c172_config
from dynamics.propulsion.engine import make_c172_engine
from dynamics.propulsion.propeller import make_c172_propeller


def make_c172_aircraft() -> AircraftConfig:
    """
    Crea la configurazione completa del C172.

    Massa: ~1000 kg (peso tipico al decollo)
    Inerzia: valori approssimativi per un aereo leggero
    """
    return AircraftConfig(
        name="C172",
        mass=1000.0,
        inertia={
            'Ixx': 1500.0,    # kg·m² (roll)
            'Iyy': 2500.0,    # kg·m² (pitch)
            'Izz': 3000.0,    # kg·m² (yaw)
            'Ixz': 0.0,       # kg·m² (cross-coupling)
        },
        aero_config=make_c172_config(),
        engine_config=make_c172_engine(),
        propeller_config=make_c172_propeller(),
    )