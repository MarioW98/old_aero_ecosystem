"""
simulator/dynamics/integrator.py

Integratore numerico Runge-Kutta del 4° ordine (RK4).

D1.4: Fondamenta — integratore RK4.

Integra le equazioni del moto 6-DoF nel tempo. Converte lo stato in
array piatto per la matematica RK4 e lo riconverte in AircraftState.

Nota: in questo step le forze/momenti sono assunti costanti durante il
passo. Quando le forze dipenderanno dallo stato (aerodinamica, D2),
l'integratore sarà esteso per ricalcolarle ad ogni sotto-passo.
"""

from __future__ import annotations

import numpy as np

from .state import Quaternion, AircraftState
from .rigid_body import RigidBodyDynamics


class RK4Integrator:
    """
    Integratore Runge-Kutta del 4° ordine per la dinamica 6-DoF.

    Uso:
        integrator = RK4Integrator(dynamics)
        new_state = integrator.step(state, forces, moments, dt)
    """

    # Dimensione dello stato: 3(pos) + 3(vel) + 4(quat) + 3(ang_vel) = 13
    STATE_SIZE = 13

    def __init__(self, dynamics: RigidBodyDynamics):
        """
        Args:
            dynamics: oggetto RigidBodyDynamics con massa e inerzia.
        """
        self.dynamics = dynamics

    # ------------------------------------------------------------------
    # Passo di integrazione
    # ------------------------------------------------------------------
    def step(self, state: AircraftState,
             forces_body: np.ndarray,
             moments_body: np.ndarray,
             dt: float) -> AircraftState:
        """
        Avanza lo stato di un passo temporale dt.

        Le forze e i momenti sono assunti costanti durante il passo.

        Args:
            state: stato corrente.
            forces_body: forze totali nel body frame [N].
            moments_body: momenti totali nel body frame [N·m].
            dt: passo temporale [s].

        Returns:
            Nuovo stato dopo dt.
        """
        y = self._state_to_array(state)

        # I quattro stadi di RK4
        k1 = self._derivatives(y, forces_body, moments_body)
        k2 = self._derivatives(y + 0.5 * dt * k1, forces_body, moments_body)
        k3 = self._derivatives(y + 0.5 * dt * k2, forces_body, moments_body)
        k4 = self._derivatives(y + dt * k3, forces_body, moments_body)

        # Combinazione pesata
        y_new = y + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        # Riconversione in stato strutturato
        new_state = self._array_to_state(y_new)

        # Normalizzazione del quaternione (anti-drift numerico)
        new_state.attitude = new_state.attitude.normalize()

        # Avanzamento del tempo
        new_state.time = state.time + dt

        return new_state

    # ------------------------------------------------------------------
    # Conversione stato <-> array piatto
    # ------------------------------------------------------------------
    def _state_to_array(self, state: AircraftState) -> np.ndarray:
        """Converte AircraftState in array piatto di 13 elementi."""
        return np.concatenate([
            state.position,                # [0:3]   NED
            state.velocity_body,           # [3:6]   u, v, w
            np.array([state.attitude.w, state.attitude.x,
                      state.attitude.y, state.attitude.z]),  # [6:10]
            state.angular_velocity,        # [10:13] p, q, r
        ])

    def _array_to_state(self, y: np.ndarray) -> AircraftState:
        """Converte array piatto di 13 elementi in AircraftState."""
        state = AircraftState()
        state.position = y[0:3].copy()
        state.velocity_body = y[3:6].copy()
        state.attitude = Quaternion(float(y[6]), float(y[7]),
                                    float(y[8]), float(y[9]))
        state.angular_velocity = y[10:13].copy()
        return state

    # ------------------------------------------------------------------
    # Calcolo derivate
    # ------------------------------------------------------------------
    def _derivatives(self, y: np.ndarray,
                     forces_body: np.ndarray,
                     moments_body: np.ndarray) -> np.ndarray:
        """Calcola il vettore delle derivate dall'array di stato."""
        temp_state = self._array_to_state(y)
        derivs = self.dynamics.compute_derivatives(
            temp_state, forces_body, moments_body)

        return np.concatenate([
            derivs['position_dot'],
            derivs['velocity_dot'],
            np.array(derivs['attitude_dot']),
            derivs['angular_velocity_dot'],
        ])