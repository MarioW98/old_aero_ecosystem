"""
tools/test_publisher.py

Publisher di telemetria standalone. Da usare con la GUI:
  1. Avvia la GUI:            cd gcs_ui && python3 -m sim_ui.main
  2. Avvia questo publisher:  cd aerospace-ecosystem && python3 tools/test_publisher.py
  3. Nella GUI: Telemetria -> ZeroMQ (Simulatore)

Uso:
    python3 tools/test_publisher.py [--hz 30] [--duration 0]
"""

import sys
import time
import math
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ipc_bus import TelemetryData, TelemetryPublisher, ZMQConfig


def run(hz: float, duration: float) -> None:
    config = ZMQConfig(telemetry_pub_endpoint="tcp://127.0.0.1:5555")
    publisher = TelemetryPublisher(config=config)
    publisher.start()

    interval = 1.0 / hz
    i = 0
    start = time.time()
    print(f"Publisher attivo su tcp://127.0.0.1:5555 ({hz:.0f} Hz)")
    print("Nella GUI seleziona: Telemetria -> ZeroMQ (Simulatore)")
    print("Ctrl+C per fermare\n")

    try:
        while True:
            t = i * interval
            telemetry = TelemetryData(
                airspeed=50.0 + 20.0 * math.sin(t * 0.5),
                altitude=1000.0 + 500.0 * math.sin(t * 0.2),
                vertical_speed=2.0 * math.sin(t * 0.3),
                heading=(t * 10.0) % 360.0,
                pitch=5.0 * math.sin(t * 0.4),
                roll=10.0 * math.sin(t * 0.6),
                turn_rate=2.0 * math.sin(t * 0.5),
                rpm=2500.0 + 500.0 * math.sin(t * 0.3),
                oil_temp=80.0 + 10.0 * math.sin(t * 0.1),
                manifold_pressure=101.3 + 5.0 * math.sin(t * 0.2),
                fuel_flow=0.001 + 0.0005 * math.sin(t * 0.4),
            )
            publisher.publish(telemetry)
            i += 1

            if i % int(hz) == 0:
                print(f"  #{i:6d}  spd={telemetry.airspeed:6.1f} m/s  "
                      f"alt={telemetry.altitude:8.1f} m  hdg={telemetry.heading:5.1f} deg")

            if duration > 0 and (time.time() - start) >= duration:
                break
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nInterrotto dall'utente")
    finally:
        publisher.stop()
        print(f"Publisher fermato. Messaggi inviati: {publisher.message_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publisher telemetria di test")
    parser.add_argument("--hz", type=float, default=30.0, help="Frequenza di invio")
    parser.add_argument("--duration", type=float, default=0.0, help="Durata in secondi (0 = infinito)")
    args = parser.parse_args()
    run(args.hz, args.duration)