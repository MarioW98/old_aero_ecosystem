"""
flight_controller/fc_config.py

Contenitori dei parametri del controllore.

IMPORTANTE (post-pulizia): questo modulo NON contiene più guadagni hardcoded.
I guadagni Kp/Ki/Kd sono il RISULTATO del calcolo model-based (T1/T2) e
vengono popolati qui da fuori. Le dataclass sono solo il contenitore typed
del risultato, per passarli al RateController / AttitudeController.

I limiti attuatori (max_delta_*) e il trim sono parametri FISICI del velivolo,
non guadagni PID: anch'essi verranno estratti dalla config velivolo in T1.
Per ora restano qui come campi della dataclass, popolati dal chiamante.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AxisGains:
    """Guadagni PID per un singolo asse (risultato del calcolo model-based)."""
    kp: float
    ki: float
    kd: float


@dataclass
class ActuatorLimits:
    """Limiti fisici di deflessione superficie [rad]. Parametro velivolo."""
    max_delta_a: float
    max_delta_e: float
    max_delta_r: float


@dataclass
class RateConfig:
    """
    Configurazione completa del rate controller.

    Popolata dal calcolatore model-based (T2), non a mano.
    I segni di direzione incorporano la fisica aero del velivolo:
    - sign_roll:   +1 se Cl_delta_a > 0 (delta_a>0 → roll destro)
    - sign_pitch:  -1 se Cm_delta_e < 0 (delta_e>0 → nose-down)
    - sign_yaw:    +1 se Cn_delta_r > 0 (delta_r>0 → yaw destro)
    """
    roll: AxisGains
    pitch: AxisGains
    yaw: AxisGains
    limits: ActuatorLimits

    # Trim di equilibrio (offset fisico di superficie, rad). Parametro velivolo.
    trim_delta_a: float = 0.0
    trim_delta_e: float = 0.0
    trim_delta_r: float = 0.0

    # Segni di direzione (dalla fisica aero del velivolo).
    sign_roll: float = 1.0
    sign_pitch: float = -1.0
    sign_yaw: float = 1.0

    # Coefficiente filtro passabasso sul termine D.
    deriv_filter_alpha: float = 0.5