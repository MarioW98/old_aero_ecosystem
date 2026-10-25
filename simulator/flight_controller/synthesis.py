"""
flight_controller/synthesis.py

Sintesi automatica dei guadagni PID per il rate loop.

T2. Data una pianta (da T1) e una specifica di prestazione (da T0),
calcola Kp, Ki, Kd con pole placement su modello del primo ordine.

Il metodo:
1. Estrae (K_eff, τ) dalla pianta.
2. Imposta il polo derivativo come frazione di τ (kd_ratio).
3. Risolve il piazzamento dei poli per (ω_n, ζ) target.
4. Verifica con closed_loop_metrics + gate T0.
5. Se il gate fallisce (es. saturazione), riduce ω_n e riprova.

Questo garantisce:
- Calibrazione automatica per velivolo (pianta diversa → guadagni diversi).
- Calibrazione per requisiti (spec diversa → guadagni diversi).
- Nessun rischio di saturazione (iterazione conservativa).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .plant import AxisPlant
from .fc_config import AxisGains, RateConfig, ActuatorLimits
from .performance_spec import PerformanceSpec, Metrics, GateResult, evaluate
from .analysis import closed_loop_metrics


# ======================================================================
# RISULTATO DELLA SINTESI
# ======================================================================

@dataclass
class SynthesisResult:
    """Esito della sintesi automatica dei guadagni."""
    gains: AxisGains
    metrics: Metrics
    gate: GateResult
    omega_n_target: float       # ω_n richiesto dalla spec
    omega_n_used: float         # ω_n effettivamente usato (può essere ridotto)
    zeta_used: float
    kd_ratio: float
    iterations: int
    success: bool               # True se il gate passa
    message: str = ""


# ======================================================================
# PIAZZAMENTO DEI POLI — formule in forma chiusa
# ======================================================================

def _pole_placement_gains(
    K_eff: float,
    tau: float,
    omega_n: float,
    zeta: float,
    kd_ratio: float,
) -> tuple[float, float, float]:
    """
    Calcola (Kp, Ki, Kd) per la pianta G(s) = K_eff/(τs+1)
    con PID ideale C(s) = Kp + Ki/s + Kd·s.

    Il polinomio caratteristico dell'anello chiuso è:
        (τ + K_eff·Kd)·s² + (1 + K_eff·Kp)·s + K_eff·Ki

    Imponiamo i poli desiderati s² + 2ζω_n·s + ω_n².
    Il terzo grado di libertà è fissato da Kd = kd_ratio·τ/K_eff.

    Returns:
        (Kp, Ki, Kd). Tutti positivi se la sintesi è valida.

    Raises:
        ValueError: se i parametri portano a guadagni non fisici.
    """
    if K_eff <= 0:
        raise ValueError(f"K_eff deve essere positivo, trovato {K_eff}")
    if tau <= 0:
        raise ValueError(f"tau deve essere positivo, trovato {tau}")
    if omega_n <= 0:
        raise ValueError(f"omega_n deve essere positivo, trovato {omega_n}")
    if not (0 < zeta <= 2.0):
        raise ValueError(f"zeta deve essere in (0, 2], trovato {zeta}")

    # Guadagno derivativo: frazione della costante di tempo della pianta
    Kd = kd_ratio * tau / K_eff

    # Costante di tempo efficace con il termine derivativo
    tau_eff = tau * (1.0 + kd_ratio)

    # Guadagno integrale
    Ki = omega_n ** 2 * tau_eff / K_eff

    # Guadagno proporzionale
    Kp = (2.0 * zeta * omega_n * tau_eff - 1.0) / K_eff

    if Kp <= 0:
        raise ValueError(
            f"Kp negativo ({Kp:.4f}): la bandwidth ω_n={omega_n:.2f} rad/s "
            f"è troppo bassa per questa pianta (τ={tau:.3f}s). "
            f"Aumentare ω_n o ridurre ζ."
        )
    if Ki <= 0:
        raise ValueError(f"Ki non positivo ({Ki:.4f}): parametri non validi.")

    return Kp, Ki, Kd


# ======================================================================
# SINTESI PRINCIPALE
# ======================================================================

def synthesize_rate_gains(
    plant: AxisPlant,
    spec: PerformanceSpec,
    output_limit: float,
    dt: float = 0.02,
    alpha_deriv: float = 0.5,
    kd_ratio: float = 0.15,
    omega_n_target: Optional[float] = None,
    zeta_target: Optional[float] = None,
    q_cmd_step: float = 0.1,
    min_omega_n: float = 1.0,
    reduction_factor: float = 0.8,
    max_iterations: int = 15,
    omega_n_margin: float = 1.3,
    zeta_compensation: float = 0.15,
) -> SynthesisResult:
    """
    Sintetizza i guadagni PID per un asse del rate loop.

    Args:
        plant: AxisPlant estratta da T1.
        spec: PerformanceSpec con i target di prestazione.
        output_limit: limite attuatore [rad].
        dt: passo temporale del controllore [s].
        alpha_deriv: coefficiente filtro derivativo del PID.
        kd_ratio: frazione di τ per il tempo derivativo.
        omega_n_target: bandwidth target [rad/s]. Se None, usa
                        spec.bandwidth_wn_min.
        zeta_target: smorzamento target. Se None, usa il punto medio
                     della banda [zeta_min, zeta_max] della spec.
        q_cmd_step: ampiezza dello scalino di prova [rad/s].
        min_omega_n: bandwidth minima sotto cui non scendere.
        reduction_factor: fattore di riduzione di ωn ad ogni iterazione.
        max_iterations: numero massimo di tentativi.
        omega_n_margin: moltiplicatore iniziale di ωn per compensare
                        l'effetto degli zeri del PID sulla risposta.
        zeta_compensation: incremento di ζ per compensare l'overshoot
                           aggiuntivo introdotto dagli zeri del PID.

    Returns:
        SynthesisResult con guadagni, metriche, gate e diagnostica.
    """
    if not plant.open_loop_stable:
        return SynthesisResult(
            gains=AxisGains(kp=0, ki=0, kd=0),
            metrics=Metrics(diverged=True),
            gate=evaluate(spec, Metrics(diverged=True)),
            omega_n_target=0, omega_n_used=0, zeta_used=0,
            kd_ratio=kd_ratio, iterations=0, success=False,
            message=f"Pianta '{plant.axis}' instabile ad anello aperto: "
                    f"la sintesi pole placement richiede una pianta stabile. "
                    f"Serve un controllore stabilizzante dedicato.",
        )

    K_eff = abs(plant.K_dc)
    tau = plant.tau

    # Target di progetto
    if omega_n_target is None:
        omega_n_target = spec.bandwidth_wn_min
    if zeta_target is None:
        zeta_target = 0.5 * (spec.damping_zeta_min + spec.damping_zeta_max)

    # Margine iniziale su ωn: compensa l'effetto degli zeri del PID.
    # Gli zeri (da termini I e D) aumentano overshoot e settling oltre
    # quanto i soli poli prevedono. Partire più alti dà margine.
    omega_n = omega_n_target * omega_n_margin
    omega_n_max = omega_n_target * 2.5  # tetto superiore

    # Compensazione di ζ: gli zeri riducono lo smorzamento efficace.
    zeta_pole = min(zeta_target + zeta_compensation, 1.0)

    best_result: Optional[SynthesisResult] = None

    for iteration in range(1, max_iterations + 1):
        # --- 1. Sintesi guadagni ---
        try:
            Kp, Ki, Kd = _pole_placement_gains(
                K_eff, tau, omega_n, zeta_pole, kd_ratio)
        except ValueError:
            omega_n *= reduction_factor
            if omega_n < min_omega_n:
                break
            continue

        gains = AxisGains(kp=Kp, ki=Ki, kd=Kd)

        # --- 2. Verifica closed-loop sulla linearizzazione ---
        metrics = closed_loop_metrics(
            plant, Kp, Ki, Kd, alpha_deriv,
            output_limit=output_limit,
            dt=dt, t_end=6.0,
            q_cmd_step=q_cmd_step,
        )

        # --- 3. Gate ---
        gate = evaluate(spec, metrics)

        result = SynthesisResult(
            gains=gains,
            metrics=metrics,
            gate=gate,
            omega_n_target=omega_n_target,
            omega_n_used=omega_n,
            zeta_used=zeta_pole,
            kd_ratio=kd_ratio,
            iterations=iteration,
            success=gate.passed,
            message="",
        )

        if best_result is None or _is_better(result, best_result):
            best_result = result

        if gate.passed and gate.fully_evaluated:
            result.message = (
                f"Sintesi riuscita: ω_n={omega_n:.2f} rad/s, "
                f"ζ_pole={zeta_pole:.2f}, {iteration} iterazioni."
            )
            return result

        # --- 4. Iterazione BIDIREZIONALE basata sul modo di fallimento ---
        failed = {c.name for c in gate.checks
                  if c.status.value == "FAIL"}

        if metrics.diverged:
            # Divergenza: riduzione drastica + più smorzamento
            omega_n *= reduction_factor * reduction_factor
            zeta_pole = min(zeta_pole + 0.1, 1.0)

        elif "Saturazione attuatori" in failed:
            # Saturazione: ridurre ωn (meno sforzo di controllo)
            omega_n *= reduction_factor

        elif "Settling 2%" in failed:
            # Settling troppo lento: AUMENTARE ωn (risposta più rapida)
            omega_n *= (1.0 / reduction_factor)
            omega_n = min(omega_n, omega_n_max)

        elif "Overshoot" in failed:
            # Overshoot eccessivo: aumentare lo smorzamento
            zeta_pole = min(zeta_pole + 0.1, 1.0)

        elif "Smorzamento ζ" in failed:
            # ζ fuori banda: aggiusta nella direzione giusta
            if metrics.damping_zeta is not None:
                if metrics.damping_zeta < spec.damping_zeta_min:
                    zeta_pole = min(zeta_pole + 0.1, 1.0)
                elif metrics.damping_zeta > spec.damping_zeta_max:
                    zeta_pole = max(zeta_pole - 0.1, 0.3)
                else:
                    omega_n *= reduction_factor
            else:
                omega_n *= reduction_factor

        else:
            # Altro: riduzione conservativa
            omega_n *= reduction_factor

        if omega_n < min_omega_n:
            break

    # --- Esaurito il budget di iterazioni ---
    if best_result is not None:
        best_result.success = False
        best_result.message = (
            f"Sintesi non riuscita dopo {max_iterations} iterazioni. "
            f"Ultimo ω_n: {omega_n:.2f} rad/s, ζ_pole: {zeta_pole:.2f}. "
            f"La specifica potrebbe essere troppo stringente per questa "
            f"pianta, oppure serve un controllore diverso."
        )
        return best_result

    return SynthesisResult(
        gains=AxisGains(kp=0, ki=0, kd=0),
        metrics=Metrics(diverged=True),
        gate=evaluate(spec, Metrics(diverged=True)),
        omega_n_target=omega_n_target, omega_n_used=0, zeta_used=zeta_target,
        kd_ratio=kd_ratio, iterations=0, success=False,
        message="Sintesi fallita: nessun risultato prodotto.",
    )


def _is_better(a: SynthesisResult, b: SynthesisResult) -> bool:
    """Confronta due risultati: preferisce quello con gate passato,
    poi quello con meno check fallite, poi quello con ω_n più alto."""
    if a.success != b.success:
        return a.success
    a_fails = a.gate.failed_count
    b_fails = b.gate.failed_count
    if a_fails != b_fails:
        return a_fails < b_fails
    return a.omega_n_used > b.omega_n_used


# ======================================================================
# SINTESI COMPLETA PER TUTTI E TRE GLI ASSI
# ======================================================================

def synthesize_full_rate_config(
    plant_bundle,
    spec: PerformanceSpec,
    limits: ActuatorLimits,
    dt: float = 0.02,
    alpha_deriv: float = 0.5,
    kd_ratio: float = 0.15,
    q_cmd_step: float = 0.1,
) -> tuple[RateConfig, dict[str, SynthesisResult]]:
    """
    Sintetizza i guadagni per tutti e tre gli assi del rate loop
    e produce una RateConfig completa.

    Args:
        plant_bundle: RatePlantBundle da T1 (contiene roll, pitch, yaw).
        spec: PerformanceSpec comune ai tre assi.
        limits: ActuatorLimits del velivolo.
        dt, alpha_deriv, kd_ratio, q_cmd_step: parametri di sintesi.

    Returns:
        (RateConfig, dict[axis_name → SynthesisResult]).
    """
    results: dict[str, SynthesisResult] = {}

    axis_map = {
        "roll": (plant_bundle.roll, limits.max_delta_a, "trim_delta_a"),
        "pitch": (plant_bundle.pitch, limits.max_delta_e, "trim_delta_e"),
        "yaw": (plant_bundle.yaw, limits.max_delta_r, "trim_delta_r"),
    }

    gains = {}
    for axis_name, (plant, limit, trim_field) in axis_map.items():
        res = synthesize_rate_gains(
            plant, spec,
            output_limit=limit,
            dt=dt,
            alpha_deriv=alpha_deriv,
            kd_ratio=kd_ratio,
            q_cmd_step=q_cmd_step,
        )
        results[axis_name] = res
        gains[axis_name] = res.gains

    # Trim dalla pianta (T1 li ha già calcolati)
    trim = plant_bundle.trim

    config = RateConfig(
        roll=gains["roll"],
        pitch=gains["pitch"],
        yaw=gains["yaw"],
        limits=limits,
        trim_delta_a=0.0,
        trim_delta_e=trim.delta_e,
        trim_delta_r=0.0,
        sign_roll=plant_bundle.roll.ctrl_sign,
        sign_pitch=plant_bundle.pitch.ctrl_sign,
        sign_yaw=plant_bundle.yaw.ctrl_sign,
        deriv_filter_alpha=alpha_deriv,
    )

    return config, results


# ======================================================================
# CONVENIENZA: aggressività → PerformanceSpec
# ======================================================================

def make_spec_from_aggressiveness(
    aggressiveness: float,
    label: str = "auto",
) -> PerformanceSpec:
    """
    Crea una PerformanceSpec da un livello di aggressività [0, 1].

    Mappatura:
        0.0 → ω_n=2, ζ=0.9  (molto dolce)
        0.5 → ω_n=7, ζ=0.7  (bilanciato)
        1.0 → ω_n=15, ζ=0.5 (aggressivo)

    L'utente può usare questa funzione per una calibrazione rapida,
    oppure creare una PerformanceSpec esplicita per controllo fine.
    """
    aggressiveness = max(0.0, min(1.0, aggressiveness))

    # Interpolazione lineare
    if aggressiveness <= 0.5:
        t = aggressiveness / 0.5
        wn = 2.0 + t * (7.0 - 2.0)
        zeta = 0.9 + t * (0.7 - 0.9)
    else:
        t = (aggressiveness - 0.5) / 0.5
        wn = 7.0 + t * (15.0 - 7.0)
        zeta = 0.7 + t * (0.5 - 0.7)

    return PerformanceSpec(
        label=label,
        bandwidth_wn_min=wn,
        damping_zeta_min=max(0.3, zeta - 0.15),
        damping_zeta_max=min(1.2, zeta + 0.15),
        overshoot_max_pct=5.0 + 20.0 * aggressiveness,
        settling_time_2pct_max_s=max(0.3, 1.5 * (1.0 - aggressiveness)),
        ss_rate_tracking_err_max_pct=5.0,
        phase_margin_min_deg=max(30.0, 55.0 - 15.0 * aggressiveness),
        gain_margin_min_db=6.0,
        saturation_frac_max_pct=max(5.0, 25.0 - 15.0 * aggressiveness),
    )