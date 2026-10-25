"""
gcs_ui/sim_ui/core/telemetry.py

Telemetria e adapter per il simulatore.
Usa il contratto dati condiviso di ipc_bus quando disponibile.
"""

import math
from dataclasses import dataclass
from typing import Dict, Any, Optional, Union

from PySide6.QtCore import QObject, Signal, QTimer


# ============================================================================
# CONTRATTO DATI — usa ipc_bus se disponibile, altrimenti fallback locale
# ============================================================================
try:
    from ipc_bus import TelemetryData
except ImportError:
    @dataclass
    class TelemetryData:
        """Contratto dati telemetria — Sistema Internazionale (SI)."""
        airspeed: float = 0.0
        altitude: float = 0.0
        vertical_speed: float = 0.0
        heading: float = 0.0
        pitch: float = 0.0
        roll: float = 0.0
        turn_rate: float = 0.0
        rpm: float = 0.0
        oil_temp: float = 0.0
        manifold_pressure: float = 0.0
        fuel_flow: float = 0.0
        pos_north: float = 0.0
        pos_east: float = 0.0
        pos_down: float = 0.0


# ============================================================================
# CLASSE BASE — tutti gli adapter ereditano da qui
# ============================================================================
class TelemetryAdapter(QObject):
    """
    Classe base per tutti gli adapter telemetria.
    Fornisce: segnale telemetry_updated, start(), stop().
    """
    telemetry_updated = Signal(object)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._running = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


# ============================================================================
# MOCK ADAPTER — genera dati sinusoidali per test
# ============================================================================
class MockTelemetryAdapter(TelemetryAdapter):
    """
    Adapter mock con dati sinusoidali.
    Ha un QTimer interno che genera dati a frequenza regolare.
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._interval_ms = 50  # default 20 Hz
        self._time = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def set_interval(self, ms: int):
        """Imposta l'intervallo tra un tick e l'altro in millisecondi."""
        self._interval_ms = max(1, ms)
        if self._running:
            self._timer.setInterval(self._interval_ms)

    def start(self):
        super().start()
        self._timer.start(self._interval_ms)

    def stop(self):
        super().stop()
        self._timer.stop()

    def _tick(self):
        dt = self._interval_ms / 1000.0
        self._time += dt
        t = self._time

        data = TelemetryData(
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
        self.telemetry_updated.emit(data)


# ============================================================================
# EXTERNAL ADAPTER — riceve dati da backend esterno
# ============================================================================
class ExternalTelemetryAdapter(TelemetryAdapter):
    """
    Adapter per telemetria esterna (backend/simulatore).
    THREAD-SAFE: push_data() può essere chiamato da qualsiasi thread.
    L'emissione del segnale viene schedulata nel main thread Qt.
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._last_data: Optional[TelemetryData] = None

    def push_data(self, data: Union[TelemetryData, Dict[str, Any]]):
        """Riceve dati dal backend e schedula l'emissione nel main thread."""
        if not self._running:
            return
        if isinstance(data, dict):
            data = TelemetryData(**data)
        self._last_data = data
        # Emetti nel main thread Qt (thread-safe)
        QTimer.singleShot(0, lambda: self.telemetry_updated.emit(data))

    def get_last_data(self) -> Optional[TelemetryData]:
        return self._last_data