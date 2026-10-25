"""
simulator/dynamics/aero/forces.py

Calcolo delle forze e dei momenti aerodinamici nel body frame.

D2.2: Ponte tra aerodinamica (coefficienti) e dinamica (forze).

Flusso:
1. Calcola alpha, beta dalla velocità nel body frame.
2. Calcola la pressione dinamica q = ½ρV².
3. Calcola i coefficienti aerodinamici (D2.1).
4. Calcola le forze nel wind frame (Lift, Drag, Side).
5. Trasforma le forze nel body frame.
6. Calcola i momenti nel body frame.
"""

from __future__ import annotations

import numpy as np

from ..state import AircraftState
from ..atmosphere import Atmosphere
from .coefficients import AeroCoefficients


# Velocità minima sotto la quale le forze aerodinamiche sono nulle
_MIN_AIRSPEED = 0.1  # m/s


class AeroForces:
    """
    Calcola forze e momenti aerodinamici nel body frame.

    Uso:
        aero_forces = AeroForces(aero_coefficients)
        forces, moments = aero_forces.compute(state, controls)
    """

    def __init__(self, aero: AeroCoefficients):
        """
        Args:
            aero: oggetto AeroCoefficients con le tabelle aerodinamiche.
        """
        self.aero = aero

    # ------------------------------------------------------------------
    # Calcolo principale
    # ------------------------------------------------------------------
    def compute(self, state: AircraftState,
                controls: dict | None = None) -> tuple[np.ndarray, np.ndarray]:
        """
        Calcola forze e momenti aerodinamici nel body frame.

        Args:
            state: stato corrente del velivolo.
            controls: dict con le deflessioni delle superfici [rad]:
                      {'delta_e': ..., 'delta_a': ..., 'delta_r': ...}
                      Se None, tutte le superfici sono neutre.

        Returns:
            (forces_body, moments_body): tuple di np.array di 3 elementi.
            forces_body: [Fx, Fy, Fz] nel body frame [N].
            moments_body: [Mx, My, Mz] nel body frame [N·m].
        """
        if controls is None:
            controls = {}

        u, v, w = state.velocity_body
        V = float(np.sqrt(u ** 2 + v ** 2 + w ** 2))

        # Velocità troppo bassa: forze aerodinamiche nulle
        if V < _MIN_AIRSPEED:
            return np.zeros(3), np.zeros(3)

        # ==================================================================
        # 1. ANGOLI AERODINAMICI
        # ==================================================================
        alpha = float(np.arctan2(w, u))
        beta = float(np.arcsin(np.clip(v / V, -1.0, 1.0)))

        # ==================================================================
        # 2. PRESSIONE DINAMICA
        # ==================================================================
        altitude = state.altitude
        rho = Atmosphere.density(altitude)
        q = 0.5 * rho * V ** 2

        # ==================================================================
        # 3. VELOCITÀ ANGOLARI ADIMENSIONALI
        # ==================================================================
        p, q_rate, r = state.angular_velocity
        cfg = self.aero.config
        p_hat = p * cfg.b_ref / (2.0 * V)
        q_hat = q_rate * cfg.c_ref / (2.0 * V)
        r_hat = r * cfg.b_ref / (2.0 * V)

        # ==================================================================
        # 4. COEFFICIENTI AERODINAMICI (da D2.1)
        # ==================================================================
        delta_e = controls.get('delta_e', 0.0)
        delta_a = controls.get('delta_a', 0.0)
        delta_r = controls.get('delta_r', 0.0)

        coeffs = self.aero.compute(
            alpha=alpha, beta=beta,
            delta_e=delta_e, delta_a=delta_a, delta_r=delta_r,
            p_hat=p_hat, q_hat=q_hat, r_hat=r_hat,
        )

        CL = coeffs['CL']
        CD = coeffs['CD']
        Cm = coeffs['Cm']
        Cl = coeffs['Cl']
        Cn = coeffs['Cn']
        CY = coeffs['CY']

        # ==================================================================
        # 5. FORZE NEL WIND FRAME
        # ==================================================================
        S = cfg.S_ref
        D = CD * q * S   # Drag (opposto alla velocità)
        L = CL * q * S   # Lift (verso l'alto nel wind frame)
        Y = CY * q * S   # Side force

        # ==================================================================
        # 6. TRASFORMAZIONE WIND → BODY FRAME
        # ==================================================================
        cos_a = np.cos(alpha)
        sin_a = np.sin(alpha)
        cos_b = np.cos(beta)
        sin_b = np.sin(beta)

        # Matrice di rotazione wind → body: R = R_y(α) · R_z(β)
        Fx = -D * cos_a * cos_b - Y * cos_a * sin_b - L * sin_a
        Fy = -D * sin_b + Y * cos_b
        Fz = D * sin_a * cos_b + Y * sin_a * sin_b - L * cos_a

        forces_body = np.array([Fx, Fy, Fz])

        # ==================================================================
        # 7. MOMENTI NEL BODY FRAME
        # ==================================================================
        b = cfg.b_ref
        c = cfg.c_ref

        Mx = Cl * q * S * b   # Roll moment
        My = Cm * q * S * c   # Pitch moment
        Mz = Cn * q * S * b   # Yaw moment

        moments_body = np.array([Mx, My, Mz])

        return forces_body, moments_body

    # ------------------------------------------------------------------
    # Utility: calcolo di alpha e beta (utile anche all'esterno)
    # ------------------------------------------------------------------
    @staticmethod
    def compute_alpha_beta(velocity_body: np.ndarray) -> tuple[float, float]:
        """
        Calcola alpha e beta dalla velocità nel body frame.

        Args:
            velocity_body: [u, v, w] in m/s.

        Returns:
            (alpha, beta) in radianti.
        """
        u, v, w = velocity_body
        V = float(np.sqrt(u ** 2 + v ** 2 + w ** 2))
        if V < _MIN_AIRSPEED:
            return 0.0, 0.0
        alpha = float(np.arctan2(w, u))
        beta = float(np.arcsin(np.clip(v / V, -1.0, 1.0)))
        return alpha, beta