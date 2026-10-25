"""
simulator/test_state.py

Test D1.1: quaternioni e stato velivolo.

Uso:
    python simulator/test_state.py
"""

import sys
import math
from pathlib import Path

# Rende importabile dynamics/ dalla root del simulatore
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from dynamics.state import Quaternion, AircraftState


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def test_identity():
    """Il quaternione identità non ha rotazione."""
    q = Quaternion.identity()
    check(abs(q.w - 1.0) < 1e-9, "identity w")
    check(abs(q.x) < 1e-9, "identity x")
    check(abs(q.y) < 1e-9, "identity y")
    check(abs(q.z) < 1e-9, "identity z")
    check(abs(q.magnitude() - 1.0) < 1e-9, "identity magnitude")


def test_euler_round_trip():
    """Eulero -> quaternione -> Eulero deve tornare agli stessi angoli."""
    test_cases = [
        (0.0, 0.0, 0.0),
        (math.radians(30), 0.0, 0.0),          # solo roll
        (0.0, math.radians(45), 0.0),          # solo pitch
        (0.0, 0.0, math.radians(90)),          # solo yaw
        (math.radians(10), math.radians(20), math.radians(30)),
        (math.radians(-15), math.radians(25), math.radians(-45)),
        (math.radians(5), math.radians(80), math.radians(170)),  # pitch alto (tailsitter)
    ]
    for roll, pitch, yaw in test_cases:
        q = Quaternion.from_euler(roll, pitch, yaw)
        r2, p2, y2 = q.to_euler()
        check(abs(r2 - roll) < 1e-6,
              f"roll round-trip: atteso {math.degrees(roll):.2f}, ottenuto {math.degrees(r2):.2f}")
        check(abs(p2 - pitch) < 1e-6,
              f"pitch round-trip: atteso {math.degrees(pitch):.2f}, ottenuto {math.degrees(p2):.2f}")
        check(abs(y2 - yaw) < 1e-6,
              f"yaw round-trip: atteso {math.degrees(yaw):.2f}, ottenuto {math.degrees(y2):.2f}")


def test_normalize():
    """La normalizzazione porta la norma a 1 preservando la direzione."""
    q = Quaternion(2.0, 0.0, 0.0, 0.0)  # non normalizzato
    qn = q.normalize()
    check(abs(qn.magnitude() - 1.0) < 1e-9, "normalize magnitude")
    check(abs(qn.w - 1.0) < 1e-9, "normalize direction")


def test_rotation_matrix_identity():
    """Il quaternione identità produce la matrice identità."""
    q = Quaternion.identity()
    R = q.to_rotation_matrix()
    check(np.allclose(R, np.eye(3), atol=1e-9), "identity rotation matrix")


def test_rotation_matrix_yaw90():
    """Con yaw 90° l'asse x del body (avanti) punta a Est."""
    q = Quaternion.from_euler(0.0, 0.0, math.radians(90))
    R = q.to_rotation_matrix()
    v_body = np.array([1.0, 0.0, 0.0])
    v_ned = R @ v_body
    check(abs(v_ned[0] - 0.0) < 1e-6, "yaw90 north component")
    check(abs(v_ned[1] - 1.0) < 1e-6, "yaw90 east component")
    check(abs(v_ned[2] - 0.0) < 1e-6, "yaw90 down component")


def test_quaternion_composition():
    """La moltiplicazione compone correttamente le rotazioni."""
    # Due rotazioni di 90° di yaw = 180° di yaw
    q90 = Quaternion.from_euler(0.0, 0.0, math.radians(90))
    q180 = q90 * q90
    _, _, yaw = q180.to_euler()
    check(abs(yaw - math.radians(180)) < 1e-6,
          f"composition yaw: atteso 180, ottenuto {math.degrees(yaw):.2f}")


def test_aircraft_state_initial():
    """Lo stato iniziale è coerente."""
    state = AircraftState()
    check(state.altitude == 0.0, "initial altitude")
    check(state.airspeed == 0.0, "initial airspeed")
    check(abs(state.pitch) < 1e-9, "initial pitch")
    check(abs(state.roll) < 1e-9, "initial roll")
    check(abs(state.heading) < 1e-9, "initial heading")


def test_state_altitude():
    """La quota deriva dalla componente down del NED."""
    state = AircraftState()
    state.position[2] = -100.0  # down = -100 -> quota +100 m
    check(abs(state.altitude - 100.0) < 1e-9, "altitude from NED")


def test_state_airspeed():
    """L'airspeed è la norma della velocità body."""
    state = AircraftState()
    state.velocity_body = np.array([50.0, 0.0, 0.0])
    check(abs(state.airspeed - 50.0) < 1e-9, "airspeed from velocity")


def test_state_attitude():
    """Le proprietà di assetto leggono dal quaternione."""
    state = AircraftState()
    state.attitude = Quaternion.from_euler(
        math.radians(15), math.radians(10), math.radians(270))
    check(abs(state.roll - 15.0) < 1e-6, "state roll")
    check(abs(state.pitch - 10.0) < 1e-6, "state pitch")
    check(abs(state.heading - 270.0) < 1e-6, "state heading")


def main():
    test_identity()
    test_euler_round_trip()
    test_normalize()
    test_rotation_matrix_identity()
    test_rotation_matrix_yaw90()
    test_quaternion_composition()
    test_aircraft_state_initial()
    test_state_altitude()
    test_state_airspeed()
    test_state_attitude()
    print("PASS: D1.1 quaternioni e stato velivolo corretti")


if __name__ == "__main__":
    main()