"""
test_zmq_integration.py — Test integrazione ZMQ con la GUI.

Posizione: MODULAR-UI-V0.3/test_zmq_integration.py (root del progetto)

Uso:
    # Terminale 1: Avvia la GUI
    python -m sim_ui

    # Terminale 2: Avvia il publisher di test
    python test_zmq_integration.py

    # Nella GUI: Menu → Telemetria → ZeroMQ (Simulatore)
"""

import sys
import time
import logging
import argparse

# Assicurati che ipc_bus sia trovabile
sys.path.insert(0, '.')

from ipc_bus import TelemetryData, TelemetryPublisher, ZMQConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestPublisher")


def run_publisher(duration: float = 0, hz: float = 20.0):
    """
    Pubblica telemetria di test su ZeroMQ.

    Args:
        duration: Durata in secondi (0 = infinito, Ctrl+C per fermare)
        hz: Frequenza di pubblicazione
    """
    config = ZMQConfig(telemetry_pub_endpoint="tcp://127.0.0.1:5555")
    publisher = TelemetryPublisher(config=config)
    publisher.start()

    interval = 1.0 / hz
    i = 0
    start = time.time()

    logger.info(f"Publisher avviato su tcp://127.0.0.1:5555 ({hz} Hz)")
    logger.info("Nella GUI: Telemetria → ZeroMQ (Simulatore)")
    logger.info("Ctrl+C per fermare\n")

    try:
        while True:
            import math
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
                elapsed = time.time() - start
                logger.info(
                    f"  #{i:5d} | "
                    f"spd={telemetry.airspeed:6.1f} m/s | "
                    f"alt={telemetry.altitude:7.1f} m | "
                    f"hdg={telemetry.heading:5.1f}° | "
                    f"rpm={telemetry.rpm:6.0f} | "
                    f"{elapsed:.0f}s"
                )

            if duration > 0 and (time.time() - start) >= duration:
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("\nInterrotto dall'utente")
    finally:
        publisher.stop()
        logger.info(f"Publisher fermato. Totale messaggi: {publisher.message_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test ZMQ Publisher")
    parser.add_argument("--duration", type=float, default=0,
                        help="Durata in secondi (0 = infinito)")
    parser.add_argument("--hz", type=float, default=20.0,
                        help="Frequenza di pubblicazione")
    args = parser.parse_args()

    run_publisher(duration=args.duration, hz=args.hz)