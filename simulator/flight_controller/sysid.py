"""
flight_controller/sysid.py

System Identification: identifica la pianta del rate loop dai dati
del simulatore non lineare.

T4. Il modello lineare di T1 è un'approssimazione. T4 verifica che
corrisponda al comportamento reale del simulatore, eccitando il sistema
con segnali noti (step o PRBS) e fittando una pianta del primo ordine
dai dati input/output.

Metodo: regressione lineare sull'equazione differenziale
    τ·ẏ + y = K·u  →  ẏ = a·u − b·y   (a=K/τ, b=1/τ)
che è un problema ai minimi quadrati.

Uso:
    result = sysid_rate_loop(aircraft_config, rate_config, trim,
                              axis="pitch", excitation="step")
    print(f"K: analitico={result.K_analytical:.3f}, "
          f"identificato={result.K_identified:.3f}, "
          f"errore={result.K_error_pct:.1f}%")
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from .fc_config import RateConfig
from .plant import AxisPlant


# ======================================================================
# RISULTATO IDENTIFICAZIONE
# ======================================================================

@dataclass
class SysIdResult:
    """Risultato dell'identificazione di un asse."""
    axis: str
    excitation: str             # "step" | "prbs"

    # Pianta identificata
    K_identified: float
    tau_identified: float

    # Pianta analitica (da T1)
    K_analytical: float
    tau_analytical: float

    # Errori relativi
    K_error_pct: float
    tau_error_pct: float

    # Qualità del fit
    R_squared: float

    # Diagnostica
    n_samples: int
    diverged: bool = False
    message: str = ""

    @property
    def valid(self) -> bool:
        """L'identificazione è affidabile."""
        return (not self.diverged
                and self.R_squared > 0.8
                and self.tau_identified > 0)


# ======================================================================
# IDENTIFICAZIONE PIANTA DEL PRIMO ORDINE
# ======================================================================

def identify_first_order(
    t: np.ndarray,
    y: np.ndarray,
    u: np.ndarray,
) -> Tuple[float, float, float]:
    """
    Identifica G(s) = K/(τs+1) dai dati input/output.

    Usa la regressione lineare sull'equazione differenziale:
        ẏ = (K/τ)·u − (1/τ)·y = a·u − b·y

    Args:
        t: tempo [s], array 1D.
        y: output (rate) [rad/s], array 1D.
        u: input (deflessione superficie incrementale) [rad], array 1D.

    Returns:
        (K, tau, R_squared). K e tau sono i parametri della pianta.
        R_squared è la qualità del fit [0, 1].
    """
    if len(t) < 10:
        return 0.0, 0.0, 0.0

    # Derivata numerica (differenze centrali)
    dydt = np.gradient(y, t)

    # Scarta i primi e ultimi punti (derivate inaccurate ai bordi)
    margin = max(2, len(t) // 20)
    dydt = dydt[margin:-margin]
    y_fit = y[margin:-margin]
    u_fit = u[margin:-margin]

    # Regressione lineare: dydt = a*u - b*y
    A = np.column_stack([u_fit, -y_fit])

    try:
        params, _, rank, _ = np.linalg.lstsq(A, dydt, rcond=None)
    except np.linalg.LinAlgError:
        return 0.0, 0.0, 0.0

    if rank < 2:
        return 0.0, 0.0, 0.0

    a, b = params

    if abs(b) < 1e-12:
        return 0.0, 0.0, 0.0

    tau = 1.0 / b
    K = a * tau

    # R²
    y_pred = A @ params
    ss_res = float(np.sum((dydt - y_pred) ** 2))
    ss_tot = float(np.sum((dydt - np.mean(dydt)) ** 2))
    R2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0

    return float(K), float(tau), float(R2)


# ======================================================================
# SEGNALI DI ECCITAZIONE
# ======================================================================

def make_step_signal(
    n_steps: int,
    dt: float,
    amplitude: float,
    t_start: float = 0.5,
) -> np.ndarray:
    """
    Genera un segnale a scalino.

    Args:
        n_steps: numero di campioni.
        dt: passo temporale [s].
        amplitude: ampiezza dello scalino.
        t_start: istante di applicazione [s].

    Returns:
        Array di valori del comando.
    """
    t = np.arange(n_steps) * dt
    signal = np.zeros(n_steps)
    signal[t >= t_start] = amplitude
    return signal


def make_prbs_signal(
    n_steps: int,
    dt: float,
    amplitude: float,
    hold_time: float = 0.1,
    seed: int = 42,
) -> np.ndarray:
    """
    Genera un segnale PRBS (Pseudo-Random Binary Sequence).

    Il segnale cambia valore ogni hold_time secondi, alternando
    tra +amplitude e -amplitude. È più informativo dello scalino
    per l'identificazione perché eccita un range più ampio di
    frequenze.

    Args:
        n_steps: numero di campioni.
        dt: passo temporale [s].
        amplitude: ampiezza del segnale.
        hold_time: durata di ogni livello [s].
        seed: seme per riproducibilità.

    Returns:
        Array di valori del comando.
    """
    rng = np.random.RandomState(seed)
    hold_steps = max(1, int(hold_time / dt))
    n_switches = n_steps // hold_steps + 1

    levels = rng.choice([-1.0, 1.0], size=n_switches)
    signal = np.repeat(levels, hold_steps)[:n_steps]

    return amplitude * signal


# ======================================================================
# SIMULAZIONE CON ECCITAZIONE
# ======================================================================

def run_rate_excitation(
    aircraft_config,
    rate_config: RateConfig,
    trim_alpha: float,
    trim_delta_e: float,
    trim_throttle: float,
    V: float,
    altitude: float,
    axis: str,
    excitation_signal: np.ndarray,
    dt: float = 0.02,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
    """
    Esegue il simulatore con il RateController e un segnale di
    eccitazione sovrapposto al comando di rate.

    L'anello aperto è necessario per identificare la pianta fisica
    pura. Il RateController (PID) distorce il segnale e darebbe
    un'identificazione inaccurata.

    Args:
        aircraft_config: AircraftConfig del velivolo.
        rate_config: RateConfig con i guadagni sintetizzati.
        trim_alpha, trim_delta_e, trim_throttle: valori di trim.
        V, altitude: condizione di volo.
        axis: asse da eccitare ("roll", "pitch", "yaw").
        excitation_signal: segnale di eccitazione (rate cmd aggiuntivo).
        dt: passo temporale [s].

    Returns:
        (t, rate, surface): tempo, rate misurato, deflessione
        superficie incrementale (senza trim).
        Il quarto elemento è un bool: True se divergente.
    """
    from dynamics.state import Quaternion, AircraftState
    from sim_engine import SimEngine
    from .rate_controller import RateController

    # Stato iniziale al trim
    state = AircraftState()
    alpha = trim_alpha
    state.position = np.array([0.0, 0.0, -altitude])
    state.velocity_body = np.array(
        [V * math.cos(alpha), 0.0, V * math.sin(alpha)])
    state.attitude = Quaternion.from_euler(0.0, alpha, 0.0)
    state.angular_velocity = np.zeros(3)

    sim = SimEngine(aircraft_config)
    sim.reset(state)

    # Mappatura asse → indice e superficie
    axis_idx = {"roll": 0, "pitch": 1, "yaw": 2}[axis]
    surface_key = {"roll": "delta_a", "pitch": "delta_e", "yaw": "delta_r"}[axis]

    # Trim per ogni superficie (dalla RateConfig)
    trim_surfaces = {
        'delta_a': rate_config.trim_delta_a,
        'delta_e': rate_config.trim_delta_e,
        'delta_r': rate_config.trim_delta_r,
    }

    n_steps = len(excitation_signal)
    t_hist = np.empty(n_steps)
    rate_hist = np.empty(n_steps)
    surf_hist = np.empty(n_steps)
    diverged = False

    for k in range(n_steps):
        # ANELLO APERTO: superficie = trim + eccitazione.
        # Il sysid identifica la pianta FISICA (superficie → rate),
        # non il controllore. Usare il PID distorcerebbe il segnale
        # e darebbe R² basso.
        surfaces = dict(trim_surfaces)
        surfaces[surface_key] += float(excitation_signal[k])

        # Controlli per il simulatore
        controls = {
            'throttle': trim_throttle,
            'delta_e': surfaces['delta_e'],
            'delta_a': surfaces['delta_a'],
            'delta_r': surfaces['delta_r'],
        }

        sim.step(dt, controls)

        # Registra dati
        t_hist[k] = sim.state.time
        rate_hist[k] = float(sim.state.angular_velocity[axis_idx])
        # Deflessione incrementale (senza trim)
        trim_val = {"delta_a": rate_config.trim_delta_a,
                    "delta_e": rate_config.trim_delta_e,
                    "delta_r": rate_config.trim_delta_r}[surface_key]
        surf_hist[k] = surfaces[surface_key] - trim_val

        # Check divergenza
        if (not math.isfinite(sim.state.angular_velocity[axis_idx])
                or abs(sim.state.angular_velocity[axis_idx]) > 100.0):
            diverged = True
            t_hist = t_hist[:k + 1]
            rate_hist = rate_hist[:k + 1]
            surf_hist = surf_hist[:k + 1]
            break

    return t_hist, rate_hist, surf_hist, diverged


# ======================================================================
# PIPELINE COMPLETA DI IDENTIFICAZIONE
# ======================================================================

def sysid_rate_loop(
    aircraft_config,
    rate_config: RateConfig,
    plant: AxisPlant,
    trim_alpha: float,
    trim_delta_e: float,
    trim_throttle: float,
    V: float,
    altitude: float,
    axis: str = "pitch",
    excitation: str = "step",
    amplitude: float = 0.05,
    duration: float = 4.0,
    dt: float = 0.02,
) -> SysIdResult:
    """
    Pipeline completa di system identification per un asse.

    1. Genera il segnale di eccitazione
    2. Esegue il simulatore con il RateController
    3. Identifica la pianta dai dati
    4. Confronta con la pianta analitica di T1

    Args:
        aircraft_config: AircraftConfig del velivolo.
        rate_config: RateConfig con guadagni sintetizzati (da T2/T3).
        plant: AxisPlant analitica (da T1) per il confronto.
        trim_alpha, trim_delta_e, trim_throttle: valori di trim.
        V, altitude: condizione di volo.
        axis: asse da identificare.
        excitation: "step" o "prbs".
        amplitude: ampiezza del segnale di eccitazione.
        duration: durata della simulazione [s].
        dt: passo temporale [s].

    Returns:
        SysIdResult con pianta identificata, analitica, e diagnostica.
    """
    n_steps = int(duration / dt)

    # Genera segnale di eccitazione
    # Genera segnale di eccitazione
    if excitation == "step":
        signal = make_step_signal(n_steps, dt, amplitude)
    elif excitation == "prbs":
        # hold_time proporzionale al tau della pianta.
        # Un hold_time troppo corto rispetto a tau dà risultati distorti:
        # il sistema non riesce a seguire il PRBS e l'identificazione
        # sottostima il guadagno e la costante di tempo.
        # Regola empirica: hold_time ≈ 0.3·tau eccita correttamente
        # la dinamica senza essere troppo lento.
        hold_time = max(0.1, 0.3 * abs(plant.tau))
        signal = make_prbs_signal(
            n_steps, dt, amplitude, hold_time=hold_time)
    else:
        raise ValueError(f"Eccitazione sconosciuta: {excitation}")

    # Esegue la simulazione
    t, rate, surf, diverged = run_rate_excitation(
        aircraft_config, rate_config,
        trim_alpha, trim_delta_e, trim_throttle,
        V, altitude, axis, signal, dt,
    )

    if diverged or len(t) < 20:
        return SysIdResult(
            axis=axis, excitation=excitation,
            K_identified=0, tau_identified=0,
            K_analytical=plant.K_dc, tau_analytical=plant.tau,
            K_error_pct=100.0, tau_error_pct=100.0,
            R_squared=0.0, n_samples=len(t),
            diverged=True,
            message="Simulazione divergente o troppo corta",
        )

    # Identifica la pianta
    K_id, tau_id, R2 = identify_first_order(t, rate, surf)

    # Confronta con la pianta analitica.
    # Il segno fisico (es. K_dc < 0 per il pitch) è gestito dal
    # RateController con sign_pitch/sign_roll/sign_yaw. Qui confrontiamo
    # solo le MAGNITUDINI: il segno dell'identificazione deve coincidere
    # con il segno fisico della pianta (entrambi negativi per il pitch).
    K_an = plant.K_dc   # segno reale, non abs
    tau_an = plant.tau

    # Errore su magnitudine (il segno è coerente per costruzione)
    K_err = abs(abs(K_id) - abs(K_an)) / max(abs(K_an), 1e-9) * 100.0
    tau_err = abs(tau_id - tau_an) / max(abs(tau_an), 1e-9) * 100.0

    return SysIdResult(
        axis=axis,
        excitation=excitation,
        K_identified=K_id,
        tau_identified=tau_id,
        K_analytical=K_an,
        tau_analytical=tau_an,
        K_error_pct=K_err,
        tau_error_pct=tau_err,
        R_squared=R2,
        n_samples=len(t),
        diverged=False,
        message="",
    )