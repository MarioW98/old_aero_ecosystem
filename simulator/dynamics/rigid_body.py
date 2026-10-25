"""
simulator/dynamics/rigid_body.py

Equazioni del moto 6-DoF per un corpo rigido.

D1.3: Fondamenta — equazioni del moto.

Questo modulo calcola le DERIVATE dello stato (accelerazioni, derivate del
quaternione) date le forze e i momenti totali nel body frame. NON integra
nel tempo: l'integrazione è compito dell'integratore (D1.4).

Convenzioni:
- Frame body: x avanti, y destra, z verso il basso.
- Frame NED: North-East-Down.
- Velocità e velocità angolari nel body frame.
- Forze e momenti nel body frame.
"""

from __future__ import annotations

import numpy as np

from .state import Quaternion, AircraftState


class RigidBodyDynamics:
    """
    Equazioni del moto 6-DoF per un corpo rigido.

    Incapsula massa e matrice d'inerzia del velivolo, e calcola le
    derivate dello stato date le forze e i momenti nel body frame.

    Uso:
        dynamics = RigidBodyDynamics(mass=1000.0, inertia={...})
        derivs = dynamics.compute_derivatives(state, forces, moments)
    """

    def __init__(self, mass: float, inertia: dict):
        """
        Args:
            mass: massa del velivolo [kg]
            inertia: dict con le componenti della matrice d'inerzia [kg·m²]:
                     {'Ixx': ..., 'Iyy': ..., 'Izz': ..., 'Ixz': ...}
                     Ixz è opzionale (default 0).
        """
        self.mass = mass
        self.Ixx = inertia['Ixx']
        self.Iyy = inertia['Iyy']
        self.Izz = inertia['Izz']
        self.Ixz = inertia.get('Ixz', 0.0)

    # ------------------------------------------------------------------
    # Equazioni del moto
    # ------------------------------------------------------------------
    def compute_derivatives(self, state: AircraftState,
                            forces_body: np.ndarray,
                            moments_body: np.ndarray) -> dict:
        """
        Calcola le derivate dello stato.

        Args:
            state: stato corrente del velivolo.
            forces_body: forze totali nel body frame [Fx, Fy, Fz] [N].
            moments_body: momenti totali nel body frame [Mx, My, Mz] [N·m].

        Returns:
            dict con le derivate:
            - 'position_dot': np.array [ṗN, ṗE, ṗD] [m/s]
            - 'velocity_dot': np.array [u̇, v̇, ẇ] [m/s²]
            - 'attitude_dot': tuple (q̇w, q̇x, q̇y, q̇z) [1/s]
            - 'angular_velocity_dot': np.array [ṗ, q̇, ṙ] [rad/s²]
        """
        u, v, w = state.velocity_body
        p, q, r = state.angular_velocity
        quat = state.attitude

        # ==================================================================
        # 1. CINEMATICA DELLA POSIZIONE
        # ==================================================================
        # La velocità nel frame NED è la velocità body ruotata nel NED.
        # ṗ_NED = R(q) · [u, v, w]
        position_dot = quat.rotate_vector(state.velocity_body)

        # ==================================================================
        # 2. DINAMICA TRASLAZIONALE (2ª legge di Newton nel body frame)
        # ==================================================================
        # m·(v̇ + ω×v) = F  →  v̇ = F/m − ω×v
        # Componenti nel body frame:
        #   u̇ = Fx/m + r·v − q·w
        #   v̇ = Fy/m + p·w − r·u
        #   ẇ = Fz/m + q·u − p·v
        Fx, Fy, Fz = forces_body
        u_dot = Fx / self.mass + r * v - q * w
        v_dot = Fy / self.mass + p * w - r * u
        w_dot = Fz / self.mass + q * u - p * v
        velocity_dot = np.array([u_dot, v_dot, w_dot])

        # ==================================================================
        # 3. CINEMATICA DELL'ASSETTO (derivata del quaternione)
        # ==================================================================
        # q̇ = ½ · q ⊗ [0, p, q, r]
        qw, qx, qy, qz = quat.w, quat.x, quat.y, quat.z
        qw_dot = 0.5 * (-qx * p - qy * q - qz * r)
        qx_dot = 0.5 * (qw * p + qy * r - qz * q)
        qy_dot = 0.5 * (qw * q - qx * r + qz * p)
        qz_dot = 0.5 * (qw * r + qx * q - qy * p)
        attitude_dot = (qw_dot, qx_dot, qy_dot, qz_dot)

        # ==================================================================
        # 4. DINAMICA ROTAZIONALE (equazioni di Eulero)
        # ==================================================================
        # I·ω̇ + ω×(I·ω) = M, con I che include il prodotto Ixz.
        Mx, My, Mz = moments_body
        Ixx, Iyy, Izz, Ixz = self.Ixx, self.Iyy, self.Izz, self.Ixz

        # Termini noti delle equazioni accoppiate
        RHS1 = Mx + (Iyy - Izz) * q * r - Ixz * p * q
        RHS2 = Mz + (Ixx - Iyy) * p * q + Ixz * q * r

        # Determinante del sistema 2×2 per ṗ e ṙ
        Delta = Ixx * Izz - Ixz ** 2

        p_dot = (Izz * RHS1 - Ixz * RHS2) / Delta
        r_dot = (Ixx * RHS2 - Ixz * RHS1) / Delta
        q_dot = (My + Ixz * (p ** 2 - r ** 2)
                 + (Izz - Ixx) * p * r) / Iyy

        angular_velocity_dot = np.array([p_dot, q_dot, r_dot])

        return {
            'position_dot': position_dot,
            'velocity_dot': velocity_dot,
            'attitude_dot': attitude_dot,
            'angular_velocity_dot': angular_velocity_dot,
        }