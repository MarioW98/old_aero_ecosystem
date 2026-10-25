"""
simulator/sim_engine.py

SimEngine: orchestratore della simulazione di volo.

D3.2: assembla tutti i componenti in un unico loop:
  Atmosfera → Aerodinamica → Propulsione → Gravità → Dinamica → Integratore

Il SimEngine gestisce lo stato del velivolo e avanza la simulazione
di un passo alla volta. Produce telemetria compatibile con la GCS.

Uso:
    from simulator.aircraft.c172 import make_c172_aircraft
    config = make_c172_aircraft()
    sim = SimEngine(config)
    sim.reset(initial_state)
    for _ in range(steps):
        sim.step(dt, controls)
    telemetry = sim.get_telemetry()
"""

from __future__ import annotations

import math
import numpy as np

from dynamics.state import Quaternion, AircraftState
from dynamics.atmosphere import Atmosphere
from dynamics.rigid_body import RigidBodyDynamics
from dynamics.integrator import RK4Integrator
from dynamics.aero.coefficients import AeroCoefficients
from dynamics.aero.forces import AeroForces
from dynamics.propulsion.engine import EngineModel
from dynamics.propulsion.propeller import PropellerModel
from dynamics.propulsion.powerplant import Powerplant

# Accelerazione di gravità standard [m/s²]
G = 9.80665


class SimEngine:
    """
    Orchestratore della simulazione di volo.

    Gestisce lo stato del velivolo e avanza la simulazione passo-passo,
    calcolando tutte le forze (aerodinamiche, propulsive, gravitazionali)
    e integrando le equazioni del moto.
    """

    def __init__(self, aircraft_config):
        """
        Args:
            aircraft_config: AircraftConfig con tutti i parametri.
        """
        self.config = aircraft_config
        self.mass = aircraft_config.mass
        self.inertia = aircraft_config.inertia

        # Inizializza i componenti
        aero_coeff = AeroCoefficients(aircraft_config.aero_config)
        self.aero_forces = AeroForces(aero_coeff)

        engine = EngineModel(aircraft_config.engine_config)
        propeller = PropellerModel(aircraft_config.propeller_config)
        self.powerplant = Powerplant(engine, propeller)

        self.dynamics = RigidBodyDynamics(self.mass, self.inertia)
        self.integrator = RK4Integrator(self.dynamics)

        # Stato corrente (da inizializzare con reset())
        self.state = AircraftState()

        # Controlli correnti
        self.controls = {
            'throttle': 0.0,
            'delta_e': 0.0,
            'delta_a': 0.0,
            'delta_r': 0.0,
        }

        # Telemetria propulsione (aggiornata ad ogni step)
        self._prop_telemetry = {}

    # ------------------------------------------------------------------
    # Inizializzazione
    # ------------------------------------------------------------------
    def reset(self, state: AircraftState = None):
        """
        Resetta lo stato della simulazione.

        Args:
            state: stato iniziale. Se None, usa uno stato di default
                   (fermo al suolo).
        """
        if state is not None:
            self.state = state
        else:
            self.state = AircraftState()

        self.controls = {
            'throttle': 0.0,
            'delta_e': 0.0,
            'delta_a': 0.0,
            'delta_r': 0.0,
        }
        self._prop_telemetry = {}

    # ------------------------------------------------------------------
    # Passo di simulazione
    # ------------------------------------------------------------------
    def step(self, dt: float, controls: dict = None):
        """
        Avanza la simulazione di un passo temporale.

        Args:
            dt: passo temporale [s].
            controls: dict con 'throttle', 'delta_e', 'delta_a', 'delta_r'.
                      Se None, usa i controlli correnti.

        Returns:
            Lo stato aggiornato.
        """
        if controls is not None:
            self.controls.update(controls)

        # 1. Angoli aerodinamici
        alpha, beta = AeroForces.compute_alpha_beta(self.state.velocity_body)

        # 2. Forze aerodinamiche
        aero_controls = {
            'delta_e': self.controls.get('delta_e', 0.0),
            'delta_a': self.controls.get('delta_a', 0.0),
            'delta_r': self.controls.get('delta_r', 0.0),
        }
        F_aero, M_aero = self.aero_forces.compute(self.state, aero_controls)

        # 3. Forze di propulsione
        throttle = self.controls.get('throttle', 0.0)
        velocity = self.state.airspeed
        F_prop, M_prop, self._prop_telemetry = self.powerplant.compute(
            throttle, velocity, alpha)

        # 4. Gravità nel body frame
        F_grav = self._compute_gravity_body()

        # 5. Forze e momenti totali
        F_total = F_aero + F_prop + F_grav
        M_total = M_aero + M_prop

        # 6. Integrazione
        self.state = self.integrator.step(self.state, F_total, M_total, dt)

        return self.state

    # ------------------------------------------------------------------
    # Gravità
    # ------------------------------------------------------------------
    def _compute_gravity_body(self) -> np.ndarray:
        """Calcola la forza di gravità nel body frame."""
        gravity_NED = np.array([0.0, 0.0, self.mass * G])
        q_conj = self.state.attitude.conjugate()
        return q_conj.rotate_vector(gravity_NED)

    # ------------------------------------------------------------------
    # Telemetria
    # ------------------------------------------------------------------
    def get_telemetry(self) -> dict:
        """
        Restituisce la telemetria corrente come dict.
        Compatibile con TelemetryData della GCS.
        Calcola vertical_speed e turn_rate dalla fisica dello stato.
        """
        s = self.state
        roll, pitch, yaw = s.attitude.to_euler()

        # =============================================================
        # VERTICAL SPEED: velocità verticale nel frame NED
        # velocity_NED = R_body_to_NED @ velocity_body
        # vertical_speed = -v_down (positivo = salita)
        # =============================================================
        velocity_NED = s.attitude.rotate_vector(s.velocity_body)
        vertical_speed = -float(velocity_NED[2])  # m/s, positivo = salita

        # =============================================================
        # TURN RATE: rate di variazione heading (heading rate)
        # Trasformazione body rates → Euler rates (componente yaw)
        # psi_dot = (q·sin(φ) + r·cos(φ)) / cos(θ)
        # =============================================================
        p, q, r = s.angular_velocity
        cos_pitch = math.cos(pitch)
        if abs(cos_pitch) > 1e-6:
            turn_rate_rad = (q * math.sin(roll) + r * math.cos(roll)) / cos_pitch
        else:
            turn_rate_rad = 0.0  # Protezione gimbal lock a ±90° pitch
        turn_rate = math.degrees(turn_rate_rad)  # deg/s

        return {
            # Posizione
            'pos_north': float(s.position[0]),
            'pos_east': float(s.position[1]),
            'pos_down': float(s.position[2]),

            # Assetto (in gradi)
            'pitch': math.degrees(pitch),
            'roll': math.degrees(roll),
            'heading': math.degrees(yaw) % 360.0,

            # Velocità
            'airspeed': s.airspeed,
            'altitude': s.altitude,
            'vertical_speed': vertical_speed,
            'turn_rate': turn_rate,

            # Propulsione
            'thrust': self._prop_telemetry.get('thrust', 0.0),
            'throttle': self._prop_telemetry.get('throttle', 0.0),
            'rpm': self._prop_telemetry.get('rpm', 0.0),
            'power': self._prop_telemetry.get('power', 0.0),

            # Tempo
            'time': s.time,
        }

    