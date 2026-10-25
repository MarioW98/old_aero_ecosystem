"""
simulator/zmq_publisher.py

Publisher ZeroMQ per la telemetria del SimEngine.

Converte la telemetria del SimEngine in TelemetryData (contratto ipc_bus)
e la pubblica su un endpoint ZMQ PUB. La GUI si sottoscrive con
Telemetria → ZeroMQ (Simulatore).

D3.3: ponte tra SimEngine e GCS.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Aggiungi la directory padre a sys.path per importare ipc_bus
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from ipc_bus import TelemetryData, TelemetryPublisher, ZMQConfig
    IPC_AVAILABLE = True
except ImportError as e:
    IPC_AVAILABLE = False
    print(f"AVVISO: ipc_bus non importabile ({e}). Il publisher ZMQ non funzionerà.")


class SimTelemetryPublisher:
    """
    Publisher per la telemetria del SimEngine.

    Converte il dict di telemetria del SimEngine in TelemetryData
    e pubblica su ZMQ.

    Uso:
        pub = SimTelemetryPublisher(endpoint="tcp://*:5555")
        pub.publish_telemetry(sim_engine.get_telemetry())
        pub.stop()
    """

    def __init__(self, endpoint: str = "tcp://127.0.0.1:5555"):
        """
        Args:
            endpoint: endpoint ZMQ PUB (default: tcp://127.0.0.1:5555).
        """
        if not IPC_AVAILABLE:
            raise ImportError("ipc_bus non disponibile")

        # Crea la configurazione con l'endpoint specificato
        config = ZMQConfig(telemetry_pub_endpoint=endpoint)
        
        # Crea il publisher con la configurazione
        self._publisher = TelemetryPublisher(config)
        self._endpoint = endpoint

        # Attiva il publisher (start fa il bind)
        self._publisher.start()

    def publish_telemetry(self, telemetry: dict):
        """
        Converte la telemetria del SimEngine in TelemetryData e pubblica.

        Args:
            telemetry: dict restituito da SimEngine.get_telemetry().
        """
        # Calcola campi derivati non direttamente disponibili
        vertical_speed = telemetry.get('vertical_speed', 0.0)
        turn_rate = telemetry.get('turn_rate', 0.0)

        # Mappa i campi della telemetria SimEngine a TelemetryData
        data = TelemetryData(
            airspeed=telemetry.get('airspeed', 0.0),
            altitude=telemetry.get('altitude', 0.0),
            vertical_speed=vertical_speed,
            heading=telemetry.get('heading', 0.0),
            pitch=telemetry.get('pitch', 0.0),
            roll=telemetry.get('roll', 0.0),
            turn_rate=turn_rate,
            rpm=telemetry.get('rpm', 0.0),
            oil_temp=telemetry.get('oil_temp', 80.0),
            manifold_pressure=telemetry.get('manifold_pressure', 101.3),
            fuel_flow=telemetry.get('fuel_flow', 0.001),
            pos_north=telemetry.get('pos_north', 0.0),
            pos_east=telemetry.get('pos_east', 0.0),
            pos_down=telemetry.get('pos_down', 0.0),
        )

        self._publisher.publish(data)

    def stop(self):
        """Ferma il publisher ZMQ."""
        self._publisher.stop()

    # Alias per compatibilità
    def close(self):
        """Alias di stop() per retrocompatibilità."""
        self.stop()

    @property
    def endpoint(self) -> str:
        return self._endpoint