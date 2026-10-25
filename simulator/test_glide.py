"""
simulator/test_glide.py

Test D2.3: validazione end-to-end con planata.
Verifica che tutta la catena (atmosphere → coefficients → forces →
rigid_body → integrator) produca risultati fisicamente coerenti.

Scenario: velivolo in planata senza motore, in condizioni prossime
all'equilibrio (velocità di trim + elevatore compensato).

Uso:
    python simulator/test_glide.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from dynamics.state import Quaternion, AircraftState
from dynamics.atmosphere import Atmosphere
from dynamics.rigid_body import RigidBodyDynamics
from dynamics.integrator import RK4Integrator
from dynamics.aero.coefficients import AeroCoefficients, make_c172_config
from dynamics.aero.forces import AeroForces

# ----------------------------------------------------------------------
# Configurazione del velivolo per il test
# ----------------------------------------------------------------------
G = 9.80665
MASS = 1000.0  # kg
INERTIA = {
    'Ixx': 1500.0,
    'Iyy': 2500.0,
    'Izz': 3000.0,
    'Ixz': 0.0,
}

# Condizioni di trim per la planata
TRIM_ALPHA = math.radians(5.0)     # angolo di attacco di trim
TRIM_SPEED = 42.0                  # m/s (calcolata per L ≈ W)
TRIM_DELTA_E = -0.05              # rad (compensa Cm picchiante)


def compute_gravity_body(state: AircraftState, mass: float) -> np.ndarray:
    """
    Calcola la forza di gravità nel body frame.

    Gravità in NED: [0, 0, m·g] (positivo verso il basso).
    Trasformazione NED → body tramite quaternione coniugato.
    """
    gravity_NED = np.array([0.0, 0.0, mass * G])
    q_conj = state.attitude.conjugate()
    return q_conj.rotate_vector(gravity_NED)


def run_glide_simulation(duration: float,
                         dt: float,
                         initial_altitude: float,
                         initial_speed: float,
                         initial_alpha: float,
                         delta_e: float = 0.0) -> dict:
    """
    Esegue una simulazione di planata (nessuna spinta).

    Args:
        duration: durata della simulazione [s].
        dt: passo temporale [s].
        initial_altitude: quota iniziale [m].
        initial_speed: velocità iniziale [m/s].
        initial_alpha: angolo di attacco iniziale [rad].
        delta_e: deflessione elevatore [rad] per il trim.

    Returns:
        dict con le serie temporali dello stato.
    """
    # Setup componenti
    cfg = make_c172_config()
    aero_coeff = AeroCoefficients(cfg)
    aero_forces = AeroForces(aero_coeff)
    dynamics = RigidBodyDynamics(mass=MASS, inertia=INERTIA)
    integrator = RK4Integrator(dynamics)

    # Stato iniziale
    state = AircraftState()
    state.position = np.array([0.0, 0.0, -initial_altitude])

    # Velocità nel body frame con alpha iniziale
    u = initial_speed * math.cos(initial_alpha)
    w = initial_speed * math.sin(initial_alpha)
    state.velocity_body = np.array([u, 0.0, w])

    # Assetto iniziale: pitch = alpha (approssimazione per planata)
    state.attitude = Quaternion.from_euler(0.0, initial_alpha, 0.0)

    # Controlli: solo elevatore per il trim
    controls = {'delta_e': delta_e, 'delta_a': 0.0, 'delta_r': 0.0}

    # Storage risultati
    times = []
    altitudes = []
    speeds = []
    positions_north = []

    steps = int(duration / dt)
    for _ in range(steps):
        times.append(state.time)
        altitudes.append(state.altitude)
        speeds.append(state.airspeed)
        positions_north.append(state.position[0])

        # Forze aerodinamiche
        F_aero, M_aero = aero_forces.compute(state, controls)

        # Gravità nel body frame
        F_grav = compute_gravity_body(state, MASS)

        # Forze e momenti totali
        F_total = F_aero + F_grav
        M_total = M_aero  # gravità agisce al CG: nessun momento

        # Integrazione
        state = integrator.step(state, F_total, M_total, dt)

    return {
        'times': np.array(times),
        'altitudes': np.array(altitudes),
        'speeds': np.array(speeds),
        'positions_north': np.array(positions_north),
    }


# ----------------------------------------------------------------------
# Utility di verifica
# ----------------------------------------------------------------------
def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual: float, expected: float, tol: float, msg: str) -> None:
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


# ----------------------------------------------------------------------
# Test
# ----------------------------------------------------------------------
def test_glide_descends():
    """Il velivolo deve perdere quota durante la planata."""
    result = run_glide_simulation(
        duration=20.0, dt=0.01,
        initial_altitude=500.0,
        initial_speed=TRIM_SPEED,
        initial_alpha=TRIM_ALPHA,
        delta_e=TRIM_DELTA_E,
    )
    initial_alt = result['altitudes'][0]
    final_alt = result['altitudes'][-1]
    check(final_alt < initial_alt,
          f"quota deve diminuire: iniziale={initial_alt:.1f}, finale={final_alt:.1f}")


def test_glide_speed_bounded():
    """La velocità deve restare in un range ragionevole (non divergere)."""
    result = run_glide_simulation(
        duration=20.0, dt=0.01,
        initial_altitude=500.0,
        initial_speed=TRIM_SPEED,
        initial_alpha=TRIM_ALPHA,
        delta_e=TRIM_DELTA_E,
    )
    speeds = result['speeds']
    check(np.min(speeds) > 10.0,
          f"velocità minima troppo bassa: {np.min(speeds):.1f} m/s")
    check(np.max(speeds) < 100.0,
          f"velocità massima troppo alta: {np.max(speeds):.1f} m/s")


def test_glide_forward_motion():
    """Il velivolo deve avanzare durante la planata."""
    result = run_glide_simulation(
        duration=20.0, dt=0.01,
        initial_altitude=500.0,
        initial_speed=TRIM_SPEED,
        initial_alpha=TRIM_ALPHA,
        delta_e=TRIM_DELTA_E,
    )
    final_pos = result['positions_north'][-1]
    check(final_pos > 200.0,
          f"il velivolo deve avanzare: posizione finale={final_pos:.1f} m")


def test_glide_no_nan():
    """Nessun valore NaN o Inf durante la simulazione."""
    result = run_glide_simulation(
        duration=30.0, dt=0.01,
        initial_altitude=500.0,
        initial_speed=TRIM_SPEED,
        initial_alpha=TRIM_ALPHA,
        delta_e=TRIM_DELTA_E,
    )
    check(not np.any(np.isnan(result['altitudes'])), "NaN nelle altitudini")
    check(not np.any(np.isnan(result['speeds'])), "NaN nelle velocità")
    check(not np.any(np.isnan(result['positions_north'])), "NaN nelle posizioni")
    check(not np.any(np.isinf(result['altitudes'])), "Inf nelle altitudini")
    check(not np.any(np.isinf(result['speeds'])), "Inf nelle velocità")


def test_glide_descent_rate_reasonable():
    """Il rateo di discesa medio deve essere fisicamente ragionevole."""
    result = run_glide_simulation(
        duration=20.0, dt=0.01,
        initial_altitude=500.0,
        initial_speed=TRIM_SPEED,
        initial_alpha=TRIM_ALPHA,
        delta_e=TRIM_DELTA_E,
    )
    total_descent = result['altitudes'][0] - result['altitudes'][-1]
    total_time = result['times'][-1] - result['times'][0]
    avg_descent_rate = total_descent / total_time  # m/s, positivo = discesa

    # Per una planata in equilibrio con L/D ≈ 20, il rateo atteso è ~2 m/s.
    # Range ragionevole: 0.1 - 15 m/s.
    check(avg_descent_rate > 0.1,
          f"rateo di discesa troppo basso: {avg_descent_rate:.3f} m/s")
    check(avg_descent_rate < 15.0,
          f"rateo di discesa troppo alto: {avg_descent_rate:.3f} m/s")


def test_glide_not_vertical():
    """La planata non deve essere verticale (il velivolo avanza)."""
    result = run_glide_simulation(
        duration=20.0, dt=0.01,
        initial_altitude=500.0,
        initial_speed=TRIM_SPEED,
        initial_alpha=TRIM_ALPHA,
        delta_e=TRIM_DELTA_E,
    )
    total_descent = result['altitudes'][0] - result['altitudes'][-1]
    total_forward = result['positions_north'][-1] - result['positions_north'][0]

    if total_descent > 0 and total_forward > 0:
        gamma = math.atan2(total_descent, total_forward)
        check(gamma < math.radians(45.0),
              f"planata troppo ripida: gamma={math.degrees(gamma):.1f}°")
        check(gamma > math.radians(0.1),
              f"planata troppo piatta: gamma={math.degrees(gamma):.1f}°")


def main():
    test_glide_descends()
    test_glide_speed_bounded()
    test_glide_forward_motion()
    test_glide_no_nan()
    test_glide_descent_rate_reasonable()
    test_glide_not_vertical()

    # ------------------------------------------------------------------
    # Stampa diagnostica
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("DIAGNOSTICA PLANATA (20 s, condizioni di trim)")
    print(f"  V0 = {TRIM_SPEED} m/s, alpha0 = {math.degrees(TRIM_ALPHA):.1f}°,"
          f" delta_e = {math.degrees(TRIM_DELTA_E):.1f}°")
    print("=" * 60)

    result = run_glide_simulation(
        duration=20.0, dt=0.01,
        initial_altitude=500.0,
        initial_speed=TRIM_SPEED,
        initial_alpha=TRIM_ALPHA,
        delta_e=TRIM_DELTA_E,
    )

    total_descent = result['altitudes'][0] - result['altitudes'][-1]
    total_forward = result['positions_north'][-1] - result['positions_north'][0]
    total_time = result['times'][-1] - result['times'][0]
    avg_descent_rate = total_descent / total_time
    avg_speed = np.mean(result['speeds'])

    if total_forward > 0:
        gamma = math.atan2(total_descent, total_forward)
    else:
        gamma = math.pi / 2

    print(f"  Durata:              {total_time:.1f} s")
    print(f"  Quota iniziale:      {result['altitudes'][0]:.1f} m")
    print(f"  Quota finale:        {result['altitudes'][-1]:.1f} m")
    print(f"  Discesa totale:      {total_descent:.1f} m")
    print(f"  Avanzamento:         {total_forward:.1f} m")
    print(f"  Rateo discesa medio: {avg_descent_rate:.2f} m/s")
    print(f"  Velocità media:      {avg_speed:.1f} m/s")
    print(f"  Angolo planata:      {math.degrees(gamma):.1f}°")
    if gamma > 0:
        print(f"  Efficienza (L/D):    {1.0 / math.tan(gamma):.1f}")
    print("=" * 60)
    print()
    print("PASS: D2.3 planata end-to-end corretta")


if __name__ == "__main__":
    main()