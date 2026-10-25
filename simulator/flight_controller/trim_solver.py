"""
flight_controller/trim_solver.py

Trim solver: trova lo stato di equilibrio in volo livellato rettilineo.

T1. Il trim NON è un guess: è la soluzione di ∑F=0, ∑M=0 nel body frame
a rate nulli e accelerazione nulla. Risolvo con Newton multivariabile
sul residuo normalizzato, usando i componenti fisici (AeroForces +
Powerplant + gravità) — gli stessi del SimEngine, quindi coerente.

Variabili di trim (volo simmetrico, beta=0):
    x = [alpha, delta_e, throttle]
Equazioni di equilibrio (componenti nel piano di simmetria x-z):
    Fx_total = 0
    Fz_total = 0
    My_total = 0
La velocità V e la quota sono CONDIZIONI DI VOLO fissate dal chiamante
(gain scheduling: si risolve un trim per ogni V della griglia).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from dynamics.state import Quaternion
from dynamics.atmosphere import Atmosphere
from dynamics.aero.coefficients import AeroCoefficients
from dynamics.aero.forces import AeroForces
from dynamics.propulsion.engine import EngineModel
from dynamics.propulsion.propeller import PropellerModel
from dynamics.propulsion.powerplant import Powerplant

G = 9.80665

# Limiti fisici delle variabili di trim (rad / adimensionale)
ALPHA_MIN, ALPHA_MAX = -0.20, 0.40      # ~ -11° .. +23°
DE_MIN, DE_MAX = -0.60, 0.60            # ~ ±34° elevatore
THR_MIN, THR_MAX = 0.0, 1.0


@dataclass
class TrimResult:
    """Esito del trim: stato di equilibrio + diagnostiche."""
    alpha: float            # rad
    delta_e: float          # rad
    throttle: float         # [0,1]
    V: float                # m/s (condizione di volo)
    altitude: float         # m (condizione di volo)
    converged: bool
    residual_norm: float    # norma del residuo normalizzato
    iterations: int

    # Quantità derivate utili per l'estrazione pianta
    rho: float = 0.0        # kg/m³
    qbar: float = 0.0       # Pa
    CL: float = 0.0
    CD: float = 0.0
    Cm: float = 0.0

    # Diagnostica avanzata
    reason: str = ""
    residual_fx: float = 0.0
    residual_fz: float = 0.0
    residual_my: float = 0.0
    alpha_at_bound: bool = False
    delta_e_at_bound: bool = False
    throttle_at_bound: bool = False

    alpha_bound_side: str = ""       # "min" | "max" | ""
    delta_e_bound_side: str = ""     # "min" | "max" | ""
    throttle_bound_side: str = ""    # "min" | "max" | ""


class TrimSolver:
    """
    Risolve il trim di volo livellato per un dato (V, quota).

    Uso:
        solver = TrimSolver(aircraft_config)
        trim = solver.solve(V=42.0, altitude=0.0)
    """

    def __init__(self, aircraft_config, tol: float = 1e-4, max_iter: int = 80):
        self.cfg = aircraft_config
        self.mass = aircraft_config.mass
        self.tol = tol
        self.max_iter = max_iter

        # Componenti fisici (stessi del SimEngine)
        aero_coeff = AeroCoefficients(aircraft_config.aero_config)
        self.aero_forces = AeroForces(aero_coeff)
        engine = EngineModel(aircraft_config.engine_config)
        propeller = PropellerModel(aircraft_config.propeller_config)
        self.powerplant = Powerplant(engine, propeller)

        self.weight = self.mass * G
        # Scale per normalizzare il residuo (conditioning Newton)
        self.f_scale = self.weight
        self.m_scale = self.weight * aircraft_config.aero_config.c_ref

    # ------------------------------------------------------------------
    # Residuo di equilibrio
    # ------------------------------------------------------------------
    def _residual(self, x: np.ndarray, V: float, altitude: float) -> np.ndarray:
        alpha, delta_e, throttle = x

        # Stato di trim: volo simmetrico, rate nulli, pitch = alpha
        state = _make_trim_state(V, alpha, altitude)

        # Forze/momenti aerodinamici
        F_aero, M_aero = self.aero_forces.compute(
            state, {'delta_e': delta_e, 'delta_a': 0.0, 'delta_r': 0.0})

        # Propulsione
        F_prop, M_prop, _ = self.powerplant.compute(throttle, V, alpha)

        # Gravità nel body frame
        F_grav = self._gravity_body(alpha)

        F_total = F_aero + F_prop + F_grav
        M_total = M_aero + M_prop

        # Componenti nel piano di simmetria: Fx, Fz, My
        r = np.array([F_total[0], F_total[2], M_total[1]])
        r[0] /= self.f_scale
        r[1] /= self.f_scale
        r[2] /= self.m_scale
        return r

    def _gravity_body(self, alpha: float) -> np.ndarray:
        """Gravità NED [0,0,W] ruotata in body con pitch=alpha."""
        q = Quaternion.from_euler(0.0, alpha, 0.0)
        return q.conjugate().rotate_vector(np.array([0.0, 0.0, self.weight]))

    # ------------------------------------------------------------------
    # Newton multivariabile con differenze finite centrali
    # ------------------------------------------------------------------
    def solve(self, V: float, altitude: float,
              x0: Optional[np.ndarray] = None) -> TrimResult:
        """
        Risolve il trim per la condizione di volo (V, quota).

        Args:
            V: velocità di trim [m/s].
            altitude: quota [m].
            x0: guess iniziale [alpha, delta_e, throttle]. Se None, usa
                un guess fisico (alpha≈5°, de≈-0.05, thr≈0.5).
        """
        if x0 is None:
            x = np.array([0.087, -0.05, 0.5])
        else:
            x = np.array(x0, dtype=float)
        x = _clip_x(x)

        rho = Atmosphere.density(altitude)
        h = np.array([1e-3, 1e-3, 1e-3])  # passi per Jacobiana

        r = self._residual(x, V, altitude)
        converged = False
        it = 0
        reason = "max_iterations"

        for it in range(1, self.max_iter + 1):
            nr = float(np.linalg.norm(r))
            if nr < self.tol:
                converged = True
                reason = "converged"
                break

            # Jacobiana 3x3 a differenze finite centrali
            J = np.zeros((3, 3))
            for j in range(3):
                xp = x.copy(); xp[j] += h[j]
                xm = x.copy(); xm[j] -= h[j]
                J[:, j] = (
                    self._residual(_clip_x(xp), V, altitude)
                    - self._residual(_clip_x(xm), V, altitude)
                ) / (2 * h[j])

            # Passo Newton con fallback least-squares
            try:
                dx = np.linalg.solve(J, -r)
            except np.linalg.LinAlgError:
                dx = np.linalg.lstsq(J, -r, rcond=None)[0]

            dx_norm = float(np.linalg.norm(dx))
            if dx_norm < 1e-12:
                reason = "no_progress"
                break

            # Limita la norma del passo
            max_step = 0.3
            if dx_norm > max_step:
                dx = dx * (max_step / dx_norm)

            # Backtracking line search
            accepted = False
            current_nr = float(np.linalg.norm(r))
            for frac in (1.0, 0.5, 0.25, 0.1, 0.05, 0.01):
                x_try = _clip_x(x + frac * dx)
                r_try = self._residual(x_try, V, altitude)
                nr_try = float(np.linalg.norm(r_try))
                if nr_try < current_nr:
                    x = x_try
                    r = r_try
                    accepted = True
                    break

            if not accepted:
                reason = "stagnated"
                break

        final_nr = float(np.linalg.norm(r))
        if final_nr < self.tol:
            converged = True
            reason = "converged"

        # Diagnostica residui componenti
        r_final = self._residual(x, V, altitude)
        residual_fx = float(r_final[0])
        residual_fz = float(r_final[1])
        residual_my = float(r_final[2])

        # Diagnostica limiti attivi
        eps = 1e-6

        def _bound_side(value: float, lo: float, hi: float) -> str:
            if abs(value - lo) < eps:
                return "min"
            if abs(value - hi) < eps:
                return "max"
            return ""

        alpha_side = _bound_side(x[0], ALPHA_MIN, ALPHA_MAX)
        delta_e_side = _bound_side(x[1], DE_MIN, DE_MAX)
        throttle_side = _bound_side(x[2], THR_MIN, THR_MAX)

        alpha_at_bound = alpha_side != ""
        delta_e_at_bound = delta_e_side != ""
        throttle_at_bound = throttle_side != ""

        if not converged:
            if alpha_side:
                reason = f"alpha_{alpha_side}_bound"
            elif delta_e_side:
                reason = f"delta_e_{delta_e_side}_bound"
            elif throttle_side:
                reason = f"throttle_{throttle_side}_bound"

        # Quantità derivate
        state = _make_trim_state(V, x[0], altitude)
        coeffs = self.aero_forces.aero.compute(
            alpha=x[0], beta=0.0, delta_e=x[1],
            delta_a=0.0, delta_r=0.0, p_hat=0.0, q_hat=0.0, r_hat=0.0
        )
        qbar = 0.5 * rho * V * V

        return TrimResult(
            alpha=float(x[0]),
            delta_e=float(x[1]),
            throttle=float(x[2]),
            V=V,
            altitude=altitude,
            converged=converged,
            residual_norm=final_nr,
            iterations=it,
            rho=rho,
            qbar=qbar,
            CL=coeffs['CL'],
            CD=coeffs['CD'],
            Cm=coeffs['Cm'],
            reason=reason,
            residual_fx=residual_fx,
            residual_fz=residual_fz,
            residual_my=residual_my,
            alpha_at_bound=alpha_at_bound,
            delta_e_at_bound=delta_e_at_bound,
            throttle_at_bound=throttle_at_bound,
            alpha_bound_side=alpha_side,
            delta_e_bound_side=delta_e_side,
            throttle_bound_side=throttle_side,
        )

# ======================================================================
# HELPER
# ======================================================================

def _clip_x(x: np.ndarray) -> np.ndarray:
    x = np.array(x, dtype=float)
    x[0] = min(max(x[0], ALPHA_MIN), ALPHA_MAX)
    x[1] = min(max(x[1], DE_MIN), DE_MAX)
    x[2] = min(max(x[2], THR_MIN), THR_MAX)
    return x


def _make_trim_state(V: float, alpha: float, altitude: float):
    """Costruisce un AircraftState di trim (rate nulli, pitch=alpha)."""
    from dynamics.state import AircraftState
    s = AircraftState()
    s.position = np.array([0.0, 0.0, -altitude])
    s.velocity_body = np.array([V * np.cos(alpha), 0.0, V * np.sin(alpha)])
    s.attitude = Quaternion.from_euler(0.0, alpha, 0.0)
    s.angular_velocity = np.zeros(3)
    return s