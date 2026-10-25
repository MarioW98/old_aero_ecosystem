"""
simulator/dynamics/propulsion/

Modulo di propulsione. Struttura a tre livelli:
- engine.py     : modello del motore (potenza, RPM, coppia)
- propeller.py  : modello dell'elica (spinta, effetti secondari)
- powerplant.py : composizione motore+elica (punto di ingresso)
"""

from .engine import EngineConfig, EngineModel
from .propeller import PropellerConfig, PropellerModel
from .powerplant import Powerplant