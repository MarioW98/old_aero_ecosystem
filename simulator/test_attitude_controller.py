"""
simulator/test_attitude_controller.py

Test (unitari, strutturali): AttitudeController.
Verifica la logica angle rate → angle target → rate target:
freeze, saturazione, segni, wrap-around, reset.
NON verifica magnitudini di risposta (compito del gate model-based).

Le configurazioni qui sono TEST FIXTURE, non guadagni di produzione.
"""

import sys
import math
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent
ROOT = SIM_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM_DIR))

import numpy as np
from dynamics.state import Quaternion, AircraftState
from flight_controller.attitude_controller import (
    AttitudeController, AttitudeConfig, _clamp,
)


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual, expected, tol, msg):
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tol {tol})")
        sys.exit(1)


# ======================================================================
# TEST FIXTURE — config di solo test
# ======================================================================

def _make_test_attitude_config() -> AttitudeConfig:
    return AttitudeConfig(
        kp_roll=4.0,
        kp_pitch=4.0,
        max_roll_rate=0.5,
        max_pitch_rate=1.0,
        max_roll_angle=math.radians(45.0),
        max_pitch_angle=math.radians(30.0),
    )


def _make_state(roll_deg=0.0, pitch_deg=0.0, yaw_deg=0.0) -> AircraftState:
    s = AircraftState()
    s.attitude = Quaternion.from_euler(
        math.radians(roll_deg), math.radians(pitch_deg), math.radians(yaw_deg))
    return s


# ======================================================================
# CLAMP
# ======================================================================

def test_clamp():
    check_close(_clamp(5, -1, 1), 1, 1e-9, "clamp sopra")
    check_close(_clamp(-5, -1, 1), -1, 1e-9, "clamp sotto")
    check_close(_clamp(0.5, -1, 1), 0.5, 1e-9, "clamp interno")


# ======================================================================
# ANGLE RATE → ANGLE TARGET (integrazione con limiti)
# ======================================================================

def test_stick_neutral_freezes_target():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac.set_targets_from_state(_make_state(roll_deg=10.0, pitch_deg=5.0))
    rt_before = ac.roll_target
    pt_before = ac.pitch_target
    for _ in range(100):
        ac.compute(_make_state(roll_deg=10.0, pitch_deg=5.0), 0.0, 0.0, 0.02)
    check_close(ac.roll_target, rt_before, 1e-9, "roll target congelato")
    check_close(ac.pitch_target, pt_before, 1e-9, "pitch target congelato")


def test_stick_full_increases_target():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac.set_targets_from_state(_make_state())
    for _ in range(150):
        ac.compute(_make_state(), 1.0, 0.0, 0.02)
    check_close(ac.roll_target, cfg.max_roll_angle, 1e-6,
                "roll target al limite massimo")


def test_stick_full_decreases_pitch():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac.set_targets_from_state(_make_state(pitch_deg=5.0))
    for _ in range(150):
        ac.compute(_make_state(pitch_deg=5.0), 0.0, -1.0, 0.02)
    check_close(ac.pitch_target, -cfg.max_pitch_angle, 1e-6,
                "pitch target al limite minimo")


def test_target_rate_limited():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac.set_targets_from_state(_make_state())
    ac.compute(_make_state(), 1.0, 0.0, 0.02)
    expected = cfg.max_roll_rate * 0.02
    check_close(ac.roll_target, expected, 1e-6,
                "angle target cresce al rate max per passo")


# ======================================================================
# ERRORE ANGOLARE → RATE TARGET (P puro, struttura)
# ======================================================================

def test_zero_error_zero_rate():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    state = _make_state(roll_deg=10.0, pitch_deg=5.0)
    ac.set_targets_from_state(state)
    p_cmd, q_cmd = ac.compute(state, 0.0, 0.0, 0.02)
    check_close(p_cmd, 0.0, 1e-6, "p_cmd=0 con errore nullo")
    check_close(q_cmd, 0.0, 1e-6, "q_cmd=0 con errore nullo")


def test_positive_error_positive_rate():
    """Errore piccolo (range lineare) → p_cmd = kp * error."""
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac.set_targets_from_state(_make_state(roll_deg=15.0))
    # Errore 5°: sotto la soglia di saturazione (0.5/4.0 = 7.16°)
    p_cmd, _ = ac.compute(_make_state(roll_deg=10.0), 0.0, 0.0, 0.02)
    check(p_cmd > 0, f"p_cmd positivo, trovato {p_cmd:.4f}")
    error = math.radians(5.0)
    expected = cfg.kp_roll * error
    check(expected < cfg.max_roll_rate, "test invalido: errore porta alla saturazione")
    check_close(p_cmd, expected, 1e-6, "p_cmd = kp * roll_error (range lineare)")


def test_rate_target_saturated():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac.set_targets_from_state(_make_state(roll_deg=45.0))
    p_cmd, _ = ac.compute(_make_state(roll_deg=0.0), 0.0, 0.0, 0.02)
    check(abs(p_cmd) <= cfg.max_roll_rate + 1e-9,
          f"p_cmd saturo: {p_cmd:.4f} <= {cfg.max_roll_rate}")


def test_pitch_error_sign():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac.set_targets_from_state(_make_state(pitch_deg=15.0))
    _, q_cmd = ac.compute(_make_state(pitch_deg=5.0), 0.0, 0.0, 0.02)
    check(q_cmd > 0, f"q_cmd positivo (cabrata), trovato {q_cmd:.4f}")


# ======================================================================
# WRAP-AROUND ROLL (percorso più corto)
# ======================================================================

def test_roll_wraparound():
    """
    Target +170°, corrente -170°: il percorso più corto è -20°
    (roll sinistro attraverso ±180°), NON +340°.
    """
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac._roll_target = math.radians(170.0)
    p_cmd, _ = ac.compute(_make_state(roll_deg=-170.0), 0.0, 0.0, 0.02)
    check(p_cmd < 0,
          f"p_cmd negativo per percorso corto -20°, trovato {p_cmd:.4f}")
    check_close(p_cmd, -cfg.max_roll_rate, 1e-9, "p_cmd saturo al limite")

    # Speculare: target -170°, corrente +170° → percorso corto +20°
    ac2 = AttitudeController(cfg)
    ac2._roll_target = math.radians(-170.0)
    p_cmd2, _ = ac2.compute(_make_state(roll_deg=170.0), 0.0, 0.0, 0.02)
    check(p_cmd2 > 0,
          f"p_cmd positivo per percorso corto +20°, trovato {p_cmd2:.4f}")


# ======================================================================
# RESET E SET_TARGETS
# ======================================================================

def test_reset():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    ac.set_targets_from_state(_make_state(roll_deg=20.0, pitch_deg=10.0))
    ac.reset()
    check_close(ac.roll_target, 0.0, 1e-9, "roll target azzerato")
    check_close(ac.pitch_target, 0.0, 1e-9, "pitch target azzerato")


def test_set_targets_from_state():
    cfg = _make_test_attitude_config()
    ac = AttitudeController(cfg)
    state = _make_state(roll_deg=15.0, pitch_deg=8.0)
    ac.set_targets_from_state(state)
    check_close(ac.roll_target, math.radians(15.0), 1e-6, "roll target = corrente")
    check_close(ac.pitch_target, math.radians(8.0), 1e-6, "pitch target = corrente")


def main():
    test_clamp()
    test_stick_neutral_freezes_target()
    test_stick_full_increases_target()
    test_stick_full_decreases_pitch()
    test_target_rate_limited()
    test_zero_error_zero_rate()
    test_positive_error_positive_rate()
    test_rate_target_saturated()
    test_pitch_error_sign()
    test_roll_wraparound()
    test_reset()
    test_set_targets_from_state()
    print("PASS: test strutturali AttitudeController corretti")


if __name__ == "__main__":
    main()