"""
simulator/dynamics/propulsion/propeller.py

Modello dell'elica: converte la potenza del motore in spinta
e calcola gli effetti secondari.

D3.1 refactored: l'elica è un componente separato dal motore.
Riceve la potenza dal motore e produce:
- Spinta (lungo +x_body)
- Coppia reattiva (momento di imbardata)
- P-factor (momento di rollio ad alto alpha)
- Momento di beccheggio da offset della linea di spinta
"""

from __future__ import annotations

import numpy as np


class PropellerConfig:
    """Configurazione dell'elica."""

    def __init__(self,
                 eta: float = 0.80,
                 T_static_max: float = 4500.0,
                 V_min: float = 5.0,
                 k_yaw: float = 0.02,
                 k_roll: float = 0.005,
                 thrust_offset_z: float = -0.1,
                 thrust_offset_y: float = 0.0):
        """
        Args:
            eta: efficienza dell'elica (0.7-0.85 tipica).
            T_static_max: spinta statica massima a piena potenza [N].
            V_min: velocità minima sotto la quale si usa il modello statico [m/s].
            k_yaw: coefficiente momento imbardata per unità di spinta.
                   k_yaw > 0 → Mz = -k_yaw * T (yaw sinistro per elica oraria).
            k_roll: coefficiente P-factor [1/rad].
            thrust_offset_z: offset verticale linea di spinta dal CG [m].
                             Negativo = sotto il CG → My > 0 (nose-up).
            thrust_offset_y: offset laterale linea di spinta dal CG [m].
        """
        self.eta = eta
        self.T_static_max = T_static_max
        self.V_min = V_min
        self.k_yaw = k_yaw
        self.k_roll = k_roll
        self.thrust_offset_z = thrust_offset_z
        self.thrust_offset_y = thrust_offset_y


class PropellerModel:
    """
    Modello dell'elica: converte potenza in spinta + effetti secondari.

    Uso:
        prop = PropellerModel(config)
        thrust, moments = prop.compute(power, velocity, alpha)
    """

    def __init__(self, config: PropellerConfig):
        self.config = config

    def compute(self, power: float, velocity: float,
                alpha: float = 0.0) -> tuple:
        """
        Calcola spinta e momenti dell'elica.

        Args:
            power: potenza ricevuta dal motore [W].
            velocity: velocità del velivolo [m/s].
            alpha: angolo di attacco [rad] (per il P-factor).

        Returns:
            (thrust, moments_body):
            - thrust: spinta [N]
            - moments_body: np.array [Mx, My, Mz] [N·m]
        """
        cfg = self.config

        if power < 1e-6:
            return 0.0, np.zeros(3)

        # ==================================================================
        # 1. SPINTA
        # ==================================================================
        if velocity > cfg.V_min:
            # Modello dinamico: T = η · P / V
            thrust = cfg.eta * power / velocity
        else:
            # Modello statico: proporzionale alla potenza
            # (evita divisione per zero a V=0)
            thrust = cfg.T_static_max * (power / max(power, 1e-6))
            # Clamp: non superare la spinta statica massima
            thrust = min(thrust, cfg.T_static_max)

        # ==================================================================
        # 2. MOMENTI (effetti secondari dell'elica)
        # ==================================================================
        # P-factor: proporzionale a spinta e alpha
        Mx = cfg.k_roll * thrust * alpha

        # Offset verticale della linea di spinta → momento di beccheggio
        My = -cfg.thrust_offset_z * thrust

        # Coppia reattiva → momento di imbardata
        Mz = -cfg.k_yaw * thrust

        # Offset laterale → momento di imbardata aggiuntivo
        Mz += cfg.thrust_offset_y * thrust

        moments_body = np.array([Mx, My, Mz])

        return thrust, moments_body


# ======================================================================
# CONFIGURAZIONI PREDEFINITE
# ======================================================================

def make_c172_propeller() -> PropellerConfig:
    """Elica tipo Cessna 172 (McCaulley 1A170, passo fisso)."""
    return PropellerConfig(
        eta=0.80,
        T_static_max=4500.0,
        V_min=5.0,
        k_yaw=0.02,
        k_roll=0.005,
        thrust_offset_z=-0.1,
        thrust_offset_y=0.0,
    )


def make_generic_propeller() -> PropellerConfig:
    """Elica generica per test (nessun effetto secondario)."""
    return PropellerConfig(
        eta=0.85,
        T_static_max=5000.0,
        V_min=5.0,
        k_yaw=0.0,
        k_roll=0.0,
        thrust_offset_z=0.0,
        thrust_offset_y=0.0,
    )