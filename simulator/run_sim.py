"""
simulator/run_sim.py

Entry point per la simulazione di volo con Flight Controller.

Riceve comandi dalla GCS via ZMQ e pubblica telemetria.
In modalità STABILIZE, gli stick comandano rate e il RateController
calcola le superfici. In modalità MANUAL, gli stick comandano
direttamente le superfici (comportamento legacy).

Uso:
    python simulator/run_sim.py
    python simulator/run_sim.py --fc-mode=manual
    python simulator/run_sim.py --gain-schedule
"""

from __future__ import annotations

import sys
import time
import math
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from dynamics.state import Quaternion, AircraftState
from sim_engine import SimEngine
from aircraft.c172 import make_c172_aircraft
from zmq_publisher import SimTelemetryPublisher

from ipc_bus import ControlSubscriber, ControlCommand

# Flight Controller imports
try:
    from flight_controller import (
        RateController,
        PerformanceSpec,
        ActuatorLimits,
        extract_rate_plant,
        synthesize_full_rate_config,
        GainScheduleGrid,
        GainScheduler,
    )
    FC_IMPORT_OK = True
except ImportError as e:
    print(f"WARNING: flight_controller non disponibile: {e}")
    FC_IMPORT_OK = False


# ======================================================================
# COSTANTI
# ======================================================================

# Limiti superfici [rad]
MAX_DELTA_E = 0.40   # ~23° elevatore
MAX_DELTA_A = 0.35   # ~20° alettoni
MAX_DELTA_R = 0.35   # ~20° timone

# Rate massimi comandabili dagli stick [rad/s]
MAX_ROLL_RATE = 1.5    # ~86°/s
MAX_PITCH_RATE = 0.8   # ~46°/s
MAX_YAW_RATE = 0.5     # ~29°/s

# Timeout comandi: se non arrivano comandi per questo tempo, usa i default
CONTROL_TIMEOUT_S = 1.0


# ======================================================================
# HELPER
# ======================================================================

def make_initial_state(altitude: float, speed: float,
                       alpha_deg: float) -> AircraftState:
    """Crea lo stato iniziale del velivolo."""
    state = AircraftState()
    state.position = np.array([0.0, 0.0, -altitude])
    alpha = math.radians(alpha_deg)
    u = speed * math.cos(alpha)
    w = speed * math.sin(alpha)
    state.velocity_body = np.array([u, 0.0, w])
    state.attitude = Quaternion.from_euler(0.0, alpha, 0.0)
    return state


def setup_flight_controller(config, V: float, altitude: float,
                            use_schedule: bool = False):
    """
    Inizializza il flight controller per la condizione di volo data.

    Se il trim fallisce alla condizione iniziale, prova velocità alternative
    vicine per trovare un punto trimmabile.

    Args:
        config: AircraftConfig del velivolo.
        V: velocità iniziale [m/s].
        altitude: quota iniziale [m].
        use_schedule: se True, costruisce una griglia di gain scheduling.

    Returns:
        (rate_controller, scheduler) oppure (None, None) se il setup fallisce.
    """
    if not FC_IMPORT_OK:
        return None, None

    try:
        spec = PerformanceSpec(label="sim_default")
        limits = ActuatorLimits(
            max_delta_a=MAX_DELTA_A,
            max_delta_e=MAX_DELTA_E,
            max_delta_r=MAX_DELTA_R,
        )

        if use_schedule:
            # --- Gain scheduling: griglia di punti ---
            print("  Costruzione griglia gain schedule...")
            grid = GainScheduleGrid()
            grid.build(
                config,
                V_values=[38.0, 42.0, 46.0, 50.0],
                alt_values=[altitude],
                spec=spec,
                limits=limits,
            )
            print(f"  Griglia: {grid.valid_count}/{grid.total_count} "
                  f"punti validi ({grid.coverage_pct:.0f}%)")

            if grid.valid_count == 0:
                print("  WARNING: nessun punto valido nella griglia")
                return None, None

            scheduler = GainScheduler(grid, smoothing_alpha=0.05)
            initial_config = scheduler.update(V, altitude)
            if initial_config is None:
                print("  WARNING: scheduler ha restituito None")
                return None, None

            rate_controller = RateController(initial_config)
            return rate_controller, scheduler

        else:
            # --- Punto singolo: sintesi diretta ---
            # Prova prima la condizione richiesta
            bundle = extract_rate_plant(config, V=V, altitude=altitude, strict=False)
            
            # Se fallisce, prova velocità alternative vicine
            if bundle is None:
                print(f"  WARNING: trim fallito a V={V:.1f} m/s, quota={altitude:.0f} m")
                print("  Provo velocità alternative...")
                alt_speeds = [45.0, 50.0, 38.0, 55.0, 42.0, 40.0]
                for V_try in alt_speeds:
                    bundle = extract_rate_plant(config, V=V_try, altitude=altitude, strict=False)
                    if bundle is not None:
                        print(f"  Trim riuscito a V={V_try:.1f} m/s (uso questo per i guadagni)")
                        break
                
                if bundle is None:
                    print("  WARNING: nessun punto trimmabile trovato, FC non disponibile")
                    return None, None

            rate_config, results = synthesize_full_rate_config(
                bundle, spec, limits)

            # Report sintesi
            for axis, result in results.items():
                status = "OK" if result.success else "FAIL"
                g = result.gains
                print(f"    {axis:6s}: [{status}]  "
                      f"Kp={g.kp:.4f}  Ki={g.ki:.4f}  Kd={g.kd:.5f}")

            rate_controller = RateController(rate_config)
            return rate_controller, None

    except Exception as e:
        print(f"  WARNING: setup FC fallito: {e}")
        import traceback
        traceback.print_exc()
        return None, None
    

# ======================================================================
# SIMULAZIONE
# ======================================================================

def run_simulation(endpoint: str, frequency: float,
                   throttle: float, delta_e: float,
                   altitude: float, speed: float, alpha_deg: float,
                   fc_mode: str = "stabilize",
                   use_schedule: bool = False):
    config = make_c172_aircraft()
    sim = SimEngine(config)
    initial_state = make_initial_state(altitude, speed, alpha_deg)
    sim.reset(initial_state)

    # ------------------------------------------------------------------
    # SETUP FLIGHT CONTROLLER
    # ------------------------------------------------------------------
    rate_controller = None
    scheduler = None
    fc_active = False

    if FC_IMPORT_OK and fc_mode == "stabilize":
        print("  Inizializzazione Flight Controller...")
        rate_controller, scheduler = setup_flight_controller(
            config, speed, altitude, use_schedule)
        if rate_controller is not None:
            fc_active = True

    # ------------------------------------------------------------------
    # CONTROLLI DI DEFAULT (usati se non arrivano comandi dalla GCS)
    # ------------------------------------------------------------------
    default_controls = {
        'throttle': throttle,
        'delta_e': delta_e,
        'delta_a': 0.0,
        'delta_r': 0.0,
    }

    # ------------------------------------------------------------------
    # STATO COMANDI RICEVUTI VIA ZMQ
    # ------------------------------------------------------------------
    received_sticks = {
        'throttle': throttle,
        'roll_stick': 0.0,
        'pitch_stick': 0.0,
        'yaw_stick': 0.0,
    }
    last_control_time = [0.0]  # mutable per accesso nel callback

    def on_control_received(cmd: ControlCommand):
        """Callback chiamato quando arriva un comando dalla GCS."""
        received_sticks['throttle'] = cmd.throttle
        received_sticks['roll_stick'] = cmd.roll_stick
        received_sticks['pitch_stick'] = cmd.pitch_stick
        received_sticks['yaw_stick'] = cmd.yaw_stick
        last_control_time[0] = time.time()

    # Subscriber per comandi dalla GCS
    control_sub = ControlSubscriber(callback=on_control_received)
    control_sub.start()

    # Publisher telemetria
    publisher = SimTelemetryPublisher(endpoint)

    dt = 1.0 / frequency

    # ------------------------------------------------------------------
    # BANNER
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("SIMULATORE DI VOLO — AeroControlQwen")
    print("=" * 60)
    print(f"  Endpoint telemetria: {publisher.endpoint}")
    print(f"  Endpoint comandi:    tcp://127.0.0.1:5556 (SUB)")
    print(f"  Frequenza:           {frequency:.0f} Hz")
    print(f"  Velivolo:            {config.name}")
    print(f"  Quota iniziale:      {altitude:.0f} m")
    print(f"  Velocità iniziale:   {speed:.1f} m/s")
    if fc_active:
        rc = rate_controller.config
        print(f"  Flight Controller:   ACTIVE (STABILIZE)")
        print(f"    Pitch: Kp={rc.pitch.kp:.4f}  "
              f"Ki={rc.pitch.ki:.4f}  Kd={rc.pitch.kd:.5f}")
        print(f"    Roll:  Kp={rc.roll.kp:.4f}  "
              f"Ki={rc.roll.ki:.4f}  Kd={rc.roll.kd:.5f}")
        print(f"    Yaw:   Kp={rc.yaw.kp:.4f}  "
              f"Ki={rc.yaw.ki:.4f}  Kd={rc.yaw.kd:.5f}")
        print(f"    Trim:  de={rc.trim_delta_e:+.4f} rad")
        if scheduler is not None:
            print(f"    Gain scheduling: attivo "
                  f"({scheduler.grid.valid_count} punti)")
    else:
        print(f"  Flight Controller:   INACTIVE (MANUAL)")
    print("=" * 60)
    print()
    print("Controlli dalla GCS: W/S throttle, frecce pitch/roll, A/D yaw")
    print("Premi Ctrl+C per terminare.")
    print()

    # ------------------------------------------------------------------
    # LOOP DI SIMULAZIONE
    # ------------------------------------------------------------------
    try:
        while True:
            loop_start = time.perf_counter()

            # Verifica se ci sono comandi recenti
            elapsed_since_control = time.time() - last_control_time[0]
            has_controls = elapsed_since_control < CONTROL_TIMEOUT_S

            if fc_active and has_controls:
                # ========================================
                # FC MODE: stick → rate → superfici
                # ========================================
                rate_cmd = (
                    received_sticks['roll_stick'] * MAX_ROLL_RATE,
                    received_sticks['pitch_stick'] * MAX_PITCH_RATE,
                    received_sticks['yaw_stick'] * MAX_YAW_RATE,
                )
                surfaces = rate_controller.compute(
                    sim.state, rate_cmd, dt)
                controls = {
                    'throttle': received_sticks['throttle'],
                    **surfaces,
                }

                # Aggiorna gain schedule se disponibile
                if scheduler is not None:
                    V_current = float(
                        np.linalg.norm(sim.state.velocity_body))
                    alt_current = float(-sim.state.position[2])
                    new_config = scheduler.update(V_current, alt_current)
                    if new_config is not None:
                        rate_controller.update_gains(new_config)

            elif has_controls:
                # ========================================
                # MANUAL MODE: stick → superfici dirette
                # ========================================
                controls = {
                    'throttle': received_sticks['throttle'],
                    'delta_e': received_sticks['pitch_stick'] * MAX_DELTA_E,
                    'delta_a': received_sticks['roll_stick'] * MAX_DELTA_A,
                    'delta_r': received_sticks['yaw_stick'] * MAX_DELTA_R,
                }

            else:
                # ========================================
                # NESSUN COMANDO: usa default
                # ========================================
                controls = dict(default_controls)

            # Avanza la simulazione
            sim.step(dt, controls)

            # Telemetria
            telemetry = sim.get_telemetry()
            publisher.publish_telemetry(telemetry)

            # Diagnostica ogni secondo
            if int(sim.state.time) != int(sim.state.time - dt):
                mode_str = "FC " if fc_active else "MAN"
                src = "GCS" if has_controls else "DEF"
                print(f"  t={sim.state.time:7.1f}s  "
                      f"[{mode_str}] [{src}]  "
                      f"quota={telemetry['altitude']:7.1f}m  "
                      f"V={telemetry['airspeed']:5.1f}m/s  "
                      f"VS={telemetry['vertical_speed']:+5.2f}m/s  "
                      f"THR={controls['throttle']:.2f}")

            # Tempo reale
            elapsed = time.perf_counter() - loop_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print()
        print("Simulazione terminata.")
    finally:
        control_sub.stop()
        publisher.close()


# ======================================================================
# MAIN
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Simulatore di volo con Flight Controller.")
    parser.add_argument("--endpoint", type=str, default="tcp://*:5555")
    parser.add_argument("--frequency", type=float, default=50.0)
    parser.add_argument("--throttle", type=float, default=0.6)
    parser.add_argument("--delta-e", type=float, default=-0.05)
    parser.add_argument("--altitude", type=float, default=0.0)
    parser.add_argument("--speed", type=float, default=45.0)
    parser.add_argument("--alpha", type=float, default=5.0)
    parser.add_argument("--fc-mode", type=str, default="stabilize",
                        choices=["manual", "stabilize"],
                        help="Modalità flight controller")
    parser.add_argument("--gain-schedule", action="store_true",
                        help="Usa gain scheduling (avvio più lento)")
    args = parser.parse_args()

    run_simulation(
        endpoint=args.endpoint,
        frequency=args.frequency,
        throttle=args.throttle,
        delta_e=args.delta_e,
        altitude=args.altitude,
        speed=args.speed,
        alpha_deg=args.alpha,
        fc_mode=args.fc_mode,
        use_schedule=args.gain_schedule,
    )


if __name__ == "__main__":
    main()