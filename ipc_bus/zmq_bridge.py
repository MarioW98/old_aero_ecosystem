"""
ZeroMQ Bridge - Wrapper per comunicazione IPC nell'ecosistema aerospaziale.

Posizione: ipc_bus/zmq_bridge.py

Questo modulo fornisce:
- TelemetryPublisher: pubblica telemetria (usato dal simulatore)
- TelemetrySubscriber: riceve telemetria in thread separato (usato dalla GCS)
- ControlPublisher: pubblica comandi (usato dalla GCS)
- ControlSubscriber: riceve comandi (usato dal FC/simulatore)

Pattern: PUB/SUB per telemetria (uno-a-molti, non bloccante)
"""

import zmq
import threading
import logging
import time
import errno
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

from .telemetry_protocol import (
    TelemetryData,
    ControlCommand,
    Topics
)


# Configurazione logging
logger = logging.getLogger(__name__)


@dataclass
class ZMQConfig:
    """Configurazione per connessioni ZeroMQ."""
    # Publisher (bind)
    telemetry_pub_endpoint: str = "tcp://127.0.0.1:5555"
    controls_pub_endpoint: str = "tcp://127.0.0.1:5556"
    
    # Subscriber (connect)
    telemetry_sub_endpoint: str = "tcp://127.0.0.1:5555"
    controls_sub_endpoint: str = "tcp://127.0.0.1:5556"
    
    # Timeout
    poll_timeout_ms: int = 100  # 100ms per subscriber loop
    reconnect_interval_ms: int = 1000


class BaseZMQClient:
    """
    Classe base per client ZeroMQ.
    
    Gestisce:
    - Creazione e distruzione del context
    - Logging strutturato
    - Cleanup risorse
    """
    
    def __init__(self, name: str):
        self.name = name
        self.context: Optional[zmq.Context] = None
        self.socket: Optional[zmq.Socket] = None
        self._running = False
        logger.info(f"[{self.name}] Inizializzazione client ZMQ")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
    
    def start(self):
        """Avvia il client."""
        if self.context is None:
            self.context = zmq.Context()
            logger.debug(f"[{self.name}] Context ZMQ creato")
        self._running = True
    
    def stop(self):
        """Ferma il client e rilascia le risorse in sicurezza."""
        self._running = False  # ← DEVE essere la prima cosa!
        
        if self.socket:
            try:
                self.socket.close(linger=0)
            except zmq.ZMQError:
                pass
            self.socket = None
            logger.debug(f"[{self.name}] Socket ZMQ chiuso")
            
        if self.context:
            try:
                self.context.term()
            except zmq.ZMQError:
                pass
            self.context = None
            logger.info(f"[{self.name}] Client ZMQ fermato")


class TelemetryPublisher(BaseZMQClient):
    """
    Publisher per telemetria (usato dal simulatore).
    
    Pubblica TelemetryData su topic specifici in formato MessagePack.
    Pattern: PUB (bind) → SUB (connect)
    
    Esempio d'uso:
        with TelemetryPublisher() as pub:
            telemetry = TelemetryData(airspeed=100.0, altitude=3000.0)
            pub.publish(telemetry)
    """
    
    def __init__(self, config: Optional[ZMQConfig] = None):
        super().__init__("TelemetryPublisher")
        self.config = config or ZMQConfig()
        self.socket: Optional[zmq.Socket] = None
        self._message_count = 0
    
    def start(self):
        """Avvia il publisher e fa il bind dell'endpoint."""
        super().start()
        if self.socket is None:
            self.socket = self.context.socket(zmq.PUB)
            # Opzioni socket per alte performance
            self.socket.setsockopt(zmq.SNDHWM, 1000)  # High Water Mark
            self.socket.setsockopt(zmq.LINGER, 0)
            # Bind all'endpoint
            self.socket.bind(self.config.telemetry_pub_endpoint)
            logger.info(
                f"[{self.name}] Bind a {self.config.telemetry_pub_endpoint}"
            )
            # Piccola pausa per permettere ai subscriber di connettersi
            time.sleep(0.1)
    
    def publish(self, data: TelemetryData, topic: str = Topics.TELEMETRY) -> bool:
        """
        Pubblica un messaggio di telemetria.
        
        Args:
            data: TelemetryData da pubblicare
            topic: Topic ZeroMQ (default: Topics.TELEMETRY)
        
        Returns:
            True se pubblicato con successo, False altrimenti
        """
        if not self._running or not self.socket:
            logger.warning(f"[{self.name}] Publisher non attivo")
            return False
        
        try:
            # Serializza in MessagePack
            payload = data.to_bytes()
            # Invia come multipart: [topic, payload]
            self.socket.send_multipart([
                topic.encode('utf-8'),
                payload
            ], flags=zmq.NOBLOCK)
            self._message_count += 1
            
            # Log ogni 1000 messaggi
            if self._message_count % 1000 == 0:
                logger.debug(
                    f"[{self.name}] Pubblicati {self._message_count} messaggi"
                )
            return True
            
        except zmq.Again:
            # Buffer pieno, messaggio scartato (tipico con PUB/SUB)
            logger.warning(f"[{self.name}] Buffer pieno, messaggio scartato")
            return False
        except Exception as e:
            logger.error(f"[{self.name}] Errore pubblicazione: {e}")
            return False
    
    @property
    def message_count(self) -> int:
        """Numero di messaggi pubblicati."""
        return self._message_count


class TelemetrySubscriber(BaseZMQClient):
    """
    Subscriber per telemetria (usato dalla GCS).
    
    Riceve TelemetryData in un thread separato e invoca una callback.
    Pattern: PUB (bind) → SUB (connect)
    
    Esempio d'uso:
        def on_telemetry(data: TelemetryData):
            print(f"Velocità: {data.airspeed}")
        
        with TelemetrySubscriber(callback=on_telemetry) as sub:
            # Il subscriber gira in background
            time.sleep(10)  # Ricevi dati per 10 secondi
    """
    
    def __init__(
        self,
        callback: Callable[[TelemetryData], None],
        config: Optional[ZMQConfig] = None,
        topics: Optional[list[str]] = None
    ):
        """
        Args:
            callback: Funzione chiamata quando arriva telemetria
            config: Configurazione ZMQ
            topics: Lista di topic a cui sottoscriversi (default: tutti)
        """
        super().__init__("TelemetrySubscriber")
        self.config = config or ZMQConfig()
        self.callback = callback
        self.topics = topics or [Topics.TELEMETRY]
        
        self.socket: Optional[zmq.Socket] = None
        self._thread: Optional[threading.Thread] = None
        self._message_count = 0
        self._last_message: Optional[TelemetryData] = None
    
    def start(self):
        """Avvia il subscriber e il thread di ricezione."""
        super().start()
        
        if self.socket is None:
            self.socket = self.context.socket(zmq.SUB)
            # Opzioni socket
            self.socket.setsockopt(zmq.RCVHWM, 1000)
            self.socket.setsockopt(zmq.LINGER, 0)
            
            # Connetti all'endpoint
            self.socket.connect(self.config.telemetry_sub_endpoint)
            logger.info(
                f"[{self.name}] Connesso a {self.config.telemetry_sub_endpoint}"
            )
            
            # Sottoscrivi ai topic
            for topic in self.topics:
                self.socket.setsockopt_string(zmq.SUBSCRIBE, topic)
                logger.debug(f"[{self.name}] Sottoscritto a topic: {topic}")
        
        # Avvia thread di ricezione
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._receive_loop,
                name="ZMQ-Subscriber-Thread",
                daemon=True
            )
            self._thread.start()
            logger.info(f"[{self.name}] Thread ricezione avviato")
    
    def stop(self):
        """Ferma il thread di ricezione e il socket."""
        self._running = False  # ← Segnale al thread di uscire
        
        # Aspetta che il thread esca dal loop di poll()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info(f"[{self.name}] Thread ricezione fermato")
            
        # Ora chiudi socket e context (ereditato da BaseZMQClient)
        super().stop()
    
    def _receive_loop(self):
        """Loop di ricezione messaggi (gira in thread separato)."""
        logger.debug(f"[{self.name}] Loop ricezione avviato")
        
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        
        while self._running:
            try:
                # Poll con timeout per permettere check di _running
                socks = dict(poller.poll(timeout=self.config.poll_timeout_ms))
                
                if self.socket in socks and socks[self.socket] == zmq.POLLIN:
                    # Ricevi messaggio multipart: [topic, payload]
                    frames = self.socket.recv_multipart(flags=zmq.NOBLOCK)
                    
                    if len(frames) >= 2:
                        topic = frames[0].decode('utf-8')
                        payload = frames[1]
                        
                        # Deserializza in TelemetryData
                        try:
                            telemetry = TelemetryData.from_bytes(payload)
                            self._last_message = telemetry
                            self._message_count += 1
                            
                            # Invoca callback (thread-safe se usa Qt signals)
                            self.callback(telemetry)
                            
                            # Log ogni 1000 messaggi
                            if self._message_count % 1000 == 0:
                                logger.debug(
                                    f"[{self.name}] Ricevuti {self._message_count} "
                                    f"messaggi (ultimo: {telemetry.age_ms():.1f}ms fa)"
                                )
                        
                        except Exception as e:
                            logger.error(
                                f"[{self.name}] Errore deserializzazione: {e}"
                            )
            
            except zmq.Again:
                # Timeout poll, continua loop
                continue
            except zmq.ZMQError as e:
                # Se il socket è stato chiuso o il context terminato, esci dal loop
                if not self._running or e.errno in (errno.ENOTSOCK, zmq.ETERM, zmq.ENOTSOCK):
                    break
                logger.error(f"[{self.name}] Errore ZMQ: {e}")
                time.sleep(0.1)
            except Exception as e:
                if not self._running:
                    break
                logger.error(f"[{self.name}] Errore inaspettato: {e}")
                time.sleep(0.1)
    
    @property
    def message_count(self) -> int:
        """Numero di messaggi ricevuti."""
        return self._message_count
    
    @property
    def last_message(self) -> Optional[TelemetryData]:
        """Ultimo messaggio ricevuto."""
        return self._last_message


class ControlPublisher(BaseZMQClient):
    """
    Publisher per comandi (usato dalla GCS).
    
    Pubblica ControlCommand per inviare input del pilota.
    
    Esempio d'uso:
        with ControlPublisher() as pub:
            cmd = ControlCommand(throttle=0.8, roll_stick=0.1)
            pub.publish(cmd)
    """
    
    def __init__(self, config: Optional[ZMQConfig] = None):
        super().__init__("ControlPublisher")
        self.config = config or ZMQConfig()
    
    def start(self):
        """Avvia il publisher."""
        super().start()
        if self.socket is None:
            self.socket = self.context.socket(zmq.PUB)
            self.socket.setsockopt(zmq.SNDHWM, 100)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.bind(self.config.controls_pub_endpoint)
            logger.info(
                f"[{self.name}] Bind a {self.config.controls_pub_endpoint}"
            )
            time.sleep(0.1)
    
    def publish(self, data: ControlCommand, topic: str = Topics.CONTROLS) -> bool:
        """Pubblica un comando di controllo."""
        if not self._running or not self.socket:
            return False
        
        try:
            payload = data.to_bytes()
            self.socket.send_multipart([
                topic.encode('utf-8'),
                payload
            ], flags=zmq.NOBLOCK)
            return True
        except Exception as e:
            logger.error(f"[{self.name}] Errore pubblicazione comando: {e}")
            return False


# ============================================================================
# INTEGRAZIONE CON PySide6 (Qt)
# ============================================================================

def create_qt_subscriber(
    signal_emitter,
    signal_name: str = "telemetry_received",
    config: Optional[ZMQConfig] = None
) -> TelemetrySubscriber:
    """
    Crea un TelemetrySubscriber che emette un segnale Qt.
    
    Questo è il bridge perfetto per integrare ZeroMQ con PySide6.
    Il subscriber gira in un thread separato, ma il segnale Qt
    viene emesso nel main thread (grazie a Qt signal/slot mechanism).
    
    Esempio d'uso in MainWindow:
        class MainWindow(QMainWindow):
            telemetry_received = Signal(object)  # Signal(object) per TelemetryData
            
            def __init__(self):
                super().__init__()
                # Connetti segnale a slot
                self.telemetry_received.connect(self.on_telemetry)
                
                # Crea subscriber Qt
                self.subscriber = create_qt_subscriber(
                    signal_emitter=self,
                    signal_name="telemetry_received"
                )
                self.subscriber.start()
            
            @Slot(object)
            def on_telemetry(self, data):
                # Questo è chiamato nel main thread Qt
                self.adapter.push_data(data)
    
    Args:
        signal_emitter: Oggetto Qt che ha il segnale (es. MainWindow)
        signal_name: Nome del segnale Qt da emettere
        config: Configurazione ZMQ
    
    Returns:
        TelemetrySubscriber configurato
    """
    def emit_signal(data: TelemetryData):
        """Callback che emette il segnale Qt."""
        # getattr per ottenere il segnale dall'emitter
        signal = getattr(signal_emitter, signal_name, None)
        if signal:
            # emit() è thread-safe in Qt (usa event loop del main thread)
            signal.emit(data)
    
    return TelemetrySubscriber(
        callback=emit_signal,
        config=config,
        topics=[Topics.TELEMETRY]
    )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def test_publisher_subscriber(duration: int = 5):
    """
    Test standalone per verificare publisher e subscriber.
    
    Esegui con: python -m ipc_bus.zmq_bridge
    """
    import sys
    
    print(f"Test ZMQ Bridge - Durata: {duration}s")
    print("=" * 60)
    
    # Counter per callback
    received_count = [0]
    
    def on_receive(data: TelemetryData):
        received_count[0] += 1
        if received_count[0] % 10 == 0:
            print(f"Ricevuto #{received_count[0]}: "
                  f"speed={data.airspeed:.1f}m/s, alt={data.altitude:.1f}m")
    
    # Avvia subscriber
    subscriber = TelemetrySubscriber(callback=on_receive)
    subscriber.start()
    
    # Attendi connessione
    time.sleep(0.5)
    
    # Avvia publisher
    publisher = TelemetryPublisher()
    publisher.start()
    
    # Pubblica dati di test
    print("Pubblicazione telemetria...")
    start_time = time.time()
    i = 0
    
    try:
        while time.time() - start_time < duration:
            telemetry = TelemetryData(
                airspeed=50.0 + i * 0.1,
                altitude=1000.0 + i * 10,
                vertical_speed=2.0,
                heading=90.0,
                pitch=5.0,
                roll=0.0,
                rpm=2500.0
            )
            publisher.publish(telemetry)
            i += 1
            time.sleep(0.02)  # 50 Hz
    except KeyboardInterrupt:
        print("\nInterrotto dall'utente")
    
    # Cleanup
    publisher.stop()
    subscriber.stop()
    
    print("=" * 60)
    print(f"Pubblicati: {publisher.message_count}")
    print(f"Ricevuti: {subscriber.message_count}")
    print(f"Loss rate: {100 * (1 - received_count[0] / max(1, i)):.1f}%")


class ControlSubscriber(BaseZMQClient):
    """
    Subscriber per comandi (usato dal simulatore/FC).
    Riceve ControlCommand in un thread separato e invoca una callback.

    Esempio d'uso:
        def on_control(cmd: ControlCommand):
            print(f"Throttle: {cmd.throttle}")

        with ControlSubscriber(callback=on_control) as sub:
            time.sleep(10)
    """

    def __init__(
        self,
        callback: Callable[[ControlCommand], None],
        config: Optional[ZMQConfig] = None,
        topics: Optional[list[str]] = None
    ):
        super().__init__("ControlSubscriber")
        self.config = config or ZMQConfig()
        self.callback = callback
        self.topics = topics or [Topics.CONTROLS]
        self.socket: Optional[zmq.Socket] = None
        self._thread: Optional[threading.Thread] = None
        self._message_count = 0
        self._last_message: Optional[ControlCommand] = None

    def start(self):
        """Avvia il subscriber e il thread di ricezione."""
        super().start()
        if self.socket is None:
            self.socket = self.context.socket(zmq.SUB)
            self.socket.setsockopt(zmq.RCVHWM, 100)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.connect(self.config.controls_sub_endpoint)
            logger.info(
                f"[{self.name}] Connesso a {self.config.controls_sub_endpoint}"
            )
            for topic in self.topics:
                self.socket.setsockopt_string(zmq.SUBSCRIBE, topic)
                logger.debug(f"[{self.name}] Sottoscritto a topic: {topic}")

        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._receive_loop,
                name="ZMQ-ControlSubscriber-Thread",
                daemon=True
            )
            self._thread.start()
            logger.info(f"[{self.name}] Thread ricezione avviato")

    def stop(self):
        """Ferma il thread di ricezione e il socket."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info(f"[{self.name}] Thread ricezione fermato")
        super().stop()

    def _receive_loop(self):
        """Loop di ricezione comandi (thread separato)."""
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        while self._running:
            try:
                socks = dict(poller.poll(timeout=self.config.poll_timeout_ms))
                if self.socket in socks and socks[self.socket] == zmq.POLLIN:
                    frames = self.socket.recv_multipart(flags=zmq.NOBLOCK)
                    if len(frames) >= 2:
                        payload = frames[1]
                        try:
                            cmd = ControlCommand.from_bytes(payload)
                            self._last_message = cmd
                            self._message_count += 1
                            self.callback(cmd)
                        except Exception as e:
                            logger.error(
                                f"[{self.name}] Errore deserializzazione: {e}"
                            )
            except zmq.Again:
                continue
            except zmq.ZMQError as e:
                if not self._running or e.errno in (errno.ENOTSOCK, zmq.ETERM):
                    break
                logger.error(f"[{self.name}] Errore ZMQ: {e}")
                time.sleep(0.1)
            except Exception as e:
                if not self._running:
                    break
                logger.error(f"[{self.name}] Errore inaspettato: {e}")
                time.sleep(0.1)

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def last_message(self) -> Optional[ControlCommand]:
        return self._last_message
    


if __name__ == "__main__":
    # Test standalone
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    test_publisher_subscriber(duration=5)