"""
simulator/test_synthesis.py

Test T2: sintesi automatica dei guadagni PID.
Verifica che la catena completa T1→T2→gate funzioni:
  1. I guadagni sono calcolati dalla fisica (non hardcoded).
  2. Il gate passa con la spec di default.
  3. La saturazione è sotto controllo.
  4. Specifiche diverse producono guadagni diversi.
  5. L'aggressività mappa correttamente a specifiche.

Uso:
    py -3.12 -m simulator.test_synthesis
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
from flight_controller.fc_config import ActuatorLimits
from flight_controller.performance_spec import PerformanceSpec
from flight_controller.synthesis import (
    synthesize_rate_gains,
    synthesize_full_rate_config,
    make_spec_from_aggressiveness,
    SynthesisResult,
)


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


# ======================================================================
# FIXTURE: pianta del C172
# ======================================================================

_CFG = None
_BUNDLE = None


def _get_bundle():
    global _CFG, _BUNDLE
    if _BUNDLE is None:
        _CFG = make_c172_aircraft()
        # Usa una velocità nel range trimmabile
        solver = TrimSolver(_CFG)
        trim = None
        for V in (45.0, 42.0, 40.0, 38.0, 50.0):
            trim = solver.solve(V, 0.0)
            if trim.converged:
                break
        if trim is None or not trim.converged:
            print("FAIL: nessun punto di trim trovato per il test")
            sys.exit(1)
        _BUNDLE = extract_rate_plant(_CFG, trim.V, 0.0, trim=trim)
    return _BUNDLE


def _get_limits():
    cfg = make_c172_aircraft()
    return ActuatorLimits(
        max_delta_a=0.35,
        max_delta_e=0.40,
        max_delta_r=0.35,
    )


# ======================================================================
# TEST 1 — Sintesi base con spec di default
# ======================================================================

def test_synthesis_default_spec():
    """La sintesi con spec di default produce guadagni validi e gate PASS."""
    bundle = _get_bundle()
    spec = PerformanceSpec(label="test_default")

    for axis_name, plant in [
        ("pitch", bundle.pitch),
        ("roll", bundle.roll),
        ("yaw", bundle.yaw),
    ]:
        result = synthesize_rate_gains(
            plant, spec, output_limit=0.40, dt=0.02)

        check(result.gains.kp > 0,
              f"{axis_name}: Kp positivo, trovato {result.gains.kp:.4f}")
        check(result.gains.ki > 0,
              f"{axis_name}: Ki positivo, trovato {result.gains.ki:.4f}")
        check(result.gains.kd >= 0,
              f"{axis_name}: Kd non negativo, trovato {result.gains.kd:.4f}")

        check(result.metrics is not None,
              f"{axis_name}: metriche prodotte")
        check(not result.metrics.diverged,
              f"{axis_name}: anello chiuso non diverge")

        check(result.success,
              f"{axis_name}: gate deve passare con spec di default. "
              f"Report:\n{result.gate.report}")


# ======================================================================
# TEST 2 — Saturazione sotto controllo
# ======================================================================

def test_synthesis_no_excessive_saturation():
    """I guadagni sintetizzati non causano saturazione eccessiva."""
    bundle = _get_bundle()
    spec = PerformanceSpec(label="test_sat", saturation_frac_max_pct=15.0)

    result = synthesize_rate_gains(
        bundle.pitch, spec, output_limit=0.40, dt=0.02,
        q_cmd_step=0.15)

    check(result.success,
          f"gate deve passare con limite saturazione 15%. "
          f"Sat={result.metrics.saturation_frac_pct:.1f}%")

    if result.metrics.saturation_frac_pct is not None:
        check(result.metrics.saturation_frac_pct <= 15.0,
              f"saturazione deve essere <=15%, "
              f"trovato {result.metrics.saturation_frac_pct:.1f}%")


# ======================================================================
# TEST 3 — Specifiche diverse → guadagni diversi
# ======================================================================

def test_different_specs_different_gains():
    """Specifiche più aggressive producono guadagni più alti."""
    bundle = _get_bundle()

    spec_smooth = PerformanceSpec(
        label="smooth", bandwidth_wn_min=3.0,
        damping_zeta_min=0.8, damping_zeta_max=1.0)
    spec_aggressive = PerformanceSpec(
        label="aggressive", bandwidth_wn_min=12.0,
        damping_zeta_min=0.5, damping_zeta_max=0.7)

    res_smooth = synthesize_rate_gains(
        bundle.pitch, spec_smooth, output_limit=0.40, dt=0.02)
    res_aggr = synthesize_rate_gains(
        bundle.pitch, spec_aggressive, output_limit=0.40, dt=0.02)

    # Entrambi devono produrre guadagni validi
    check(res_smooth.gains.kp > 0, "smooth: Kp > 0")
    check(res_aggr.gains.kp > 0, "aggressive: Kp > 0")

    # L'aggressivo deve avere guadagni più alti (o ω_n più alto)
    check(res_aggr.omega_n_used >= res_smooth.omega_n_used,
          f"aggressivo deve avere ω_n >= smooth: "
          f"{res_aggr.omega_n_used:.2f} vs {res_smooth.omega_n_used:.2f}")

    # I guadagni devono essere effettivamente diversi
    check(
        abs(res_aggr.gains.kp - res_smooth.gains.kp) > 1e-6 or
        abs(res_aggr.gains.ki - res_smooth.gains.ki) > 1e-6,
        "guadagni devono differire tra smooth e aggressive"
    )


# ======================================================================
# TEST 4 — make_spec_from_aggressiveness
# ======================================================================

def test_aggressiveness_mapping():
    """La mappatura aggressività → spec è monotona e coerente."""
    spec_low = make_spec_from_aggressiveness(0.0, "low")
    spec_mid = make_spec_from_aggressiveness(0.5, "mid")
    spec_high = make_spec_from_aggressiveness(1.0, "high")

    # Bandwidth crescente
    check(spec_low.bandwidth_wn_min < spec_mid.bandwidth_wn_min,
          "aggressività 0 < 0.5 → bandwidth")
    check(spec_mid.bandwidth_wn_min < spec_high.bandwidth_wn_min,
          "aggressività 0.5 < 1.0 → bandwidth")

    # Smorzamento decrescente
    zeta_low = 0.5 * (spec_low.damping_zeta_min + spec_low.damping_zeta_max)
    zeta_high = 0.5 * (spec_high.damping_zeta_min + spec_high.damping_zeta_max)
    check(zeta_low > zeta_high,
          "aggressività alta → smorzamento più basso")

    # Overshoot tollerato crescente
    check(spec_high.overshoot_max_pct >= spec_low.overshoot_max_pct,
          "aggressività alta → overshoot tollerato maggiore")


# ======================================================================
# TEST 5 — Sintesi completa (3 assi)
# ======================================================================

def test_synthesize_full_rate_config():
    """synthesize_full_rate_config produce una RateConfig completa."""
    bundle = _get_bundle()
    limits = _get_limits()
    spec = PerformanceSpec(label="full_config_test")

    config, results = synthesize_full_rate_config(
        bundle, spec, limits, dt=0.02)

    # Verifica struttura
    check(config.roll.kp > 0, "roll Kp > 0")
    check(config.pitch.kp > 0, "pitch Kp > 0")
    check(config.yaw.kp > 0, "yaw Kp > 0")

    check(config.limits.max_delta_e == limits.max_delta_e,
          "limiti attuatori preservati")

    # Verifica trim
    check(config.trim_delta_e == bundle.trim.delta_e,
          "trim delta_e dalla pianta")

    # Verifica segni
    check(config.sign_pitch == bundle.pitch.ctrl_sign,
          "sign_pitch coerente con la pianta")
    check(config.sign_roll == bundle.roll.ctrl_sign,
          "sign_roll coerente con la pianta")
    check(config.sign_yaw == bundle.yaw.ctrl_sign,
          "sign_yaw coerente con la pianta")

    # Verifica risultati per asse
    check(len(results) == 3, "3 risultati di sintesi")
    for axis in ("roll", "pitch", "yaw"):
        check(axis in results, f"risultato per {axis}")
        check(results[axis].success,
              f"{axis}: gate deve passare. Report:\n{results[axis].gate.report}")


# ======================================================================
# TEST 6 — Pianta instabile gestita con grazia
# ======================================================================

def test_unstable_plant_graceful():
    """Una pianta instabile non crasha, ritorna un risultato con messaggio."""
    from flight_controller.plant import AxisPlant

    unstable = AxisPlant(
        axis="test", K_dc=1.0, tau=-1.0,
        M_q=1.0, M_ctrl=1.0, inertia=1.0,
        ctrl_sign=1.0, open_loop_stable=False,
    )

    spec = PerformanceSpec(label="unstable_test")
    result = synthesize_rate_gains(unstable, spec, output_limit=0.4)

    check(not result.success, "pianta instabile → synthesis non riuscita")
    check(len(result.message) > 0, "messaggio diagnostico presente")
    check("instabile" in result.message.lower(),
          "messaggio menziona instabilità")


# ======================================================================
# MAIN + DIAGNOSTICA
# ======================================================================

def main():
    test_synthesis_default_spec()
    test_synthesis_no_excessive_saturation()
    test_different_specs_different_gains()
    test_aggressiveness_mapping()
    test_synthesize_full_rate_config()
    test_unstable_plant_graceful()

    # ------------------------------------------------------------------
    # Diagnostica completa
    # ------------------------------------------------------------------
    bundle = _get_bundle()
    limits = _get_limits()

    print()
    print("=" * 72)
    print("T2 DIAGNOSTICA — Sintesi automatica guadagni PID (C172)")
    print("=" * 72)
    print(f"Condizione di volo: V={bundle.V:.1f} m/s, quota 0")
    print(f"Trim: alpha={math.degrees(bundle.trim.alpha):+.2f}°, "
          f"de={bundle.trim.delta_e:+.4f} rad, "
          f"thr={bundle.trim.throttle:.3f}")

    for aggr, label in [(0.0, "DOLCE"), (0.5, "BILANCIATO"), (1.0, "AGGRESSIVO")]:
        spec = make_spec_from_aggressiveness(aggr, label)
        config, results = synthesize_full_rate_config(
            bundle, spec, limits, dt=0.02)

        print(f"\n--- Aggressività {aggr:.1f} ({label}) ---")
        print(f"  Spec: ω_n≥{spec.bandwidth_wn_min:.1f} rad/s, "
              f"ζ∈[{spec.damping_zeta_min:.2f},{spec.damping_zeta_max:.2f}], "
              f"OS≤{spec.overshoot_max_pct:.0f}%, "
              f"sat≤{spec.saturation_frac_max_pct:.0f}%")

        for axis in ("roll", "pitch", "yaw"):
            r = results[axis]
            g = r.gains
            m = r.metrics
            status = "PASS" if r.success else "FAIL"
            
            # Fallback per metriche None
            os_pct = f"{m.overshoot_pct:.1f}" if m.overshoot_pct is not None else "n/a"
            ts_s = f"{m.settling_time_2pct_s:.2f}" if m.settling_time_2pct_s is not None else "n/a"
            sat_pct = f"{m.saturation_frac_pct:.1f}" if m.saturation_frac_pct is not None else "n/a"
            pm_deg = f"{m.phase_margin_deg:.0f}" if m.phase_margin_deg is not None else "n/a"
            wn_used = f"{r.omega_n_used:.1f}" if r.omega_n_used else "n/a"
            
            print(f"  {axis:6s}: Kp={g.kp:.4f}  Ki={g.ki:.4f}  Kd={g.kd:.5f}  "
                  f"ωn={wn_used}  "
                  f"[{status}]  "
                  f"OS={os_pct}%  "
                  f"ts={ts_s}s  "
                  f"sat={sat_pct}%  "
                  f"PM={pm_deg}°")

    print("=" * 72)
    print()
    print("PASS: T2 sintesi automatica guadagni PID corretta")


if __name__ == "__main__":
    main()