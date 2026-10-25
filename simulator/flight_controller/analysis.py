"""
flight_controller/analysis.py

Analisi delle prestazioni dell'anello chiuso sulla LINEARIZZAZIONE.

T1. Dato un asse di pianta (K_dc, τ, M_q, M_ctrl) e un set di guadagni
PID, valuto le prestazioni SENZA simulare il velivolo completo:

- Margini di fase/guadagno: risposta in frequenza dell'anello aperto
  L(jω) = C(jω)·G(jω), con C(s) = Kp + Ki/s + Kd·s·Nd/(s+Nd).
- Metriche temporali (ωn, ζ, overshoot, settling, errore a regime,
  saturazione): integrando la linearizzazione col VERO PIDController
  (stesso controllore del SimEngine), quindi nessuna approssimazione
  sul controllore — solo la pianta è lineare.

IMPORTANTE: l'analisi lavora in COORDINATE DI CONTROLLO, cioè dopo
l'applicazione del segno di direzione del RateController.
Per questo si usa autorità efficace positiva:
    M_ctrl_eff = abs(M_ctrl)
    K_dc_eff   = abs(K_dc)

Questo garantisce coerenza con:
    delta = sign_axis * out_pid + trim
dove sign_axis = sign(M_ctrl).
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .pid import PIDController
from .plant import AxisPlant
from .performance_spec import Metrics


def derivative_filter_cutoff(alpha: float, dt: float) -> float:
    """
    Frequenza di taglio [rad/s] del filtro D, dalla alpha del PID discreto.

    Il PID usa un filtro esponenziale:
        y_k = alpha*x_k + (1-alpha)*y_{k-1}

    Equivalentemente, con discretizzazione backward Euler di:
        τ ydot + y = x
    si ha:
        alpha = dt / (τ + dt)
        τ = dt * (1-alpha) / alpha
        ω_c = 1/τ = alpha / (dt * (1-alpha))

    Args:
        alpha: coefficiente del filtro EMA [0,1].
        dt: passo temporale [s].

    Returns:
        Frequenza di taglio in rad/s.
        alpha=1 → nessun filtro → inf.
        alpha=0 → filtro infinito → 0.
    """
    if dt <= 1e-12:
        return math.inf
    if alpha >= 1.0 - 1e-9:
        return math.inf
    if alpha <= 1e-9:
        return 0.0
    return alpha / ((1.0 - alpha) * dt)


# ======================================================================
# MARGINI DI ANELLO APERTO
# ======================================================================

def open_loop_margins(plant: AxisPlant, kp: float, ki: float, kd: float,
                      nd: float,
                      w_min: float = 1e-2, w_max: float = 1e3,
                      n: int = 4000) -> tuple[Optional[float], Optional[float]]:
    """
    Calcola margine di fase [°] e margine di guadagno [dB] di L(jω)=C·G.

    La pianta è espressa in coordinate di controllo, quindi si usa
    K_dc_eff = abs(K_dc).
    """
    w = np.logspace(math.log10(w_min), math.log10(w_max), n)
    s = 1j * w

    # Controllore C(s)
    C = kp + ki / s
    if math.isinf(nd):
        C = C + kd * s
    else:
        C = C + kd * s * nd / (s + nd)

    # Pianta G(s) = K_dc_eff / (τ s + 1)
    K_eff = abs(plant.K_dc)

    if math.isinf(plant.tau):
        G = np.full_like(s, K_eff, dtype=complex)
    else:
        G = K_eff / (plant.tau * s + 1.0)

    L = C * G
    mag = np.abs(L)
    phase = np.degrees(np.unwrap(np.angle(L)))   # gradi, unwrapped

    pm = _phase_margin(w, mag, phase)
    gm = _gain_margin(w, mag, phase)
    return pm, gm


def _phase_margin(w, mag, phase) -> Optional[float]:
    """PM = 180 + ∠L(ω_gc), ω_gc dove |L|=1 (decrescente)."""
    for i in range(len(w) - 1):
        if mag[i] >= 1.0 > mag[i + 1]:
            f = (mag[i] - 1.0) / (mag[i] - mag[i + 1])
            ph = phase[i] + f * (phase[i + 1] - phase[i])
            return 180.0 + ph
    return None


def _gain_margin(w, mag, phase) -> Optional[float]:
    """
    GM_dB = -20log10|L(ω_pc)|, ω_pc dove ∠L=-180 (attraversamento decrescente).

    Se la fase non attraversa mai -180°:
      - resta sempre SOPRA -180° → il guadagno può crescere illimitatamente
        senza instabilità → GM = +inf (robustezza massima).
      - resta sempre SOTTO -180° → caso patologico (sistema già oltre la
        soglia), segnalato con -inf.
    """
    target = -180.0
    for i in range(len(w) - 1):
        if phase[i] >= target > phase[i + 1]:
            f = (phase[i] - target) / (phase[i] - phase[i + 1])
            m = mag[i] + f * (mag[i + 1] - mag[i])
            if m <= 0:
                return math.inf
            return -20.0 * math.log10(m)

    # Nessun attraversamento: discrimina i due casi
    if phase[-1] > target:
        return math.inf     # fase sempre sopra -180° → GM infinito
    return -math.inf        # fase sempre sotto -180° → già oltre soglia


# ======================================================================
# METRICHE TEMPORALI DALLA LINEARIZZAZIONE
# ======================================================================

def closed_loop_metrics(plant: AxisPlant, kp: float, ki: float, kd: float,
                        alpha_deriv: float, output_limit: float,
                        dt: float = 0.01, t_end: float = 6.0,
                        q_cmd_step: float = 0.1) -> Metrics:
    """
    Integra la linearizzazione col vero PIDController e ne estrae le
    metriche temporali. I margini sono aggiunti dall'anello aperto.

    La simulazione è in coordinate di controllo:
        u = PID output
        qdot = (M_q*q + |M_ctrl|*u) / I

    Questo è coerente col RateController, che applica:
        delta = sign(M_ctrl) * u + trim
    """
    nd = derivative_filter_cutoff(alpha_deriv, dt)
    pm, gm = open_loop_margins(plant, kp, ki, kd, nd)

    # --- Simulazione linearizzata col vero PID ---
    pid = PIDController(kp=kp, ki=ki, kd=kd,
                        output_limit=output_limit,
                        deriv_filter_alpha=alpha_deriv)

    M_ctrl_eff = abs(plant.M_ctrl)

    nsteps = int(t_end / dt)
    q = 0.0
    q_hist = np.empty(nsteps)
    sat_count = 0
    diverged = False

    for k in range(nsteps):
        u = pid.compute(q_cmd_step, q, dt)

        if abs(u) >= output_limit * 0.999:
            sat_count += 1

        # q̇ = (M_q·q + M_ctrl_eff·u) / I
        qdot = (plant.M_q * q + M_ctrl_eff * u) / plant.inertia
        q = q + dt * qdot

        if not math.isfinite(q) or abs(q) > 1e6:
            diverged = True
            q_hist[k:] = q if math.isfinite(q) else np.nan
            break

        q_hist[k] = q

    if diverged:
        return Metrics(diverged=True, phase_margin_deg=pm, gain_margin_db=gm)

    # --- Estrazione metriche dalla risposta a scalino ---
    final = float(np.mean(q_hist[int(0.9 * nsteps):]))
    ss_err_pct = abs(q_cmd_step - final) / abs(q_cmd_step) * 100.0

    peak = float(np.max(q_hist)) if q_cmd_step > 0 else float(np.min(q_hist))
    if abs(final) > 1e-9:
        overshoot_pct = max(0.0, (peak - final) / abs(final) * 100.0)
    else:
        overshoot_pct = 0.0

    threshold = 0.02 * abs(final)
    out_idx = np.where(np.abs(q_hist - final) > threshold)[0]
    settling_s = float((out_idx[-1] + 1) * dt) if len(out_idx) else dt

    # ζ da overshoot, ωn da settling
    os_frac = overshoot_pct / 100.0
    if 0.0 < os_frac < 1.0:
        ln_os = math.log(os_frac)
        zeta = -ln_os / math.sqrt(math.pi ** 2 + ln_os ** 2)
    elif os_frac <= 0.0:
        zeta = 1.0
    else:
        zeta = 0.0

    wn = 4.0 / (zeta * settling_s) if (zeta > 1e-6 and settling_s > 1e-9) else None

    saturation_pct = sat_count / nsteps * 100.0

    return Metrics(
        bandwidth_wn=wn,
        damping_zeta=zeta,
        overshoot_pct=overshoot_pct,
        settling_time_2pct_s=settling_s,
        ss_rate_tracking_err_pct=ss_err_pct,
        phase_margin_deg=pm,
        gain_margin_db=gm,
        saturation_frac_pct=saturation_pct,
        diverged=False,
    )