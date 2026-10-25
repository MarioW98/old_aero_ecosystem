"""
simulator/test_performance_spec.py

Test T0: gate di accettazione oggettivo e configurabile.
Verifica la logica di confronto (direzioni, bande, pending, override
della spec) senza dipendere da pianta o simulazione.

Uso:
    py -3.12 -m simulator.test_performance_spec
"""

import sys
from dataclasses import replace
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent
ROOT = SIM_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM_DIR))

from flight_controller.performance_spec import (
    PerformanceSpec, Metrics, GateResult, CheckResult, CheckStatus, evaluate,
)


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def _perfect_metrics() -> Metrics:
    """Metrics che soddisfano tutti i default."""
    return Metrics(
        bandwidth_wn=8.0, damping_zeta=0.7, overshoot_pct=8.0,
        settling_time_2pct_s=0.5, ss_rate_tracking_err_pct=2.0,
        phase_margin_deg=55.0, gain_margin_db=10.0,
        saturation_frac_pct=5.0, diverged=False,
    )


def _find(gate: GateResult, name: str) -> CheckResult:
    for c in gate.checks:
        if c.name == name:
            return c
    raise AssertionError(f"check '{name}' non trovata")


# ----------------------------------------------------------------------
# Default e struttura
# ----------------------------------------------------------------------

def test_default_spec_values():
    s = PerformanceSpec()
    check(s.bandwidth_wn_min == 7.0, "bandwidth default 7")
    check(s.overshoot_max_pct == 15.0, "overshoot default 15")
    check(s.phase_margin_min_deg == 45.0, "fase default 45")
    check(s.divergence_allowed is False, "divergenza non permessa di default")
    check(s.damping_zeta_min < s.damping_zeta_max, "banda ζ coerente")


def test_metrics_default_none_not_diverged():
    m = Metrics()
    check(m.bandwidth_wn is None, "bandwidth default None")
    check(m.diverged is False, "diverged default False")


# ----------------------------------------------------------------------
# Passa tutto
# ----------------------------------------------------------------------

def test_pass_all():
    gate = evaluate(PerformanceSpec(), _perfect_metrics())
    check(gate.passed is True, "gate deve passare")
    check(gate.fully_evaluated is True, "gate completo")
    check(gate.failed_count == 0, "zero fallimenti")
    check(gate.pending_count == 0, "zero pending")
    check(all(c.status == CheckStatus.PASS for c in gate.checks),
          "tutte le check PASS")


# ----------------------------------------------------------------------
# Singoli fallimenti (direzioni corrette)
# ----------------------------------------------------------------------

def test_fail_overshoot():
    m = _perfect_metrics(); m.overshoot_pct = 30.0
    gate = evaluate(PerformanceSpec(), m)
    check(gate.passed is False, "overshoot alto → fail")
    check(_find(gate, "Overshoot").status == CheckStatus.FAIL, "check overshoot FAIL")
    check("Overshoot" in gate.report, "report cita overshoot")


def test_fail_diverged():
    m = _perfect_metrics(); m.diverged = True
    gate = evaluate(PerformanceSpec(), m)
    check(gate.passed is False, "divergenza → fail")
    check(_find(gate, "Divergenza").status == CheckStatus.FAIL, "check divergenza FAIL")


def test_fail_bandwidth_low():
    m = _perfect_metrics(); m.bandwidth_wn = 3.0   # < 7
    gate = evaluate(PerformanceSpec(), m)
    check(_find(gate, "Bandwidth ωn").status == CheckStatus.FAIL,
          "bandwidth sotto target → FAIL (>=)")


def test_fail_phase_margin_low():
    m = _perfect_metrics(); m.phase_margin_deg = 30.0  # < 45
    check(_find(evaluate(PerformanceSpec(), m), "Margine di fase").status
          == CheckStatus.FAIL, "margine fase basso → FAIL (>=)")


def test_fail_gain_margin_low():
    m = _perfect_metrics(); m.gain_margin_db = 3.0   # < 6
    check(_find(evaluate(PerformanceSpec(), m), "Margine di guadagno").status
          == CheckStatus.FAIL, "margine guadagno basso → FAIL (>=)")


def test_fail_settling_high():
    m = _perfect_metrics(); m.settling_time_2pct_s = 1.2  # > 0.8
    check(_find(evaluate(PerformanceSpec(), m), "Settling 2%").status
          == CheckStatus.FAIL, "settling alto → FAIL (<=)")


def test_fail_ss_err_high():
    m = _perfect_metrics(); m.ss_rate_tracking_err_pct = 8.0  # > 5
    check(_find(evaluate(PerformanceSpec(), m), "Err. regime rate").status
          == CheckStatus.FAIL, "errore a regime alto → FAIL (<=)")


def test_fail_saturation_high():
    m = _perfect_metrics(); m.saturation_frac_pct = 30.0  # > 20
    check(_find(evaluate(PerformanceSpec(), m), "Saturazione attuatori").status
          == CheckStatus.FAIL, "saturazione alta → FAIL (<=)")


# ----------------------------------------------------------------------
# Banda di smorzamento: né sotto né sopra
# ----------------------------------------------------------------------

def test_damping_band():
    lo = _perfect_metrics(); lo.damping_zeta = 0.3
    hi = _perfect_metrics(); hi.damping_zeta = 0.95
    ok = _perfect_metrics(); ok.damping_zeta = 0.7
    check(_find(evaluate(PerformanceSpec(), lo), "Smorzamento ζ").status
          == CheckStatus.FAIL, "ζ troppo basso → FAIL")
    check(_find(evaluate(PerformanceSpec(), hi), "Smorzamento ζ").status
          == CheckStatus.FAIL, "ζ troppo alto → FAIL")
    check(_find(evaluate(PerformanceSpec(), ok), "Smorzamento ζ").status
          == CheckStatus.PASS, "ζ in banda → PASS")


# ----------------------------------------------------------------------
# Pending: metriche non calcolate non fanno fallire ma rendono incompleto
# ----------------------------------------------------------------------

def test_pending_when_none():
    gate = evaluate(PerformanceSpec(), Metrics())   # tutto None, diverged False
    check(gate.passed is True, "nessun FAIL → passed True (solo divergenza nota)")
    check(gate.fully_evaluated is False, "con None → non completo")
    check(gate.pending_count == 8, "8 metriche None → 8 pending")
    check(_find(gate, "Overshoot").status == CheckStatus.PENDING, "overshoot pending")


# ----------------------------------------------------------------------
# Configurabilità: override della spec cambia l'esito
# ----------------------------------------------------------------------

def test_custom_spec_override():
    m = _perfect_metrics(); m.overshoot_pct = 10.0
    # Con default (max 15) passa
    check(evaluate(PerformanceSpec(), m).passed is True, "overshoot 10 ok con default")
    # Stringendo il limite a 5, fallisce → dimostra che la spec è configurabile
    strict = replace(PerformanceSpec(), overshoot_max_pct=5.0)
    check(evaluate(strict, m).passed is False, "overshoot 10 fail con spec stretta")


def test_divergence_allowed_override():
    m = _perfect_metrics(); m.diverged = True
    loose = replace(PerformanceSpec(), divergence_allowed=True)
    check(evaluate(loose, m).passed is True,
          "con divergence_allowed=True la divergenza non fa fail")


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------

def test_report_format():
    gate = evaluate(PerformanceSpec(), _perfect_metrics())
    check(isinstance(gate.report, str) and len(gate.report) > 0, "report non vuoto")
    check("GATE DI ACCETTAZIONE" in gate.report, "report ha header")
    check("rate_loop_default" in gate.report, "report ha label")
    check("ESITO" in gate.report, "report ha esito")


def main():
    test_default_spec_values()
    test_metrics_default_none_not_diverged()
    test_pass_all()
    test_fail_overshoot()
    test_fail_diverged()
    test_fail_bandwidth_low()
    test_fail_phase_margin_low()
    test_fail_gain_margin_low()
    test_fail_settling_high()
    test_fail_ss_err_high()
    test_fail_saturation_high()
    test_damping_band()
    test_pending_when_none()
    test_custom_spec_override()
    test_divergence_allowed_override()
    test_report_format()
    print("PASS: T0 gate di accettazione oggettivo e configurabile")


if __name__ == "__main__":
    main()