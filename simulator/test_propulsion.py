"""
simulator/test_propulsion.py

Test D3.1 refactored: propulsione a tre livelli.
Verifica motore, elica e powerplant separatamente.

Uso:
    python simulator/test_propulsion.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from dynamics.propulsion.engine import EngineModel, EngineConfig, make_c172_engine
from dynamics.propulsion.propeller import PropellerModel, PropellerConfig, make_c172_propeller
from dynamics.propulsion.powerplant import Powerplant, make_c172_powerplant, make_generic_powerplant


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual: float, expected: float, tol: float, msg: str) -> None:
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


# ======================================================================
# TEST LIVELLO 1: MOTORE
# ======================================================================

def test_engine_zero_throttle():
    """Throttle=0: potenza nulla, RPM al minimo."""
    engine = EngineModel(make_c172_engine())
    power, torque, rpm = engine.compute(0.0)

    check_close(power, 0.0, 1e-9, "potenza nulla a throttle=0")
    check_close(rpm, 700.0, 1e-6, "RPM al minimo a throttle=0")
    check_close(torque, 0.0, 1e-9, "coppia nulla a throttle=0")


def test_engine_full_throttle():
    """Throttle=1: potenza massima, RPM massimo."""
    cfg = make_c172_engine()
    engine = EngineModel(cfg)
    power, torque, rpm = engine.compute(1.0)

    check_close(power, cfg.P_max, 1e-6, "potenza massima a throttle=1")
    check_close(rpm, cfg.rpm_max, 1e-6, "RPM massimo a throttle=1")
    check(torque > 0, "coppia positiva a throttle=1")


def test_engine_half_throttle():
    """Throttle=0.5: potenza dimezzata."""
    cfg = make_c172_engine()
    engine = EngineModel(cfg)
    power, _, rpm = engine.compute(0.5)

    check_close(power, 0.5 * cfg.P_max, 1e-6, "potenza dimezzata a throttle=0.5")
    expected_rpm = cfg.rpm_idle + 0.5 * (cfg.rpm_max - cfg.rpm_idle)
    check_close(rpm, expected_rpm, 1e-6, "RPM a throttle=0.5")


def test_engine_torque_consistency():
    """La coppia deve essere coerente: τ = P / ω."""
    engine = EngineModel(make_c172_engine())
    power, torque, rpm = engine.compute(0.8)

    omega = rpm * 2.0 * math.pi / 60.0
    expected_torque = power / omega
    check_close(torque, expected_torque, 1e-6, "τ = P/ω")


# ======================================================================
# TEST LIVELLO 2: ELICA
# ======================================================================

def test_propeller_zero_power():
    """Potenza=0: spinta e momenti nulli."""
    prop = PropellerModel(make_c172_propeller())
    thrust, moments = prop.compute(0.0, velocity=40.0, alpha=0.0)

    check_close(thrust, 0.0, 1e-9, "spinta nulla a potenza=0")
    check(np.allclose(moments, 0.0, atol=1e-9), "momenti nulli a potenza=0")


def test_propeller_dynamic_thrust():
    """A V > V_min: spinta = η·P/V."""
    cfg = make_c172_propeller()
    prop = PropellerModel(cfg)

    power = 80000.0  # W
    velocity = 40.0  # m/s
    thrust, _ = prop.compute(power, velocity, alpha=0.0)

    expected = cfg.eta * power / velocity
    check_close(thrust, expected, 1e-6, "spinta dinamica T = η·P/V")


def test_propeller_static_thrust():
    """A V ≈ 0: spinta statica proporzionale alla potenza."""
    cfg = make_c172_propeller()
    prop = PropellerModel(cfg)

    # A piena potenza statica
    power = 119000.0  # P_max del C172
    thrust, _ = prop.compute(power, velocity=0.0, alpha=0.0)

    check_close(thrust, cfg.T_static_max, 100.0,
                "spinta statica ≈ T_static_max a piena potenza")


def test_propeller_yaw_moment():
    """La coppia reattiva genera Mz negativo (yaw sinistro)."""
    cfg = make_c172_propeller()
    prop = PropellerModel(cfg)

    thrust, moments = prop.compute(80000.0, velocity=40.0, alpha=0.0)

    expected_Mz = -cfg.k_yaw * thrust
    check(moments[2] < 0, "Mz negativo (yaw sinistro)")
    check_close(moments[2], expected_Mz, 1e-6, "Mz = -k_yaw * T")


def test_propeller_pitch_moment():
    """L'offset della linea di spinta genera My."""
    cfg = make_c172_propeller()
    prop = PropellerModel(cfg)

    thrust, moments = prop.compute(80000.0, velocity=40.0, alpha=0.0)

    expected_My = -cfg.thrust_offset_z * thrust
    check(moments[1] > 0, "My positivo (nose-up con spinta sotto CG)")
    check_close(moments[1], expected_My, 1e-6, "My = -offset_z * T")


def test_propeller_pfactor():
    """Il P-factor è proporzionale ad alpha."""
    cfg = make_c172_propeller()
    prop = PropellerModel(cfg)

    _, moments_0 = prop.compute(80000.0, velocity=40.0, alpha=0.0)
    _, moments_10 = prop.compute(80000.0, velocity=40.0, alpha=math.radians(10.0))

    check_close(moments_0[0], 0.0, 1e-9, "P-factor nullo ad alpha=0")
    check(abs(moments_10[0]) > abs(moments_0[0]),
          "P-factor aumenta con alpha")


# ======================================================================
# TEST LIVELLO 3: POWERPLANT
# ======================================================================

def test_powerplant_zero_throttle():
    """Throttle=0: forze e momenti nulli."""
    pp = make_c172_powerplant()
    forces, moments, telem = pp.compute(throttle=0.0, velocity=40.0, alpha=0.0)

    check(np.allclose(forces, 0.0, atol=1e-9), "forze nulle a throttle=0")
    check(np.allclose(moments, 0.0, atol=1e-9), "momenti nulli a throttle=0")
    check_close(telem['thrust'], 0.0, 1e-9, "spinta nulla a throttle=0")


def test_powerplant_full_throttle():
    """Throttle=1: spinta positiva lungo x."""
    pp = make_c172_powerplant()
    forces, moments, telem = pp.compute(throttle=1.0, velocity=40.0, alpha=0.0)

    check(forces[0] > 0, "Fx positiva (spinta in avanti)")
    check_close(forces[1], 0.0, 1e-9, "Fy nulla")
    check_close(forces[2], 0.0, 1e-9, "Fz nulla")
    check(telem['rpm'] > 2000, "RPM alto a throttle=1")
    check(telem['power'] > 100000, "potenza alta a throttle=1")


def test_powerplant_throttle_clamp():
    """Throttle fuori range viene clampato."""
    pp = make_c172_powerplant()

    forces_neg, _, _ = pp.compute(throttle=-0.5, velocity=40.0)
    check_close(forces_neg[0], 0.0, 1e-9, "throttle negativo clampato")

    forces_over, _, telem = pp.compute(throttle=1.5, velocity=40.0)
    forces_max, _, _ = pp.compute(throttle=1.0, velocity=40.0)
    check_close(forces_over[0], forces_max[0], 1e-6, "throttle > 1 clampato")


def test_generic_powerplant_no_moments():
    """Il powerplant generico non produce momenti parassiti."""
    pp = make_generic_powerplant()
    forces, moments, _ = pp.compute(throttle=1.0, velocity=40.0,
                                     alpha=math.radians(10.0))

    check(forces[0] > 0, "spinta positiva")
    check(np.allclose(moments, 0.0, atol=1e-9),
          "powerplant generico senza momenti")


def test_powerplant_sustained_flight():
    """Coerenza: la spinta a un certo throttle bilancia il drag."""
    sys.path.insert(0, str(ROOT))
    from dynamics.aero.coefficients import AeroCoefficients, make_c172_config
    from dynamics.aero.forces import AeroForces
    from dynamics.state import AircraftState

    # Setup aerodinamica
    aero_cfg = make_c172_config()
    aero = AeroCoefficients(aero_cfg)
    aero_forces = AeroForces(aero)

    # Setup powerplant
    pp = make_c172_powerplant()

    # Condizione: V = 42 m/s, alpha = 5°
    V = 42.0
    alpha = math.radians(5.0)
    state = AircraftState()
    state.velocity_body = np.array([V * math.cos(alpha), 0.0, V * math.sin(alpha)])

    # Drag
    F_aero, _ = aero_forces.compute(state)
    drag = -F_aero[0]

    # Trova il throttle che bilancia il drag
    # Spinta = η * P / V → P = spinta * V / η → throttle = P / P_max
    cfg_engine = make_c172_engine()
    cfg_prop = make_c172_propeller()
    throttle_needed = drag * V / (cfg_prop.eta * cfg_engine.P_max)

    check(0.0 < throttle_needed < 1.0,
          f"throttle per volo sostenuto in (0,1): {throttle_needed:.3f}")

    # Verifica che a quel throttle la spinta ≈ drag
    forces_pp, _, _ = pp.compute(throttle=throttle_needed, velocity=V, alpha=alpha)
    check_close(forces_pp[0], drag, 50.0,
                "spinta ≈ drag in volo sostenuto")


def main():
    # Livello 1: Motore
    test_engine_zero_throttle()
    test_engine_full_throttle()
    test_engine_half_throttle()
    test_engine_torque_consistency()

    # Livello 2: Elica
    test_propeller_zero_power()
    test_propeller_dynamic_thrust()
    test_propeller_static_thrust()
    test_propeller_yaw_moment()
    test_propeller_pitch_moment()
    test_propeller_pfactor()

    # Livello 3: Powerplant
    test_powerplant_zero_throttle()
    test_powerplant_full_throttle()
    test_powerplant_throttle_clamp()
    test_generic_powerplant_no_moments()
    test_powerplant_sustained_flight()

    print("PASS: D3.1 propulsione a tre livelli corretta")


if __name__ == "__main__":
    main()