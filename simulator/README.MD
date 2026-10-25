
## Architettura

```bash
simulator/
├── dynamics/
│   ├── __init__.py
│   ├── state.py            # Stato velivolo + quaternioni
│   ├── atmosphere.py       # Atmosfera ISA
│   ├── rigid_body.py       # Equazioni del moto 6-DoF
│   ├── integrator.py       # Integratore RK4
│   ├── aero/
│   │   ├── __init__.py
│   │   ├── coefficients.py # Tabelle CL, CD, Cm (ala fissa)
│   │   └── forces.py       # Forze/momenti aerodinamici
│   └── propulsion/
│       ├── __init__.py
│       └── engine.py       # Motore semplice (per ora)
├── aircraft/
│   └── fixed_wing/
│       └── config.py       # Massa, inerzia, geometria
├── sim_engine.py           # Orchestratore: loop + TelemetryData
└── test_dynamics.py        # Validazione con casi noti
```
