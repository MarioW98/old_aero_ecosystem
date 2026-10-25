"""
tools/test_ipc_pipeline.py

Verifica la pipeline IPC (publisher -> subscriber) SENZA GUI.
Usa due thread nello stesso processo: uno pubblica, uno riceve.

Uso:
    cd aerospace-ecosystem
    python3 tools/test_ipc_pipeline.py
"""

import sys
import time
import threading
from pathlib import Path

# Rende importabile ipc_bus dalla root del progetto
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ipc_bus import TelemetryData, TelemetryPublisher, TelemetrySubscriber, ZMQConfig, Topics


def run_pipeline_test(duration: float = 5.0, hz: float = 30.0) -> bool:
    received: list[TelemetryData] = []
    lock = threading.Lock()

    def on_receive(data: TelemetryData):
        with lock:
            received.append(data)

    config = ZMQConfig(
        telemetry_pub_endpoint="tcp://127.0.0.1:5555",
        telemetry_sub_endpoint="tcp://127.0.0.1:5555",
    )

    subscriber = TelemetrySubscriber(callback=on_receive, config=config, topics=[Topics.TELEMETRY])
    publisher = TelemetryPublisher(config=config)

    subscriber.start()
    publisher.start()

    # ZeroMQ PUB/SUB ha il "slow joiner problem": il subscriber deve
    # essere connesso prima che il publisher inizi a inviare.
    time.sleep(0.5)

    interval = 1.0 / hz
    sent = 0
    start = time.time()
    try:
        while time.time() - start < duration:
            telemetry = TelemetryData(
                airspeed=50.0 + sent * 0.1,
                altitude=1000.0 + sent,
                vertical_speed=2.0,
                heading=(sent * 3.0) % 360.0,
                pitch=5.0,
                roll=0.0,
                turn_rate=1.0,
                rpm=2500.0,
                oil_temp=80.0,
                manifold_pressure=101.3,
                fuel_flow=0.001,
            )
            if publisher.publish(telemetry):
                sent += 1
            time.sleep(interval)
    finally:
        time.sleep(0.3)  # lascia il tempo di svuotare il buffer
        publisher.stop()
        subscriber.stop()

    received_count = len(received)
    print("=" * 60)
    print(f"Inviati:   {sent}")
    print(f"Ricevuti:  {received_count}")
    loss = 100.0 * (1 - received_count / sent) if sent else 0.0
    print(f"Loss rate: {loss:.1f}%")

    if received:
        last = received[-1]
        print(f"Ultimo pacchetto: airspeed={last.airspeed:.1f} m/s, "
              f"altitude={last.altitude:.1f} m, heading={last.heading:.1f} deg")

    ok = received_count > 0 and loss < 10.0
    print("RISULTATO:", "PASS" if ok else "FAIL")
    print("=" * 60)
    return ok


if __name__ == "__main__":
    success = run_pipeline_test(duration=5.0, hz=30.0)
    sys.exit(0 if success else 1)