"""
ipc_bus/trajectory_adapter.py

Adapter Qt che pilota un TrajectoryGenerator e pubblica TelemetryData
a frequenza regolare. Riutilizzabile da qualsiasi applicazione Qt.

Espone la stessa interfaccia degli altri adapter telemetria
(telemetry_updated, start, stop, set_interval), quindi si integra
con il meccanismo di selezione sorgente della GCS tramite duck-typing.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer

from .trajectory import TrajectoryGenerator


class TrajectoryTelemetryAdapter(QObject):
    """
    Sorgente di telemetria basata su una traiettoria coerente.

    Ad ogni tick del timer campiona la traiettoria al tempo corrente
    ed emette il TelemetryData risultante. Il tempo avanza in modo
    coerente con l'intervallo, quindi la traiettoria è fluida.
    """

    telemetry_updated = Signal(object)

    def __init__(
        self,
        trajectory: TrajectoryGenerator,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._trajectory = trajectory
        self._interval_ms = 50          # default 20 Hz
        self._t = 0.0
        self._running = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Configurazione
    # ------------------------------------------------------------------
    def set_trajectory(self, trajectory: TrajectoryGenerator) -> None:
        """Cambia traiettoria e riparte da t=0."""
        self._trajectory = trajectory
        self._t = 0.0

    def set_interval(self, ms: int) -> None:
        """Imposta l'intervallo tra un campione e l'altro (millisecondi)."""
        self._interval_ms = max(1, ms)
        if self._running:
            self._timer.setInterval(self._interval_ms)

    # ------------------------------------------------------------------
    # Ciclo di vita (stessa interfaccia degli altri adapter)
    # ------------------------------------------------------------------
    def start(self) -> None:
        self._running = True
        self._timer.start(self._interval_ms)

    def stop(self) -> None:
        self._running = False
        self._timer.stop()

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Tick interno
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        data = self._trajectory.sample(self._t)
        self._t += self._interval_ms / 1000.0
        self.telemetry_updated.emit(data)