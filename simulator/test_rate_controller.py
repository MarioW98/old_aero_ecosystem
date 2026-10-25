"""
simulator/test_rate_controller.py

Test (unitari, strutturali): PIDController e RateController.

Questi test verificano che i controllori facciano la cosa GIUSTA data una
configurazione: segni corretti, saturazione rispettata, trim applicato,
anti-windup, D-on-measurement. NON verificano magnitudini di risposta
(quello è compito del gate model-based in T0+).

Le configurazioni qui sono TEST FIXTURE: valori scelti per esercitare la
struttura, non guadagni di produzione.
"""

import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent
ROOT = SIM_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM_DIR))

from flight_controller.pid import PIDController, _clamp
from flight_controller.rate_controller import RateController
from flight_controller.fc_config import (
    RateConfig, AxisGains, ActuatorLimits,
)
from dynamics.state import AircraftState
import numpy as np


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual, expected, tol, msg):
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tol {tol})")
        sys.exit(1)


# ======================================================================
# TEST FIXTURE — config di solo test (NON guadagni di produzione)
# ======================================================================

def _make_test_rate_config() -> RateConfig:
    """
    Configurazione di test per il RateController.
    Valori scelti per esercitare struttura (segni, saturazione, trim).
    """
    return RateConfig(
        roll=AxisGains(kp=0.35, ki=0.5, kd=0.04),
        pitch=AxisGains(kp=0.35, ki=0.7, kd=0.06),
        yaw=AxisGains(kp=0.40, ki=0.6, kd=0.08),
        limits=ActuatorLimits(
            max_delta_a=0.35,
            max_delta_e=0.40,
            max_delta_r=0.35,
        ),
        trim_delta_e=-0.05,
        sign_roll=1.0,
        sign_pitch=-1.0,
        sign_yaw=1.0,
        deriv_filter_alpha=0.5,
    )


# ======================================================================
# PID — proprietà strutturali (indipendenti dai guadagni)
# ======================================================================

def test_clamp():
    check_close(_clamp(5, -1, 1), 1, 1e-9, "clamp sopra")
    check_close(_clamp(-5, -1, 1), -1, 1e-9, "clamp sotto")
    check_close(_clamp(0.5, -1, 1), 0.5, 1e-9, "clamp interno")


def test_proportional_only():
    pid = PIDController(kp=2.0, ki=0.0, kd=0.0, output_limit=10.0)
    out = pid.compute(setpoint=1.0, measurement=0.0, dt=0.01)
    check_close(out, 2.0, 1e-9, "P puro: kp*error")
    check_close(pid.p_term, 2.0, 1e-9, "p_term esposto")


def test_saturation():
    pid = PIDController(kp=10.0, ki=0.0, kd=0.0, output_limit=1.0)
    out = pid.compute(setpoint=100.0, measurement=0.0, dt=0.01)
    check_close(out, 1.0, 1e-9, "saturato al limite superiore")
    out = pid.compute(setpoint=-100.0, measurement=0.0, dt=0.01)
    check_close(out, -1.0, 1e-9, "saturato al limite inferiore")


def test_integral_accumulates():
    pid = PIDController(kp=0.0, ki=1.0, kd=0.0, output_limit=100.0)
    pid.compute(setpoint=1.0, measurement=0.0, dt=0.1)
    pid.compute(setpoint=1.0, measurement=0.0, dt=0.1)
    check_close(pid.integral, 0.2, 1e-9, "integrale accumula")


def test_anti_windup_bounds_integral():
    pid = PIDController(kp=0.5, ki=1.0, kd=0.0, output_limit=1.0)
    for _ in range(500):
        pid.compute(setpoint=5.0, measurement=0.0, dt=0.02)
    check(abs(pid.integral) <= 1.0 + 0.5,
          f"anti-windup: integrale limitato, trovato {pid.integral:.3f}")


def test_derivative_on_measurement():
    kd = 1.0
    pid = PIDController(kp=0.0, ki=0.0, kd=kd, output_limit=100.0,
                        deriv_filter_alpha=1.0)
    rate = 0.1
    meas = 0.0
    for _ in range(20):
        meas += rate * 0.02
        pid.compute(setpoint=0.0, measurement=meas, dt=0.02)
    check_close(pid.d_term, -kd * rate, 1e-6, "D on measurement")


def test_derivative_filter_smooths_step():
    pid_nofilt = PIDController(kp=0.0, ki=0.0, kd=1.0, output_limit=100.0,
                               deriv_filter_alpha=1.0)
    pid_filt = PIDController(kp=0.0, ki=0.0, kd=1.0, output_limit=100.0,
                             deriv_filter_alpha=0.2)
    pid_nofilt.compute(0.0, 0.0, 0.02)
    pid_filt.compute(0.0, 0.0, 0.02)
    d_nofilt = pid_nofilt.compute(0.0, 1.0, 0.02)
    d_filt = pid_filt.compute(0.0, 1.0, 0.02)
    check(abs(d_filt) < abs(d_nofilt), "filtro attenua lo spike del D")


def test_reset():
    pid = PIDController(kp=1.0, ki=1.0, kd=1.0, output_limit=1.0)
    for _ in range(10):
        pid.compute(1.0, 0.0, 0.02)
    pid.reset()
    check_close(pid.integral, 0.0, 1e-12, "integrale azzerato")
    check_close(pid.d_term, 0.0, 1e-12, "d_term azzerato")


# ======================================================================
# RATE CONTROLLER — proprietà strutturali (segno, saturazione, trim)
# ======================================================================

def _make_state(p=0.0, q=0.0, r=0.0) -> AircraftState:
    s = AircraftState()
    s.angular_velocity = np.array([p, q, r])
    return s


def test_rate_zero_cmd_returns_trim():
    """Con rate nullo e cmd nullo, output = trim (PID a 0)."""
    cfg = _make_test_rate_config()
    rc = RateController(cfg)
    out = rc.compute(_make_state(), (0.0, 0.0, 0.0), dt=0.02)
    check_close(out['delta_e'], cfg.trim_delta_e, 1e-6, "delta_e = trim in equilibrio")
    check_close(out['delta_a'], 0.0, 1e-6, "delta_a = 0 (no trim roll)")
    check_close(out['delta_r'], 0.0, 1e-6, "delta_r = 0")


def test_rate_correction_sign_pitch():
    """q > q_cmd → il FC comanda delta_e per frenare (direzione, non magnitudine)."""
    cfg = _make_test_rate_config()
    rc = RateController(cfg)
    out = rc.compute(_make_state(q=0.3), (0.0, 0.0, 0.0), dt=0.02)
    # sign_pitch=-1: per frenare q+ serve delta_e > trim
    check(out['delta_e'] > cfg.trim_delta_e,
          f"delta_e deve aumentare per frenare q+, trovato {out['delta_e']:.4f}")


def test_rate_correction_sign_roll():
    """p > p_cmd → delta_a nella direzione opposta (frenare il rollio)."""
    cfg = _make_test_rate_config()
    rc = RateController(cfg)
    out = rc.compute(_make_state(p=0.3), (0.0, 0.0, 0.0), dt=0.02)
    check(out['delta_a'] < 0.0,
          f"delta_a negativo per frenare p+, trovato {out['delta_a']:.4f}")


def test_rate_output_saturated():
    """Le deflessioni non superano mai i limiti attuatori."""
    cfg = _make_test_rate_config()
    rc = RateController(cfg)
    out = rc.compute(_make_state(p=10.0, q=10.0, r=10.0),
                     (0.0, 0.0, 0.0), dt=0.02)
    check(abs(out['delta_a']) <= cfg.limits.max_delta_a + 1e-9, "delta_a saturo")
    check(abs(out['delta_e']) <= cfg.limits.max_delta_e + 1e-9, "delta_e saturo")
    check(abs(out['delta_r']) <= cfg.limits.max_delta_r + 1e-9, "delta_r saturo")


def test_rate_tracking_direction():
    """cmd_pitch > 0 e q=0 → delta_e nella direzione di cabrata (segno)."""
    cfg = _make_test_rate_config()
    rc = RateController(cfg)
    out = rc.compute(_make_state(q=0.0), (0.0, 0.2, 0.0), dt=0.02)
    # Per aumentare q (cabrata) serve delta_e < trim (sign_pitch=-1)
    check(out['delta_e'] < cfg.trim_delta_e,
          f"delta_e deve diminuire per cmd_pitch+, trovato {out['delta_e']:.4f}")


def test_rate_reset():
    cfg = _make_test_rate_config()
    rc = RateController(cfg)
    for _ in range(10):
        rc.compute(_make_state(q=0.5), (0.0, 0.0, 0.0), dt=0.02)
    rc.reset()
    out = rc.compute(_make_state(), (0.0, 0.0, 0.0), dt=0.02)
    check_close(out['delta_e'], cfg.trim_delta_e, 1e-6, "delta_e = trim dopo reset")


def main():
    test_clamp()
    test_proportional_only()
    test_saturation()
    test_integral_accumulates()
    test_anti_windup_bounds_integral()
    test_derivative_on_measurement()
    test_derivative_filter_smooths_step()
    test_reset()
    test_rate_zero_cmd_returns_trim()
    test_rate_correction_sign_pitch()
    test_rate_correction_sign_roll()
    test_rate_output_saturated()
    test_rate_tracking_direction()
    test_rate_reset()
    print("PASS: test strutturali PID e RateController corretti")


if __name__ == "__main__":
    main()