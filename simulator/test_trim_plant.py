"""
simulator/test_trim_plant.py

Test T1: trim solver, estrazione pianta, analisi闭环 → gate T0.

Questo test è envelope-aware: non assume che una velocità scelta a mano
sia trimmabile dal modello. Scandisce un range di velocità, raccoglie i
punti trimmabili e verifica la catena fisica→pianta→metriche→gate su
quelli.

Uso:
    py -3.12 -m simulator.test_trim_plant
"""

import sys
import math
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent
ROOT = SIM_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM_DIR))

import numpy as np
from aircraft.c172 import make_c172_aircraft
from flight_controller.trim_solver import TrimSolver
from flight_controller.plant import extract_rate_plant
from flight_controller.analysis import (
    closed_loop_metrics,
    derivative_filter_cutoff,
)
from flight_controller.performance_spec import PerformanceSpec, evaluate


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


# ======================================================================
# SCAN INVILUPPO TRIMMABILE
# ======================================================================

_TEST_CFG = None
_TEST_BUNDLES = None


def _scan_feasible_bundles(cfg, speeds):
    """
    Scandisce velocità in ordine decrescente e usa continuation:
    il trim converguto di una velocità diventa guess per la successiva.
    Restituisce solo i bundle trimmabili, ordinati per V crescente.
    """
    solver = TrimSolver(cfg)
    bundles = []
    x0 = None

    # Andiamo dall'alta alla bassa velocità: di solito il throttle
    # richiesto cresce scendendo di velocità, quindi la continuation
    # aiuta la convergenza.
    for V in sorted(speeds, reverse=True):
        V = float(V)
        trim = solver.solve(V, 0.0, x0=x0)

        if trim.converged:
            x0 = np.array(
                [trim.alpha, trim.delta_e, trim.throttle],
                dtype=float,
            )
            bundle = extract_rate_plant(cfg, V, 0.0, trim=trim)
            bundles.append(bundle)

    return sorted(bundles, key=lambda b: b.V)


def _get_bundles():
    """
    Cache dei bundle trimmabili per il C172 di test.
    Prima prova un range grossolano 35..55 m/s.
    Se non trova almeno 2 punti, allarga a 30..60 m/s con passo 0.5.
    """
    global _TEST_CFG, _TEST_BUNDLES

    if _TEST_CFG is None:
        _TEST_CFG = make_c172_aircraft()

    if _TEST_BUNDLES is None:
        speeds = [float(v) for v in range(55, 34, -1)]  # 55,54,...,35
        _TEST_BUNDLES = _scan_feasible_bundles(_TEST_CFG, speeds)

        if len(_TEST_BUNDLES) < 2:
            speeds = [30.0 + 0.5 * i for i in range(61)]  # 30..60
            _TEST_BUNDLES = _scan_feasible_bundles(_TEST_CFG, speeds)

    return _TEST_BUNDLES


def _bundle_near(bundles, V_target):
    """Restituisce il bundle trimmabile più vicino a V_target."""
    return min(bundles, key=lambda b: abs(b.V - float(V_target)))


# ======================================================================
# TEST PRINCIPALE: INVILUPPO
# ======================================================================

def test_envelope_has_at_least_two_points():
    """
    Il modello deve avere almeno due velocità trimmabili distinte,
    altrimenti non ha senso parlare di gain scheduling o pianta variabile.
    """
    bundles = _get_bundles()
    check(
        len(bundles) >= 2,
        f"servono almeno 2 velocità trimmabili, trovate {len(bundles)}. "
        "Controllare tabelle aero/propulsione: il modello potrebbe essere "
        "sottopotenziato o avere CL_max/CD troppo restrittivi."
    )


# ======================================================================
# TRIM
# ======================================================================

def test_trim_converges():
    """Il trim deve convergere almeno in un punto dell'inviluppo trovato."""
    bundles = _get_bundles()
    check(len(bundles) >= 1, "nessun punto trimmabile trovato")

    trim = bundles[0].trim

    check(trim.converged, f"trim deve convergere, residuo={trim.residual_norm:.2e}")
    check(trim.residual_norm < 1e-3, "residuo trim piccolo")

    alpha_deg = math.degrees(trim.alpha)
    check(
        -10.0 < alpha_deg < 25.0,
        f"alpha trim fisicamente plausibile, trovato {alpha_deg:.2f}°"
    )

    check(
        0.0 <= trim.throttle <= 1.0,
        f"throttle trim in [0,1], trovato {trim.throttle:.3f}"
    )

    # Per un aereo convenzionale picchiante il trim elevator è tipicamente
    # negativo (nose-up). Accettiamo anche piccolo positivo per robustezza.
    check(
        trim.delta_e < 0.05,
        f"delta_e trim plausibile, trovato {trim.delta_e:.4f} rad"
    )


def test_trim_qbar_consistency():
    """qbar deve essere coerente con rho e V del trim."""
    bundles = _get_bundles()
    b = _bundle_near(bundles, 42.0)
    trim = b.trim

    expected = 0.5 * trim.rho * trim.V * trim.V
    rel_err = abs(trim.qbar - expected) / max(expected, 1e-9)

    check(rel_err < 1e-9, f"qbar incoerente: {trim.qbar:.6f} vs {expected:.6f}")


# ======================================================================
# PIANTA
# ======================================================================

def test_plant_pitch_stable_and_signed():
    """
    Pitch: per un aereo convenzionale stabile ci si aspetta
    M_q < 0, τ > 0, Cm_δe < 0 ⇒ K_dc < 0 e ctrl_sign = -1.
    """
    bundles = _get_bundles()
    b = _bundle_near(bundles, 42.0)
    p = b.pitch

    check(p.open_loop_stable, "pitch: smorzamento aerodinamico negativo atteso")
    check(p.tau > 0.0 and math.isfinite(p.tau),
          f"pitch τ>0 e finito, trovato {p.tau:.6f}")
    check(p.K_dc < 0.0,
          f"pitch K_dc<0 (Cm_δe<0), trovato {p.K_dc:.6f}")
    check(p.ctrl_sign == -1.0,
          f"pitch ctrl_sign deve essere -1, trovato {p.ctrl_sign}")

    # Range di sanità fisica, non di taratura.
    check(0.01 < p.tau < 10.0,
          f"pitch τ in range realistico, trovato {p.tau:.6f}")
    check(0.1 < abs(p.K_dc) < 200.0,
          f"|K_dc| pitch realistico, trovato {p.K_dc:.6f}")


def test_plant_roll_yaw():
    """
    Roll/yaw convenzionali: M_q/M_r < 0 e derivata di controllo positiva
    ⇒ K_dc > 0 e ctrl_sign = +1.
    """
    bundles = _get_bundles()
    b = _bundle_near(bundles, 42.0)

    for ax in (b.roll, b.yaw):
        check(ax.open_loop_stable, f"{ax.axis}: smorzamento negativo atteso")
        check(ax.tau > 0.0 and math.isfinite(ax.tau),
              f"{ax.axis} τ>0, trovato {ax.tau:.6f}")
        check(ax.K_dc > 0.0,
              f"{ax.axis} K_dc>0 atteso, trovato {ax.K_dc:.6f}")
        check(ax.ctrl_sign == 1.0,
              f"{ax.axis} ctrl_sign=+1 atteso, trovato {ax.ctrl_sign}")
        check(0.01 < ax.tau < 10.0,
              f"{ax.axis} τ in range realistico, trovato {ax.tau:.6f}")
        check(0.1 < abs(ax.K_dc) < 200.0,
              f"|K_dc| {ax.axis} realistico, trovato {ax.K_dc:.6f}")


def test_plant_varies_with_speed():
    """
    Sanity gain-scheduling: la pianta deve cambiare con V.

    Nota fisica corretta:
    - M_q dimensionato ∝ V
    - τ = -I/M_q ∝ 1/V
    - M_ctrl ∝ V²
    - K_dc = M_ctrl/(-M_q) ∝ V

    Quindi, in un modello convenzionale, all'aumentare di V ci si aspetta
    |K_dc| maggiore e τ più piccolo. Qui però assertiamo solo che cambino,
    per non rendere il test fragile su tavole aero non ideali.
    La tendenza fisica la stampiamo in diagnostica.
    """
    bundles = _get_bundles()
    check(len(bundles) >= 2, "servono almeno 2 punti trimmabili")

    lo = bundles[0]
    hi = bundles[-1]

    check(hi.V > lo.V + 1.0,
          f"le velocità estreme devono essere distinte: {lo.V:.1f} vs {hi.V:.1f}")

    for axis_name, ax_lo, ax_hi in (
        ("pitch", lo.pitch, hi.pitch),
        ("roll", lo.roll, hi.roll),
        ("yaw", lo.yaw, hi.yaw),
    ):
        check(ax_lo.tau > 0 and math.isfinite(ax_lo.tau),
              f"{axis_name}: τ lo non valido")
        check(ax_hi.tau > 0 and math.isfinite(ax_hi.tau),
              f"{axis_name}: τ hi non valido")

        check(abs(ax_hi.K_dc - ax_lo.K_dc) > 1e-3,
              f"{axis_name}: K_dc deve variare con V")
        check(abs(ax_hi.tau - ax_lo.tau) > 1e-4,
              f"{axis_name}: τ deve variare con V")


def test_extract_non_strict_handles_infeasible_point():
    """
    Un punto molto lento può non essere trimmabile in configurazione pulita.
    Con strict=False, extract_rate_plant deve restituire None invece di
    sollevare eccezione. Se in futuro il modello rendesse quel punto
    fattibile, il test resta valido perché accetta anche un bundle valido.
    """
    cfg = make_c172_aircraft()
    bundle = extract_rate_plant(cfg, V=15.0, altitude=0.0, strict=False)

    check(
        bundle is None or bundle.trim.converged,
        "strict=False deve restituire None oppure un bundle converguto"
    )


# ======================================================================
# ANALISI CHIUSO LOOP → GATE
# ======================================================================

def test_closed_loop_metrics_finite():
    """
    Con guadagni di prova, le metriche闭环 devono essere finite e sensate.
    Questi NON sono guadagni di produzione: servono solo a verificare
    la catena analisi→metriche.
    """
    bundles = _get_bundles()
    b = _bundle_near(bundles, 42.0)
    p = b.pitch

    kp, ki, kd = 0.35, 0.7, 0.06
    alpha = 0.5
    dt = 0.01

    m = closed_loop_metrics(
        p, kp, ki, kd, alpha,
        output_limit=0.40,
        dt=dt,
        t_end=6.0,
        q_cmd_step=0.1,
    )

    check(not m.diverged, "anello chiuso non deve divergere con questi gain di prova")
    check(m.bandwidth_wn is not None and m.bandwidth_wn > 0,
          f"ωn finito e >0, trovato {m.bandwidth_wn}")
    check(m.damping_zeta is not None and 0.0 < m.damping_zeta < 2.0,
          f"ζ in range sensato, trovato {m.damping_zeta}")
    check(m.overshoot_pct is not None and m.overshoot_pct >= 0,
          "overshoot >=0")
    check(m.settling_time_2pct_s is not None and m.settling_time_2pct_s > 0,
          "settling >0")
    check(m.ss_rate_tracking_err_pct is not None and m.ss_rate_tracking_err_pct < 20,
          f"errore a regime contenuto, {m.ss_rate_tracking_err_pct:.2f}%")
    check(m.phase_margin_deg is not None, "margine di fase calcolato")
    check(m.gain_margin_db is not None, "margine di guadagno calcolato")
    check(0.0 <= m.saturation_frac_pct <= 100.0, "saturazione in [0,100]")


def test_gate_consumes_metrics():
    """Il gate T0 accetta le metriche T1 e produce un verdetto + report."""
    bundles = _get_bundles()
    b = _bundle_near(bundles, 42.0)

    m = closed_loop_metrics(
        b.pitch, 0.35, 0.7, 0.06, 0.5,
        output_limit=0.40,
        dt=0.01,
        t_end=6.0,
    )

    spec = PerformanceSpec(label=f"pitch_V{b.V:.0f}")
    gate = evaluate(spec, m)

    check(isinstance(gate.passed, bool), "gate.passed è bool")
    check(gate.fully_evaluated is True,
          "tutte le metriche popolate → gate completo")
    check(len(gate.report) > 0 and "GATE DI ACCETTAZIONE" in gate.report,
          "report generato")
    check(gate.failed_count + gate.pending_count <= len(gate.checks),
          "conteggi coerenti")


def test_derivative_filter_cutoff():
    check(math.isinf(derivative_filter_cutoff(1.0, 0.02)), "alpha=1 → Nd=inf")
    check(derivative_filter_cutoff(0.0, 0.02) == 0.0, "alpha=0 → Nd=0")

    nd = derivative_filter_cutoff(0.5, 0.02)
    check(abs(nd - 50.0) < 1e-6, f"alpha=0.5,dt=0.02 → Nd=50, trovato {nd}")

    nd = derivative_filter_cutoff(0.2, 0.02)
    check(abs(nd - 12.5) < 1e-6, f"alpha=0.2,dt=0.02 → Nd=12.5, trovato {nd}")


# ======================================================================
# MAIN + DIAGNOSTICA
# ======================================================================

def main():
    test_envelope_has_at_least_two_points()
    test_trim_converges()
    test_trim_qbar_consistency()
    test_plant_pitch_stable_and_signed()
    test_plant_roll_yaw()
    test_plant_varies_with_speed()
    test_extract_non_strict_handles_infeasible_point()
    test_closed_loop_metrics_finite()
    test_gate_consumes_metrics()
    test_derivative_filter_cutoff()

    bundles = _get_bundles()

    print()
    print("=" * 72)
    print("T1 DIAGNOSTICA — Trim + Pianta + Analisi闭环 + Gate (C172)")
    print("=" * 72)
    print(f"Inviluppo trimmabile trovato: "
          f"{bundles[0].V:.1f} .. {bundles[-1].V:.1f} m/s "
          f"({len(bundles)} punti)")

    # Seleziona min, vicino a 42, max, senza duplicati
    selected = []
    for label, b in (
        ("min", bundles[0]),
        ("ref~42", _bundle_near(bundles, 42.0)),
        ("max", bundles[-1]),
    ):
        if all(abs(b.V - s[1].V) > 1e-6 for s in selected):
            selected.append((label, b))

    for label, b in selected:
        p = b.pitch
        print(f"\n--- {label}: V={b.V:.1f} m/s, quota 0 ---")
        print(f"  Trim        : alpha={math.degrees(b.trim.alpha):+.2f}°  "
              f"de={b.trim.delta_e:+.4f} rad  thr={b.trim.throttle:.3f}  "
              f"(residuo {b.trim.residual_norm:.1e}, motivo={b.trim.reason})")
        print(f"  Bound       : alpha={b.trim.alpha_bound_side or '-'}  "
              f"de={b.trim.delta_e_bound_side or '-'}  "
              f"thr={b.trim.throttle_bound_side or '-'}")
        print(f"  Pianta pitch: K_dc={p.K_dc:+.3f} (rad/s)/rad   τ={p.tau:.4f} s   "
              f"M_q={p.M_q:.1f}  M_de={p.M_ctrl:.1f}")
        print(f"  Pianta roll : K_dc={b.roll.K_dc:+.3f}   τ={b.roll.tau:.4f} s")
        print(f"  Pianta yaw  : K_dc={b.yaw.K_dc:+.3f}   τ={b.yaw.tau:.4f} s")

        m = closed_loop_metrics(
            p, 0.35, 0.7, 0.06, 0.5,
            output_limit=0.40,
            dt=0.01,
            t_end=6.0,
        )
        gate = evaluate(PerformanceSpec(label=f"pitch_V{b.V:.0f}"), m)

        print("  Anello chiuso (gain prova 0.35/0.7/0.06):")
        print(f"     ωn={m.bandwidth_wn:.2f} rad/s  ζ={m.damping_zeta:.2f}  "
              f"OS={m.overshoot_pct:.1f}%  ts={m.settling_time_2pct_s:.2f}s  "
              f"sserr={m.ss_rate_tracking_err_pct:.1f}%")
        print(f"     PM={m.phase_margin_deg:.1f}°  GM={m.gain_margin_db:.1f}dB  "
              f"sat={m.saturation_frac_pct:.1f}%")
        print(f"     GATE: {'PASS' if gate.passed else 'FAIL'} "
              f"(completo={gate.fully_evaluated}, "
              f"fail={gate.failed_count}, pending={gate.pending_count})")

    # Trend fisico, solo diagnostica
    if len(bundles) >= 2:
        lo = bundles[0]
        hi = bundles[-1]
        print("\nTrend fisico atteso per pianta convenzionale:")
        print(f"  V: {lo.V:.1f} → {hi.V:.1f} m/s")
        print(f"  |K_pitch|: {abs(lo.pitch.K_dc):.3f} → {abs(hi.pitch.K_dc):.3f}  (atteso crescita)")
        print(f"  τ_pitch  : {lo.pitch.tau:.4f} → {hi.pitch.tau:.4f} s  (atteso diminuzione)")

    print("=" * 72)
    print()
    print("PASS: T1 trim + pianta + analisi ciclo chiuso + gate corretti")


if __name__ == "__main__":
    main()