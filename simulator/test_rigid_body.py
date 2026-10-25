"""
simulator/test_rigid_body.py

Test D1.3: equazioni del moto 6-DoF.
Verifica con casi noti: caduta libera, cinematica, termini giroscopici.

Uso:
    python simulator/test_rigid_body.py
"""

import sys
import math
from pathlib import Path

# Rende importabile dynamics/ dalla root del simulatore
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from dynamics.state import Quaternion, AircraftState
from dynamics.rigid_body import RigidBodyDynamics

# ----------------------------------------------------------------------
# Configurazione di test: velivolo generico
# ----------------------------------------------------------------------
G = 9.80665  # m/s²
MASS = 1000.0  # kg
INERTIA = {
    'Ixx': 1500.0,
    'Iyy': 2500.0,
    'Izz': 3000.0,
    'Ixz': 0.0,  # simmetria rispetto al piano x-z
}


def make_dynamics() -> RigidBodyDynamics:
    return RigidBodyDynamics(mass=MASS, inertia=INERTIA)


def make_state() -> AircraftState:
    return AircraftState()


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual: float, expected: float, tol: float, msg: str) -> None:
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


def check_vec_close(actual, expected, tol: float, msg: str) -> None:
    actual = np.asarray(actual, dtype=float)
    expected = np.asarray(expected, dtype=float)
    if not np.allclose(actual, expected, atol=tol):
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


def test_no_force_no_moment():
    """Velivolo fermo, nessuna forza/momento: tutte le derivate sono nulle."""
    dyn = make_dynamics()
    state = make_state()
    forces = np.zeros(3)
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    check_vec_close(d['position_dot'], [0, 0, 0], 1e-9, "position_dot nullo")
    check_vec_close(d['velocity_dot'], [0, 0, 0], 1e-9, "velocity_dot nullo")
    check_vec_close(d['attitude_dot'], [0, 0, 0, 0], 1e-9, "attitude_dot nullo")
    check_vec_close(d['angular_velocity_dot'], [0, 0, 0], 1e-9,
                    "angular_velocity_dot nullo")


def test_translational_force():
    """Forza costante, velivolo fermo: accelerazione = F/m."""
    dyn = make_dynamics()
    state = make_state()
    forces = np.array([5000.0, 0.0, 0.0])  # 5000 N lungo x
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    # u̇ = Fx/m = 5000/1000 = 5 m/s²
    check_close(d['velocity_dot'][0], 5.0, 1e-9, "u_dot = Fx/m")
    check_close(d['velocity_dot'][1], 0.0, 1e-9, "v_dot nullo")
    check_close(d['velocity_dot'][2], 0.0, 1e-9, "w_dot nullo")


def test_free_fall():
    """Caduta libera: gravità nel body frame, velivolo livellato."""
    dyn = make_dynamics()
    state = make_state()
    # Gravità nel body frame (velivolo livellato, assetto identità):
    # la gravità è verso il basso, cioè +z_body.
    forces = np.array([0.0, 0.0, MASS * G])
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    # ẇ = Fz/m = g
    check_close(d['velocity_dot'][0], 0.0, 1e-9, "u_dot nullo in caduta libera")
    check_close(d['velocity_dot'][1], 0.0, 1e-9, "v_dot nullo in caduta libera")
    check_close(d['velocity_dot'][2], G, 1e-9, "w_dot = g in caduta libera")


def test_rotational_moment():
    """Momento costante attorno a x, velivolo fermo: ṗ = Mx/Ixx."""
    dyn = make_dynamics()
    state = make_state()
    forces = np.zeros(3)
    moments = np.array([3000.0, 0.0, 0.0])  # 3000 N·m attorno a x
    d = dyn.compute_derivatives(state, forces, moments)

    # Con velivolo fermo e Ixz=0: ṗ = Mx/Ixx
    check_close(d['angular_velocity_dot'][0], 3000.0 / INERTIA['Ixx'], 1e-9,
                "p_dot = Mx/Ixx")
    check_close(d['angular_velocity_dot'][1], 0.0, 1e-9, "q_dot nullo")
    check_close(d['angular_velocity_dot'][2], 0.0, 1e-9, "r_dot nullo")


def test_position_kinematics_identity():
    """Velocità body → NED con assetto identità: coincidono."""
    dyn = make_dynamics()
    state = make_state()
    state.velocity_body = np.array([50.0, 0.0, 0.0])  # 50 m/s avanti
    forces = np.zeros(3)
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    # Con assetto identità, body = NED: ṗN = u, ṗE = 0, ṗD = 0
    check_vec_close(d['position_dot'], [50.0, 0.0, 0.0], 1e-9,
                    "position_dot con assetto identità")


def test_position_kinematics_yaw90():
    """Velocità body → NED con yaw 90°: l'asse x del body punta a Est."""
    dyn = make_dynamics()
    state = make_state()
    state.attitude = Quaternion.from_euler(0.0, 0.0, math.radians(90.0))
    state.velocity_body = np.array([50.0, 0.0, 0.0])  # avanti nel body
    forces = np.zeros(3)
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    # Con yaw 90°, il velivolo punta a Est: ṗN = 0, ṗE = u, ṗD = 0
    check_vec_close(d['position_dot'], [0.0, 50.0, 0.0], 1e-6,
                    "position_dot con yaw 90°")


def test_attitude_kinematics_roll_rate():
    """Velocità angolare [p,0,0] con assetto identità: q̇ = ½·(0,p,0,0)."""
    dyn = make_dynamics()
    state = make_state()
    p_rate = 0.5  # rad/s
    state.angular_velocity = np.array([p_rate, 0.0, 0.0])
    forces = np.zeros(3)
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    # q = (1,0,0,0), ω = (p,0,0): q̇ = ½·(0, p, 0, 0)
    check_close(d['attitude_dot'][0], 0.0, 1e-9, "q̇w nullo")
    check_close(d['attitude_dot'][1], 0.5 * p_rate, 1e-9, "q̇x = p/2")
    check_close(d['attitude_dot'][2], 0.0, 1e-9, "q̇y nullo")
    check_close(d['attitude_dot'][3], 0.0, 1e-9, "q̇z nullo")


def test_coriolis_terms():
    """Termini di Coriolis/centrifughi: velocità u e yaw rate r non nulli."""
    dyn = make_dynamics()
    state = make_state()
    u_val = 50.0
    r_val = 0.2  # rad/s
    state.velocity_body = np.array([u_val, 0.0, 0.0])
    state.angular_velocity = np.array([0.0, 0.0, r_val])
    forces = np.zeros(3)
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    # Con F=0:
    #   u̇ = r·v − q·w = 0
    #   v̇ = p·w − r·u = −r·u
    #   ẇ = q·u − p·v = 0
    check_close(d['velocity_dot'][0], 0.0, 1e-9, "u_dot con Coriolis")
    check_close(d['velocity_dot'][1], -r_val * u_val, 1e-9,
                "v_dot = -r·u (Coriolis)")
    check_close(d['velocity_dot'][2], 0.0, 1e-9, "w_dot con Coriolis")


def test_gyroscopic_rotation_about_x():
    """Rotazione attorno ad asse principale x con Ixz=0: nessuna acc. angolare."""
    dyn = make_dynamics()
    state = make_state()
    state.angular_velocity = np.array([0.3, 0.0, 0.0])
    forces = np.zeros(3)
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    # Con Ixz=0 e rotazione pura attorno a x: ṗ = q̇ = ṙ = 0
    check_vec_close(d['angular_velocity_dot'], [0.0, 0.0, 0.0], 1e-9,
                    "nessuna acc. angolare per rotazione attorno ad asse principale")


def test_gyroscopic_coupling():
    """Accoppiamento giroscopico: p e q non nulli generano ṙ."""
    dyn = make_dynamics()
    state = make_state()
    p_val = 0.1
    q_val = 0.2
    state.angular_velocity = np.array([p_val, q_val, 0.0])
    forces = np.zeros(3)
    moments = np.zeros(3)
    d = dyn.compute_derivatives(state, forces, moments)

    # Con M=0 e Ixz=0:
    #   ṙ = [(Ixx - Iyy)·p·q] / Izz  (dalla terza equazione, con r=0)
    # Verifichiamo il segno e il valore atteso.
    expected_r_dot = (INERTIA['Ixx'] - INERTIA['Iyy']) * p_val * q_val / INERTIA['Izz']
    check_close(d['angular_velocity_dot'][2], expected_r_dot, 1e-9,
                "accoppiamento giroscopico ṙ")


def main():
    test_no_force_no_moment()
    test_translational_force()
    test_free_fall()
    test_rotational_moment()
    test_position_kinematics_identity()
    test_position_kinematics_yaw90()
    test_attitude_kinematics_roll_rate()
    test_coriolis_terms()
    test_gyroscopic_rotation_about_x()
    test_gyroscopic_coupling()
    print("PASS: D1.3 equazioni del moto 6-DoF corrette")


if __name__ == "__main__":
    main()