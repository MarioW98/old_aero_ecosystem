"""
simulator/aircraft/config.py

Configurazione completa di un velivolo.

Raggruppa tutti i parametri necessari alla simulazione:
- Massa e inerzia (dinamica)
- Tabelle aerodinamiche (aero)
- Configurazione motore (propulsione)
- Configurazione elica (propulsione)
"""

from __future__ import annotations


class AircraftConfig:
    """
    Configurazione completa di un velivolo.

    Uso:
        config = AircraftConfig(
            name="C172",
            mass=1000.0,
            inertia={'Ixx': 1500, 'Iyy': 2500, 'Izz': 3000, 'Ixz': 0},
            aero_config=make_c172_config(),
            engine_config=make_c172_engine(),
            propeller_config=make_c172_propeller(),
        )
    """

    def __init__(self,
                 name: str,
                 mass: float,
                 inertia: dict,
                 aero_config,
                 engine_config,
                 propeller_config):
        """
        Args:
            name: nome del velivolo.
            mass: massa [kg].
            inertia: dict con 'Ixx', 'Iyy', 'Izz', 'Ixz' [kg·m²].
            aero_config: AeroConfig (da dynamics/aero/coefficients.py).
            engine_config: EngineConfig (da dynamics/propulsion/engine.py).
            propeller_config: PropellerConfig (da dynamics/propulsion/propeller.py).
        """
        self.name = name
        self.mass = mass
        self.inertia = inertia
        self.aero_config = aero_config
        self.engine_config = engine_config
        self.propeller_config = propeller_config