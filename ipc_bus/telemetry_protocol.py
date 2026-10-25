"""
Telemetry Protocol - Contratto dati per IPC nell'ecosistema aerospaziale.

Posizione: ipc_bus/telemetry_protocol.py

Questo modulo definisce il contratto dati che tutti i componenti (Simulatore, GCS, 
Flight Controller, CFD) devono rispettare per comunicare via ZeroMQ.

Regola fondamentale: aggiunte di campi solo additive (mai rinomine senza accordo).
"""

import msgpack
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any
import time


@dataclass
class TelemetryData:
    """
    Contratto dati telemetria - Sistema Internazionale (SI).
    
    Questo è il contratto tra simulatore e interfaccia.
    Tutti i valori sono in unità SI per coerenza interna.
    La conversione alle unità di visualizzazione (nodi, piedi, ecc.) 
    è gestita a livello di UI (UnitButtonsMixin).
    """
    
    # Meta-dati
    schema_version: int = 1
    timestamp: float = field(default_factory=time.time)
    
    # Parametri di volo (SI)
    airspeed: float = 0.0           # m/s
    altitude: float = 0.0           # m
    vertical_speed: float = 0.0     # m/s
    heading: float = 0.0            # gradi (0-360)
    pitch: float = 0.0              # gradi
    roll: float = 0.0               # gradi
    turn_rate: float = 0.0          # gradi/s
    
    # Parametri motore (SI quando possibile)
    rpm: float = 0.0                # giri/min
    oil_temp: float = 0.0           # °C
    manifold_pressure: float = 0.0  # kPa
    fuel_flow: float = 0.0          # kg/s

    # NED position (metri)
    pos_north:  float = 0.0
    pos_east:   float = 0.0
    pos_down:   float = 0.0
    
    def to_bytes(self) -> bytes:
        """
        Serializza il dataclass in bytes usando MessagePack.
        
        MessagePack è 3-5x più veloce di JSON per dati numerici
        e produce payload più piccoli (importante per alte frequenze).
        """
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'TelemetryData':
        """
        Deserializza bytes in TelemetryData.
        
        Usa **unpacked per permettere campi mancanti (backward compatibility).
        Se un vecchio ricevitore legge un messaggio con nuovi campi,
        i campi mancanti useranno i valori di default.
        """
        unpacked = msgpack.unpackb(data, raw=False)
        return cls(**unpacked)
    
    def update_timestamp(self) -> None:
        """Aggiorna il timestamp all'istante corrente."""
        self.timestamp = time.time()
    
    def age_ms(self) -> float:
        """Ritorna l'età del messaggio in millisecondi."""
        return (time.time() - self.timestamp) * 1000


@dataclass
class ControlCommand:
    """
    Comando di controllo dall'utente al Flight Controller/Simulatore.
    
    Usato per inviare input del pilota (stick, throttle, switch) 
    dalla GCS al simulatore o al flight controller reale.
    """
    
    schema_version: int = 1
    timestamp: float = field(default_factory=time.time)
    
    # Controlli di volo (normalizzati -1.0 a +1.0, tranne throttle 0.0 a 1.0)
    throttle: float = 0.0           # 0.0 a 1.0
    roll_stick: float = 0.0         # -1.0 a +1.0
    pitch_stick: float = 0.0        # -1.0 a +1.0
    yaw_stick: float = 0.0          # -1.0 a +1.0
    
    # Switch e modalità
    arm_disarm: bool = False        # True = ARM, False = DISARM
    flight_mode: int = 0            # 0=MANUAL, 1=STABILIZE, 2=AUTO, ecc.
    
    # Input custom (estendibile)
    custom_inputs: Dict[str, float] = field(default_factory=dict)
    
    def to_bytes(self) -> bytes:
        """Serializza in MessagePack."""
        return msgpack.packb(asdict(self), use_bin_type=True)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'ControlCommand':
        """Deserializza da MessagePack."""
        unpacked = msgpack.unpackb(data, raw=False)
        return cls(**unpacked)
    
    def update_timestamp(self) -> None:
        """Aggiorna il timestamp."""
        self.timestamp = time.time()


# Topic ZeroMQ standardizzati
class Topics:
    """
    Topic ZeroMQ per routing dei messaggi.
    
    Il simulatore pubblica su questi topic, la GCS si sottoscrive.
    La GCS pubblica comandi, il FC/Simulatore si sottoscrive.
    """
    # Telemetria (Simulatore → GCS)
    TELEMETRY = "telemetry/flight"
    
    # Comandi (GCS → Simulatore/FC)
    CONTROLS = "controls/pilot"
    
    # Stato sistema (tutti i componenti → GCS)
    SYSTEM_STATUS = "system/status"
    
    # Eventi speciali (crash, allarmi, transizioni VTOL)
    EVENTS = "events/alerts"


# Versione del protocollo
PROTOCOL_VERSION = "1.0.0"