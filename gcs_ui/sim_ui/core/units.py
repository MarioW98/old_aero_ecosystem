from __future__ import annotations
from dataclasses import dataclass


@dataclass
class UnitDefinition:
    unit_id: str
    label: str
    factor: float        # moltiplicatore: valore_display = valore_SI * factor
    decimals: int = 0
    major_step: float = 0.0


def unit_index(units: list[UnitDefinition], key: str) -> int:
    """Trova l'indice di un'unità per unit_id o label."""
    for i, u in enumerate(units):
        if u.unit_id == key or u.label == key:
            return i
    return 0


# =============================================================================
# VELOCITÀ — base SI: m/s
# =============================================================================
AIRSPEED_UNITS = [
    UnitDefinition("ms",  "M/S",    1.0,       0, 20.0),    # base SI
    UnitDefinition("kt",  "KNOTS",  1.94384,   0, 20.0),    # 1 m/s = 1.94384 kt
    UnitDefinition("kmh", "KM/H",   3.6,       0, 40.0),    # 1 m/s = 3.6 km/h
    UnitDefinition("mph", "MPH",    2.23694,   0, 20.0),    # 1 m/s = 2.23694 mph
]

# =============================================================================
# ALTITUDINE — base SI: metri
# =============================================================================
ALTITUDE_UNITS = [
    UnitDefinition("m",  "METERS",  1.0,      0, 500.0),   # base SI
    UnitDefinition("ft", "FEET",    3.28084,  0, 1000.0),  # 1 m = 3.28084 ft
]

# =============================================================================
# VELOCITÀ VERTICALE — base SI: m/s
# =============================================================================
VSI_UNITS = [
    UnitDefinition("ms",  "M/S",     1.0,      1, 2.0),     # base SI
    UnitDefinition("fpm", "FT/MIN",  196.85,   0, 500.0),   # 1 m/s = 196.85 ft/min
    UnitDefinition("fps", "FT/SEC",  3.28084,  1, 10.0),    # 1 m/s = 3.28084 ft/s
]