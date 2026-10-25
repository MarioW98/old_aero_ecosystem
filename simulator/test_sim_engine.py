"""
simulator/test_sim_engine.py

Test D3.2: SimEngine orchestratore.
Verifica il volo sostenuto con motore e la planata senza motore.

Uso:
    python simulator/test_sim_engine.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from dynamics.state import Quaternion, AircraftState
from sim_engine import SimEngine
from aircraft.c172 import make_c172_aircraft


def make_initial_state(altitude=500.0, speed=42.0, alpha_deg=5.0):
    """Crea uno stato iniziale per il volo livellato."""
    state = AircraftState()
    state.position = np.array([0.0, 0.0, -altitude])

    alpha = math.radians(alpha_deg)
    u = speed * math.cos(alpha)
    w = speed * math.sin(alpha)
    state.velocity_body = np.array([u, 0.0, w])
    state.attitude = Quaternion.from_euler(0.0, alpha, 0.0)

    return state


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual, expected, tol, msg):
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


def test_sim_engine_initialization():
    """Il SimEngine si inizializza correttamente."""
    config = make_c172_aircraft()
    sim = SimEngine(config)

    check(sim.mass > 0, "massa positiva")
    check(sim.state is not None, "stato inizializzato")
    check(sim.config.name == "C172", "nome configurazione corretto")


def test_sim_engine_reset():
    """Il reset imposta lo stato correttamente."""
    config = make_c172_aircraft()
    sim = SimEngine(config)

    initial = make_initial_state(altitude=1000.0, speed=50.0)
    sim.reset(initial)

    check_close(sim.state.altitude, 1000.0, 1e-6, "quota dopo reset")
    check_close(sim.state.airspeed, 50.0, 1e-6, "velocità dopo reset")


def test_sim_engine_glide():
    """Con throttle=0, il velivolo plana (perde quota)."""
    config = make_c172_aircraft()
    sim = SimEngine(config)

    initial = make_initial_state(altitude=500.0, speed=42.0, alpha_deg=5.0)
    sim.reset(initial)

    # Simula 10 secondi senza motore, con elevatore per il trim
    dt = 0.01
    controls = {'throttle': 0.0, 'delta_e': -0.05, 'delta_a': 0.0, 'delta_r': 0.0}

    for _ in range(int(10.0 / dt)):
        sim.step(dt, controls)

    telem = sim.get_telemetry()

    # Il velivolo deve aver perso quota
    check(telem['altitude'] < 500.0,
          f"quota deve diminuire in planata: {telem['altitude']:.1f} m")

    # Il velivolo deve essere avanzato
    check(telem['pos_north'] > 100.0,
          f"avanzamento in planata: {telem['pos_north']:.1f} m")

    # La velocità deve essere ragionevole
    check(10.0 < telem['airspeed'] < 100.0,
          f"velocità in planata: {telem['airspeed']:.1f} m/s")

    # Nessun NaN
    check(not math.isnan(telem['altitude']), "NaN nella quota")
    check(not math.isnan(telem['airspeed']), "NaN nella velocità")


def test_sim_engine_sustained_flight():
    """Con throttle sufficiente, il velivolo mantiene la quota o sale."""
    config = make_c172_aircraft()
    sim = SimEngine(config)

    initial = make_initial_state(altitude=500.0, speed=42.0, alpha_deg=5.0)
    sim.reset(initial)

    # Simula 10 secondi con motore a piena potenza
    dt = 0.01
    controls = {'throttle': 1.0, 'delta_e': -0.05, 'delta_a': 0.0, 'delta_r': 0.0}

    for _ in range(int(10.0 / dt)):
        sim.step(dt, controls)

    telem = sim.get_telemetry()

    # Con piena potenza, il velivolo non deve perdere quota rapidamente
    # (potrebbe salire o mantenere, ma non precipitare)
    check(telem['altitude'] > 400.0,
          f"con motore il velivolo non deve precipitare: {telem['altitude']:.1f} m")

    # La spinta deve essere positiva
    check(telem['thrust'] > 0,
          f"spinta positiva con throttle=1: {telem['thrust']:.1f} N")

    # RPM deve essere alto
    check(telem['rpm'] > 2000,
          f"RPM alto con throttle=1: {telem['rpm']:.0f}")


def test_sim_engine_telemetry_completeness():
    """La telemetria contiene tutti i campi attesi."""
    config = make_c172_aircraft()
    sim = SimEngine(config)

    initial = make_initial_state()
    sim.reset(initial)
    sim.step(0.01, {'throttle': 0.5})

    telem = sim.get_telemetry()

    expected_keys = [
        'pos_north', 'pos_east', 'pos_down',
        'pitch', 'roll', 'heading',
        'airspeed', 'altitude',
        'thrust', 'throttle', 'rpm', 'power',
        'time',
    ]

    for key in expected_keys:
        check(key in telem, f"telemetria manca il campo '{key}'")
        check(not math.isnan(telem[key]), f"telemetria '{key}' è NaN")


def test_sim_engine_time_advancement():
    """Il tempo avanza correttamente."""
    config = make_c172_aircraft()
    sim = SimEngine(config)
    sim.reset(make_initial_state())

    dt = 0.01
    for _ in range(100):
        sim.step(dt)

    telem = sim.get_telemetry()
    check_close(telem['time'], 1.0, 1e-6, "tempo dopo 100 passi da 0.01 s")


def main():
    test_sim_engine_initialization()
    test_sim_engine_reset()
    test_sim_engine_glide()
    test_sim_engine_sustained_flight()
    test_sim_engine_telemetry_completeness()
    test_sim_engine_time_advancement()

    # ------------------------------------------------------------------
    # Diagnostica
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("DIAGNOSTICA SIMENGINE (volo sostenuto, 10 s, throttle=1)")
    print("=" * 60)

    config = make_c172_aircraft()
    sim = SimEngine(config)
    initial = make_initial_state(altitude=500.0, speed=42.0, alpha_deg=5.0)
    sim.reset(initial)

    dt = 0.01
    controls = {'throttle': 1.0, 'delta_e': -0.05, 'delta_a': 0.0, 'delta_r': 0.0}
    for _ in range(int(10.0 / dt)):
        sim.step(dt, controls)

    telem = sim.get_telemetry()
    print(f"  Quota:         {telem['altitude']:.1f} m")
    print(f"  Velocità:      {telem['airspeed']:.1f} m/s")
    print(f"  Posizione N:   {telem['pos_north']:.1f} m")
    print(f"  Spinta:        {telem['thrust']:.1f} N")
    print(f"  Throttle:      {telem['throttle']:.2f}")
    print(f"  RPM:           {telem['rpm']:.0f}")
    print(f"  Potenza:       {telem['power']:.0f} W")
    print(f"  Pitch:         {telem['pitch']:.1f}°")
    print(f"  Roll:          {telem['roll']:.1f}°")
    print(f"  Heading:       {telem['heading']:.1f}°")
    print("=" * 60)
    print()
    print("PASS: D3.2 SimEngine orchestratore corretto")


if __name__ == "__main__":
    main()