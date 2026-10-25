"""
simulator/test_integrator.py

Test D1.4: integratore RK4.
Verifica con soluzioni analitiche note.

Uso:
    python simulator/test_integrator.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from dynamics.state import Quaternion, AircraftState
from dynamics.rigid_body import RigidBodyDynamics
from dynamics.integrator import RK4Integrator

# ----------------------------------------------------------------------
# Configurazione di test
# ----------------------------------------------------------------------
G = 9.80665       # m/s²
MASS = 1000.0     # kg
INERTIA = {
    'Ixx': 1500.0,
    'Iyy': 2500.0,
    'Izz': 3000.0,
    'Ixz': 0.0,
}


def make_integrator() -> RK4Integrator:
    dynamics = RigidBodyDynamics(mass=MASS, inertia=INERTIA)
    return RK4Integrator(dynamics)


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual: float, expected: float, tol: float, msg: str) -> None:
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


def test_free_fall():
    """
    Caduta libera: moto uniformemente accelerato.
    v(t) = g·t,  z(t) = z0 + ½·g·t²
    """
    integ = make_integrator()
    state = AircraftState()
    state.position = np.array([0.0, 0.0, -100.0])  # 100 m di quota

    # Gravità nel body frame (assetto identità): [0, 0, m·g]
    forces = np.array([0.0, 0.0, MASS * G])
    moments = np.zeros(3)

    dt = 0.01
    t_total = 2.0
    steps = int(t_total / dt)

    for _ in range(steps):
        state = integ.step(state, forces, moments, dt)

    # Dopo 2 secondi:
    expected_w = G * t_total                        # 19.613 m/s
    expected_z = -100.0 + 0.5 * G * t_total ** 2   # -80.387 m
    expected_alt = 100.0 - 0.5 * G * t_total ** 2   # 80.387 m

    check_close(state.velocity_body[2], expected_w, 0.01,
                "velocità verticale dopo 2 s di caduta libera")
    check_close(state.position[2], expected_z, 0.01,
                "posizione verticale dopo 2 s di caduta libera")
    check_close(state.altitude, expected_alt, 0.01,
                "quota dopo 2 s di caduta libera")


def test_constant_velocity():
    """Moto rettilineo uniforme: nessuna forza, velocità costante."""
    integ = make_integrator()
    state = AircraftState()
    state.position = np.array([0.0, 0.0, -100.0])
    state.velocity_body = np.array([50.0, 0.0, 0.0])

    forces = np.zeros(3)
    moments = np.zeros(3)

    dt = 0.01
    t_total = 2.0
    steps = int(t_total / dt)

    for _ in range(steps):
        state = integ.step(state, forces, moments, dt)

    # Dopo 2 secondi: x = 50·2 = 100 m
    check_close(state.position[0], 100.0, 0.01,
                "posizione x dopo 2 s a velocità costante")
    check_close(state.velocity_body[0], 50.0, 0.01,
                "velocità x costante senza forze")
    check_close(state.position[2], -100.0, 0.01,
                "quota invariata senza forze verticali")


def test_quaternion_normalization():
    """Dopo molti passi con rotazione, il quaternione resta normalizzato."""
    integ = make_integrator()
    state = AircraftState()
    state.angular_velocity = np.array([0.1, 0.2, 0.3])

    forces = np.zeros(3)
    moments = np.zeros(3)

    dt = 0.01
    for _ in range(1000):
        state = integ.step(state, forces, moments, dt)

    mag = state.attitude.magnitude()
    check_close(mag, 1.0, 1e-6,
                "quaternione normalizzato dopo 1000 passi")


def test_rk4_accuracy_constant_acceleration():
    """
    RK4 con accelerazione costante deve dare la soluzione esatta
    (RK4 è esatto per polinomi fino al grado 4).
    """
    integ = make_integrator()
    state = AircraftState()
    state.position = np.array([0.0, 0.0, -100.0])

    forces = np.array([0.0, 0.0, MASS * G])
    moments = np.zeros(3)

    # Integriamo con dt = 0.1 per 1 secondo (10 passi)
    dt = 0.1
    for _ in range(10):
        state = integ.step(state, forces, moments, dt)

    # Soluzione analitica: z = -100 + ½·g·1² = -95.097
    expected_z = -100.0 + 0.5 * G * 1.0 ** 2
    check_close(state.position[2], expected_z, 1e-6,
                "accuratezza RK4 con accelerazione costante (dt=0.1)")


def test_rotation_principal_axis():
    """
    Rotazione attorno ad asse principale (x) con Ixz=0:
    la velocità angolare resta costante (nessuna precessione).
    """
    integ = make_integrator()
    state = AircraftState()
    state.angular_velocity = np.array([0.5, 0.0, 0.0])

    forces = np.zeros(3)
    moments = np.zeros(3)

    dt = 0.01
    for _ in range(100):
        state = integ.step(state, forces, moments, dt)

    check_close(state.angular_velocity[0], 0.5, 1e-6,
                "p costante per rotazione attorno ad asse principale")
    check_close(state.angular_velocity[1], 0.0, 1e-6,
                "q nullo per rotazione attorno ad asse principale")
    check_close(state.angular_velocity[2], 0.0, 1e-6,
                "r nullo per rotazione attorno ad asse principale")


def test_time_advancement():
    """Il tempo dello stato avanza correttamente."""
    integ = make_integrator()
    state = AircraftState()
    forces = np.zeros(3)
    moments = np.zeros(3)

    dt = 0.05
    for _ in range(20):
        state = integ.step(state, forces, moments, dt)

    check_close(state.time, 1.0, 1e-9,
                "tempo dopo 20 passi da 0.05 s")


def test_attitude_evolution():
    """Con velocità angolare costante, l'assetto evolve coerentemente."""
    integ = make_integrator()
    state = AircraftState()
    # Rotazione pura attorno a z (yaw) a 0.1 rad/s
    state.angular_velocity = np.array([0.0, 0.0, 0.1])

    forces = np.zeros(3)
    moments = np.zeros(3)

    dt = 0.01
    t_total = 1.0
    steps = int(t_total / dt)
    for _ in range(steps):
        state = integ.step(state, forces, moments, dt)

    # Dopo 1 secondo: yaw ≈ 0.1 rad ≈ 5.73°
    _, _, yaw = state.attitude.to_euler()
    expected_yaw = 0.1 * t_total
    check_close(yaw, expected_yaw, 0.01,
                "yaw dopo 1 s di rotazione costante attorno a z")


def main():
    test_free_fall()
    test_constant_velocity()
    test_quaternion_normalization()
    test_rk4_accuracy_constant_acceleration()
    test_rotation_principal_axis()
    test_time_advancement()
    test_attitude_evolution()
    print("PASS: D1.4 integratore RK4 corretto")


if __name__ == "__main__":
    main()