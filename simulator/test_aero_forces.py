"""
simulator/test_aero_forces.py

Test D2.2: forze e momenti aerodinamici.
Verifica direzioni, equilibrio, e coerenza dimensionale.

Uso:
    python simulator/test_aero_forces.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from dynamics.state import AircraftState
from dynamics.atmosphere import Atmosphere
from dynamics.aero.coefficients import (
    AeroCoefficients, make_c172_config,
)
from dynamics.aero.forces import AeroForces

# ----------------------------------------------------------------------
# Configurazione di test
# ----------------------------------------------------------------------
G = 9.80665
MASS = 1000.0  # kg


def make_aero_forces() -> AeroForces:
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)
    return AeroForces(aero)


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual: float, expected: float, tol: float, msg: str) -> None:
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


def test_zero_velocity():
    """Velivolo fermo: forze e momenti nulli."""
    aero = make_aero_forces()
    state = AircraftState()
    state.velocity_body = np.zeros(3)

    forces, moments = aero.compute(state)

    check(np.allclose(forces, 0.0, atol=1e-9), "forze nulle a velocità zero")
    check(np.allclose(moments, 0.0, atol=1e-9), "momenti nulli a velocità zero")


def test_lift_direction():
    """Con alpha positivo, la portanza deve essere verso l'alto (Fz negativa nel body)."""
    aero = make_aero_forces()
    state = AircraftState()
    # Velocità in avanti con alpha = 5°
    V = 50.0
    alpha = math.radians(5.0)
    u = V * math.cos(alpha)
    w = V * math.sin(alpha)
    state.velocity_body = np.array([u, 0.0, w])

    forces, moments = aero.compute(state)

    # Con alpha > 0, CL > 0, quindi la portanza è verso l'alto.
    # Nel body frame, la componente z della portanza è negativa (verso l'alto).
    check(forces[2] < 0, "Fz deve essere negativa (portanza verso l'alto)")

    # Il drag deve opporsi al moto: Fx deve essere negativa (o comunque < 0)
    check(forces[0] < 0, "Fx deve essere negativa (drag opposto al moto)")


def test_drag_always_opposes_motion():
    """Il drag deve sempre opporsi alla direzione del moto."""
    aero = make_aero_forces()
    state = AircraftState()

    # Volo con alpha = 0 (solo velocità lungo x)
    V = 50.0
    state.velocity_body = np.array([V, 0.0, 0.0])

    forces, _ = aero.compute(state)

    # Con alpha = 0, beta = 0: Fx = -D (drag puro lungo -x)
    check(forces[0] < 0, "drag deve essere negativo lungo x (opposto al moto)")
    # Forza laterale nulla per simmetria
    check(abs(forces[1]) < 1.0, "Fy deve essere ~nulla per beta=0")


def test_symmetric_flight():
    """Con beta = 0, la forza laterale deve essere nulla."""
    aero = make_aero_forces()
    state = AircraftState()
    state.velocity_body = np.array([50.0, 0.0, 2.0])  # alpha > 0, beta = 0

    forces, _ = aero.compute(state)

    check(abs(forces[1]) < 1.0,
          "Fy deve essere ~nulla in volo simmetrico (beta=0)")


def test_sideslip_generates_side_force():
    """Con beta > 0, deve esserci una forza laterale."""
    aero = make_aero_forces()
    state = AircraftState()
    # Velocità con componente laterale (beta > 0)
    V = 50.0
    beta = math.radians(5.0)
    u = V * math.cos(beta)
    v = V * math.sin(beta)
    state.velocity_body = np.array([u, v, 0.0])

    forces, _ = aero.compute(state)

    # Con beta > 0, ci deve essere una forza laterale
    check(abs(forces[1]) > 10.0,
          "Fy deve essere significativa con beta > 0")


def test_elevator_effect_on_pitch():
    """L'elevatore deve generare un momento di beccheggio."""
    aero = make_aero_forces()
    state = AircraftState()
    state.velocity_body = np.array([50.0, 0.0, 0.0])

    # Senza elevatore
    _, moments_neutral = aero.compute(state, controls={'delta_e': 0.0})

    # Con elevatore deflesso
    _, moments_elev = aero.compute(state, controls={'delta_e': math.radians(10.0)})

    # Cm_delta_e è negativo: delta_e positivo dà momento di pitch-down
    check(moments_elev[1] < moments_neutral[1],
          "elevatore deflesso deve dare momento di pitch-down")


def test_aileron_effect_on_roll():
    """Gli alettoni devono generare un momento di rollio."""
    aero = make_aero_forces()
    state = AircraftState()
    state.velocity_body = np.array([50.0, 0.0, 0.0])

    _, moments_neutral = aero.compute(state, controls={'delta_a': 0.0})
    _, moments_roll = aero.compute(state, controls={'delta_a': math.radians(15.0)})

    check(moments_roll[0] != moments_neutral[0],
          "alettoni devono generare momento di rollio")


def test_force_magnitude_reasonable():
    """Le forze devono essere dimensionalmente ragionevoli."""
    aero = make_aero_forces()
    state = AircraftState()
    state.velocity_body = np.array([50.0, 0.0, 0.0])

    forces, moments = aero.compute(state)

    # Pressione dinamica a 50 m/s al suolo: q = 0.5 * 1.225 * 2500 ≈ 1531 Pa
    # Forza = q * S * C ≈ 1531 * 16.2 * 0.03 ≈ 745 N per CD = 0.03
    # L'ordine di grandezza deve essere centinaia/migliaia di Newton
    force_mag = np.linalg.norm(forces)
    check(force_mag > 100, f"forza totale troppo piccola: {force_mag} N")
    check(force_mag < 100000, f"forza totale troppo grande: {force_mag} N")


def test_equilibrium_lift_equals_weight():
    """
    Per un volo livellato in equilibrio, la portanza deve bilanciare il peso.
    Verifica che a una certa velocità e alpha, L ≈ m·g.
    """
    aero = make_aero_forces()
    state = AircraftState()

    # Cerchiamo la velocità per cui L = m·g a alpha = 5°
    # L = CL · q · S = CL · 0.5 · ρ · V² · S
    # m·g = CL · 0.5 · ρ · V² · S
    # V² = m·g / (CL · 0.5 · ρ · S)
    alpha = math.radians(5.0)
    cfg = aero.aero.config
    rho = Atmosphere.density(0.0)

    # CL a alpha = 5° (dalla tabella)
    coeffs = aero.aero.compute(alpha=alpha)
    CL = coeffs['CL']

    V_eq = math.sqrt(MASS * G / (CL * 0.5 * rho * cfg.S_ref))

    # Imposta la velocità di equilibrio
    u = V_eq * math.cos(alpha)
    w = V_eq * math.sin(alpha)
    state.velocity_body = np.array([u, 0.0, w])

    forces, _ = aero.compute(state)

    # La componente verticale della forza aerodinamica (nel NED) deve essere ≈ -m·g
    # Nel body frame, con alpha piccolo, Fz ≈ -L ≈ -m·g
    # Trasformiamo nel frame NED per verificare
    # Per semplicità, verifichiamo che la forza verticale (body z) sia ≈ -m·g
    # (approssimazione valida per alpha piccolo)
    L_actual = -forces[2]  # Portanza ≈ -Fz per alpha piccolo

    check_close(L_actual, MASS * G, MASS * G * 0.1,
                "portanza deve bilanciare il peso in equilibrio")


def test_alpha_beta_computation():
    """Verifica il calcolo di alpha e beta."""
    # alpha = 10°, beta = 0
    V = 50.0
    alpha = math.radians(10.0)
    u = V * math.cos(alpha)
    w = V * math.sin(alpha)
    a, b = AeroForces.compute_alpha_beta(np.array([u, 0.0, w]))
    check_close(a, alpha, 1e-6, "alpha calcolato correttamente")
    check_close(b, 0.0, 1e-6, "beta nullo in volo simmetrico")

    # beta = 5°, alpha = 0
    beta = math.radians(5.0)
    u2 = V * math.cos(beta)
    v2 = V * math.sin(beta)
    a2, b2 = AeroForces.compute_alpha_beta(np.array([u2, v2, 0.0]))
    check_close(a2, 0.0, 1e-6, "alpha nullo con w=0")
    check_close(b2, beta, 1e-6, "beta calcolato correttamente")


def test_moments_zero_in_symmetric_flight():
    """In volo simmetrico senza comandi, i momenti di roll e yaw sono nulli."""
    aero = make_aero_forces()
    state = AircraftState()
    state.velocity_body = np.array([50.0, 0.0, 0.0])

    _, moments = aero.compute(state)

    # Roll e yaw devono essere ~nulli in volo simmetrico senza comandi
    check(abs(moments[0]) < 10.0, "momento di roll ~nullo in volo simmetrico")
    check(abs(moments[2]) < 10.0, "momento di yaw ~nullo in volo simmetrico")


def main():
    test_zero_velocity()
    test_lift_direction()
    test_drag_always_opposes_motion()
    test_symmetric_flight()
    test_sideslip_generates_side_force()
    test_elevator_effect_on_pitch()
    test_aileron_effect_on_roll()
    test_force_magnitude_reasonable()
    test_equilibrium_lift_equals_weight()
    test_alpha_beta_computation()
    test_moments_zero_in_symmetric_flight()
    print("PASS: D2.2 forze e momenti aerodinamici corretti")


if __name__ == "__main__":
    main()