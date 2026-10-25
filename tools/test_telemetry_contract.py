"""
tools/test_telemetry_contract.py
Verifica che il contratto TelemetryData includa la posizione NED
e che la serializzazione MessagePack resti funzionante.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ipc_bus import TelemetryData

def main():
    # 1. Crea un pacchetto con posizione
    t = TelemetryData(
        airspeed=55.0,
        altitude=1200.0,
        heading=90.0,
        pos_north=100.0,
        pos_east=-50.0,
        pos_down=-1200.0,
    )

    # 2. Verifica presenza campi
    assert hasattr(t, "pos_north"), "Manca pos_north"
    assert hasattr(t, "pos_east"), "Manca pos_east"
    assert hasattr(t, "pos_down"), "Manca pos_down"

    # 3. Round-trip serializzazione
    packed = t.to_bytes()
    unpacked = TelemetryData.from_bytes(packed)
    assert unpacked.pos_north == 100.0, "pos_north non sopravvive al round-trip"
    assert unpacked.pos_east == -50.0, "pos_east non sopravvive al round-trip"
    assert unpacked.pos_down == -1200.0, "pos_down non sopravvive al round-trip"
    assert unpacked.airspeed == 55.0, "campo esistente corrotto"

    # 4. Backward compatibility: messaggio senza posizione
    legacy = TelemetryData(airspeed=30.0)
    legacy_packed = legacy.to_bytes()
    legacy_back = TelemetryData.from_bytes(legacy_packed)
    assert legacy_back.pos_north == 0.0, "default posizione non corretto"

    print("PASS: contratto NED corretto, serializzazione OK, backward-compat OK")
    print(f"  pos_north={unpacked.pos_north}, pos_east={unpacked.pos_east}, pos_down={unpacked.pos_down}")

if __name__ == "__main__":
    main()