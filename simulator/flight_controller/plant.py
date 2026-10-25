"""
flight_controller/plant.py

Estrazione della pianta del rate loop dalla fisica del velivolo.

T1. Dalle derivate aerodinamiche (ottenute perturbando AeroCoefficients)
+ inerzie + geometria + condizioni di trim, ricavo per ogni asse rate:

    I·q̇ = M_q·q + M_δ·δ        ⇒   G(s) = K_dc / (τ·s + 1)

    K_dc = M_δ / (-M_q)     [(rad/s)/rad]   gain a regime
    τ    = -I / M_q         [s]             costante di tempo (M_q<0 ⇒ τ>0)

Il segno di direzione per il controllore esce dalla fisica:
    ctrl_sign = sign(M_δ)
(per pitch Cm_δe<0 ⇒ ctrl_sign=-1, la convenzione sign_pitch).

Nessun numero hardcoded: tutto derivato dalle tabelle aero del velivolo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from dynamics.aero.coefficients import AeroCoefficients
from .trim_solver import TrimSolver, TrimResult


@dataclass
class AxisPlant:
    """Pianta del rate loop per un singolo asse."""
    axis: str            # "roll" | "pitch" | "yaw"
    K_dc: float          # [(rad/s)/rad]  gain a regime
    tau: float           # [s]            costante di tempo
    M_q: float           # [N·m·s/rad]    derivata di smorzamento (feedback)
    M_ctrl: float        # [N·m/rad]      derivata di controllo
    inertia: float       # [kg·m²]
    ctrl_sign: float     # sign(M_ctrl), per il controllore
    open_loop_stable: bool   # True se M_q < 0 (rate decade senza feedback)


@dataclass
class RatePlantBundle:
    """Piante rate dei 3 assi + trim di riferimento."""
    roll: AxisPlant
    pitch: AxisPlant
    yaw: AxisPlant
    trim: TrimResult
    V: float
    altitude: float


# Passo di perturbazione per le derivate (adimensionale su q_hat / rad su δ)
_H_QHAT = 1e-3
_H_DELTA = 1e-3


def extract_rate_plant(
    aircraft_config,
    V: float,
    altitude: float,
    trim: TrimResult | None = None,
    strict: bool = True,
) -> Optional[RatePlantBundle]:
    """
    Estrae le piante rate per (V, quota), risolvendo il trim se necessario.

    Args:
        aircraft_config: AircraftConfig del velivolo.
        V: velocità di trim [m/s].
        altitude: quota [m].
        trim: TrimResult già calcolato. Se None, viene risolto qui.
        strict: se True, solleva eccezione se il trim non converge.
                se False, restituisce None per punti non trimmabili.

    Returns:
        RatePlantBundle se il trim converge, altrimenti None se strict=False.
    """
    if trim is None:
        trim = TrimSolver(aircraft_config).solve(V, altitude)

    if not trim.converged:
        msg = (
            f"Trim non riuscito a V={V:.1f} m/s, quota={altitude:.0f} m: "
            f"residuo={trim.residual_norm:.3e}, motivo={trim.reason}, "
            f"componenti=(Fx={trim.residual_fx:.3e}, "
            f"Fz={trim.residual_fz:.3e}, My={trim.residual_my:.3e}), "
            f"bound=(alpha={trim.alpha_at_bound}/{trim.alpha_bound_side}, "
            f"delta_e={trim.delta_e_at_bound}/{trim.delta_e_bound_side}, "
            f"throttle={trim.throttle_at_bound}/{trim.throttle_bound_side})"
        )
        if strict:
            raise RuntimeError(msg)
        return None

    aero = AeroCoefficients(aircraft_config.aero_config)
    cfg = aircraft_config.aero_config
    S, b, c = cfg.S_ref, cfg.b_ref, cfg.c_ref
    I = aircraft_config.inertia
    qbar, rho = trim.qbar, trim.rho

    # ------------------------------------------------------------------
    # DERIVATE PER ASSE (perturbazioni centrali sui coefficienti)
    # ------------------------------------------------------------------
    # Pitch: Iyy·q̇ = M_q·q + M_δe·δe
    Cm_de = _dCm_ddelta(aero, trim, 'delta_e')
    Cm_q = _dCm_dqhat(aero, trim)
    M_de = Cm_de * qbar * S * c
    M_q = Cm_q * qbar * S * c * c / (2.0 * V)
    pitch = _make_axis('pitch', M_q, M_de, I['Iyy'])

    # Roll: Ixx·ṗ = L_p·p + L_δa·δa
    Cl_da = _dCl_ddelta(aero, trim, 'delta_a')
    Cl_p = _dCl_phhat(aero, trim)
    L_da = Cl_da * qbar * S * b
    L_p = Cl_p * qbar * S * b * b / (2.0 * V)
    roll = _make_axis('roll', L_p, L_da, I['Ixx'])

    # Yaw: Izz·ṙ = N_r·r + N_δr·δr
    Cn_dr = _dCn_ddelta(aero, trim, 'delta_r')
    Cn_r = _dCn_rhat(aero, trim)
    N_dr = Cn_dr * qbar * S * b
    N_r = Cn_r * qbar * S * b * b / (2.0 * V)
    yaw = _make_axis('yaw', N_r, N_dr, I['Izz'])

    return RatePlantBundle(roll=roll, pitch=pitch, yaw=yaw,
                           trim=trim, V=V, altitude=altitude)


def _make_axis(name: str, M_q: float, M_ctrl: float, inertia: float) -> AxisPlant:
    """Costruisce AxisPlant da derivate fisiche. Gestisce M_q>=0 (instabile)."""
    open_loop_stable = M_q < 0.0
    if abs(M_q) < 1e-9:
        # Smorzamento nullo: pianta integratore puro (τ→∞)
        K_dc = np.inf if M_ctrl > 0 else -np.inf
        tau = np.inf
    else:
        K_dc = M_ctrl / (-M_q)
        tau = -inertia / M_q
    ctrl_sign = 1.0 if M_ctrl >= 0 else -1.0
    return AxisPlant(axis=name, K_dc=float(K_dc), tau=float(tau),
                     M_q=float(M_q), M_ctrl=float(M_ctrl),
                     inertia=float(inertia), ctrl_sign=ctrl_sign,
                     open_loop_stable=open_loop_stable)


# ======================================================================
# DERIVATE NUMERICHE (perturbazioni centrali su AeroCoefficients)
# ======================================================================

def _base_kwargs(trim: TrimResult) -> dict:
    return dict(alpha=trim.alpha, beta=0.0,
                delta_e=trim.delta_e, delta_a=0.0, delta_r=0.0,
                p_hat=0.0, q_hat=0.0, r_hat=0.0)


def _dCm_ddelta(aero, trim, which: str) -> float:
    kw = _base_kwargs(trim)
    kp = dict(kw); kp[which] += _H_DELTA
    km = dict(kw); km[which] -= _H_DELTA
    return (aero.compute(**kp)['Cm'] - aero.compute(**km)['Cm']) / (2 * _H_DELTA)


def _dCl_ddelta(aero, trim, which: str) -> float:
    kw = _base_kwargs(trim)
    kp = dict(kw); kp[which] += _H_DELTA
    km = dict(kw); km[which] -= _H_DELTA
    return (aero.compute(**kp)['Cl'] - aero.compute(**km)['Cl']) / (2 * _H_DELTA)


def _dCn_ddelta(aero, trim, which: str) -> float:
    kw = _base_kwargs(trim)
    kp = dict(kw); kp[which] += _H_DELTA
    km = dict(kw); km[which] -= _H_DELTA
    return (aero.compute(**kp)['Cn'] - aero.compute(**km)['Cn']) / (2 * _H_DELTA)


def _dCm_dqhat(aero, trim) -> float:
    kw = _base_kwargs(trim)
    kp = dict(kw); kp['q_hat'] += _H_QHAT
    km = dict(kw); km['q_hat'] -= _H_QHAT
    return (aero.compute(**kp)['Cm'] - aero.compute(**km)['Cm']) / (2 * _H_QHAT)


def _dCl_phhat(aero, trim) -> float:
    kw = _base_kwargs(trim)
    kp = dict(kw); kp['p_hat'] += _H_QHAT
    km = dict(kw); km['p_hat'] -= _H_QHAT
    return (aero.compute(**kp)['Cl'] - aero.compute(**km)['Cl']) / (2 * _H_QHAT)


def _dCn_rhat(aero, trim) -> float:
    kw = _base_kwargs(trim)
    kp = dict(kw); kp['r_hat'] += _H_QHAT
    km = dict(kw); km['r_hat'] -= _H_QHAT
    return (aero.compute(**kp)['Cn'] - aero.compute(**km)['Cn']) / (2 * _H_QHAT)