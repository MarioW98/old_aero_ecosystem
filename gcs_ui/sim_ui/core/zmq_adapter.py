"""
gcs_ui/sim_ui/core/zmq_adapter.py
"""

import logging
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal, Slot

try:
    from ipc_bus import (
        TelemetryData,
        ZMQConfig,
        TelemetrySubscriber,
        Topics
    )
    IPC_AVAILABLE = True
except ImportError:
    IPC_AVAILABLE = False

logger = logging.getLogger(__name__)


class ZMQTelemetryAdapter(QObject):
    """
    Riceve telemetria via ZeroMQ in un thread separato
    e la consegna nel main thread Qt tramite segnale.
    """

    # Segnale emesso nel main thread Qt quando arriva telemetria
    telemetry_received = Signal(object)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        endpoint: str = "tcp://127.0.0.1:5555",
        auto_start: bool = False
    ):
        super().__init__(parent)
        self._endpoint = endpoint
        self._subscriber: Optional[TelemetrySubscriber] = None
        self._running = False
        self._external_callback: Optional[Callable] = None

        # Connetti segnale a slot interno (cross-thread automatico)
        self.telemetry_received.connect(self._deliver_to_callback)

        if auto_start:
            self.start()

    def set_external_callback(self, callback: Callable):
        """
        Imposta la callback per consegnare i dati.
        Tipicamente: MainWindow._on_telemetry
        """
        self._external_callback = callback

    def start(self):
        if not IPC_AVAILABLE:
            logger.warning("ipc_bus non disponibile, ZMQ disabilitato")
            return
        if self._running:
            return

        # Crea il subscriber solo la prima volta, poi riutilizzalo
        if self._subscriber is None:
            config = ZMQConfig(telemetry_sub_endpoint=self._endpoint)
            self._subscriber = TelemetrySubscriber(
                callback=self._emit_signal,
                config=config,
                topics=[Topics.TELEMETRY]
            )
        
        self._subscriber.start()
        self._running = True
        logger.info(f"ZMQ Subscriber avviato su {self._endpoint}")

    def stop(self):
        if self._subscriber and self._running:
            self._subscriber.stop()
            self._running = False
            logger.info("ZMQ Subscriber fermato")

    def _emit_signal(self, data):
        """Chiamato dal thread ZMQ. Emette segnale Qt (thread-safe)."""
        self.telemetry_received.emit(data)

    @Slot(object)
    def _deliver_to_callback(self, data):
        """Chiamato nel main thread Qt. Consegna i dati alla callback."""
        if self._external_callback:
            self._external_callback(data)

    @property
    def is_running(self) -> bool:
        return self._running