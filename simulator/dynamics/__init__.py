"""
simulator/dynamics/

Modulo di dinamica del volo. Contiene il motore fisico Python:
- state.py        : stato velivolo + quaternioni (D1.1)
- atmosphere.py   : modello ISA (D1.2)
- rigid_body.py   : equazioni del moto 6-DoF (D1.3)
- integrator.py   : integratore RK4 (D1.4)
- aero/           : aerodinamica (D2)
- propulsion/     : propulsione (D3)
"""