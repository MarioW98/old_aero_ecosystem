"""
ipc_bus/trajectory.py

Generatori di traiettorie coerenti per test di visualizzazione.

Una traiettoria produce uno stato di telemetria COMPLETO e COERENTE
a partire da un modello matematico del percorso. A differenza del mock
sinusoidale (campi indipendenti), qui posizione, prua, assetto e velocità
raccontano tutti la stessa storia.

Uso:
    traj  = StraightLineTrajectory(airspeed=50.0, heading=90.0)
    stato = traj.sample(t=10.0)   # TelemetryData al tempo t
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

from .telemetry_protocol import TelemetryData


class TrajectoryGenerator(ABC):
    """
    Interfaccia comune a tutti i generatori di traiettoria.

    Ogni traiettoria è una funzione dello stato nel tempo: dato un tempo
    assoluto t (secondi), restituisce lo stato completo e coerente del
    velivolo. È stateless: nessun accumulo interno, quindi thread-safe
    e facilmente testabile.
    """

    @abstractmethod
    def sample(self, t: float) -> TelemetryData:
        """Restituisce lo stato di telemetria al tempo t (secondi)."""
        raise NotImplementedError


class StraightLineTrajectory(TrajectoryGenerator):
    """
    Traiettoria rettilinea livellata.

    Il velivolo vola in linea retta a velocità e quota costanti, prua
    fissa, nessun rollio e nessuna virata.

    La posizione è calcolata in forma chiusa (analitica):
        nord = nord0 + V·t·cos(prua)
        est  = est0  + V·t·sin(prua)
        giù  = -quota            (NED: l'asse giù è positivo)

    Convenzione prua (aeronautica): 0°=Nord, 90°=Est, misura oraria.
    """

    def __init__(
        self,
        airspeed: float = 50.0,        # m/s
        heading: float = 0.0,          # gradi, 0=Nord, 90=Est
        altitude: float = 1000.0,      # m
        start_north: float = 0.0,      # m
        start_east: float = 0.0,       # m
        pitch: float = 0.0,            # gradi
        rpm: float = 2500.0,
        oil_temp: float = 80.0,
        manifold_pressure: float = 101.3,
        fuel_flow: float = 0.001,
    ) -> None:
        self._airspeed = airspeed
        self._heading = heading % 360.0
        self._altitude = altitude
        self._start_north = start_north
        self._start_east = start_east
        self._pitch = pitch
        self._rpm = rpm
        self._oil_temp = oil_temp
        self._manifold_pressure = manifold_pressure
        self._fuel_flow = fuel_flow

        # Componenti di velocità nel piano orizzontale (m/s)
        hdg_rad = math.radians(self._heading)
        self._v_north = airspeed * math.cos(hdg_rad)
        self._v_east = airspeed * math.sin(hdg_rad)

    def sample(self, t: float) -> TelemetryData:
        # Posizione integrata analiticamente
        pos_north = self._start_north + self._v_north * t
        pos_east = self._start_east + self._v_east * t
        pos_down = -self._altitude  # NED: giù positivo, quota sopra il riferimento

        return TelemetryData(
            airspeed=self._airspeed,
            altitude=self._altitude,
            vertical_speed=0.0,          # volo livellato
            heading=self._heading,       # prua fissa
            pitch=self._pitch,
            roll=0.0,                    # nessuna virata
            turn_rate=0.0,               # nessuna virata
            rpm=self._rpm,
            oil_temp=self._oil_temp,
            manifold_pressure=self._manifold_pressure,
            fuel_flow=self._fuel_flow,
            pos_north=pos_north,
            pos_east=pos_east,
            pos_down=pos_down,
        )

# =========================================================================
# COSTANTE FISICA
# =========================================================================
# Accelerazione di gravità (m/s²) per il calcolo della virata coordinata
_G = 9.81


class OrbitTrajectory(TrajectoryGenerator):
    """
    Traiettoria orbitale circolare livellata (virata coordinata).

    Il velivolo descrive un cerchio di raggio R a velocità e quota
    costanti. Tutti i campi sono coerenti con il moto circolare:
      - posizione:      punto sul cerchio
      - prua:           tangente al cerchio (calcolata dalla velocità)
      - rollio:         bank di virata coordinata  atan(V² / (R·g))
      - turn_rate:      velocità angolare          V/R
      - vertical_speed: 0 (orbita livellata)

    direction: +1 = virata destra / oraria, -1 = virata sinistra / antioraria.
    """

    def __init__(
        self,
        airspeed: float = 50.0,        # m/s
        radius: float = 500.0,         # m
        altitude: float = 1000.0,      # m
        center_north: float = 0.0,     # m
        center_east: float = 0.0,      # m
        direction: int = 1,            # +1 destra, -1 sinistra
        phase0: float = 0.0,           # angolo iniziale (rad)
        pitch: float = 0.0,            # gradi (0 per orbita livellata)
        rpm: float = 2500.0,
        oil_temp: float = 80.0,
        manifold_pressure: float = 101.3,
        fuel_flow: float = 0.001,
    ) -> None:
        if airspeed <= 0:
            raise ValueError("airspeed deve essere > 0")
        if radius <= 0:
            raise ValueError("radius deve essere > 0")
        if direction not in (1, -1):
            raise ValueError("direction deve essere +1 oppure -1")

        self._airspeed = airspeed
        self._radius = radius
        self._altitude = altitude
        self._center_north = center_north
        self._center_east = center_east
        self._direction = direction
        self._phase0 = phase0
        self._pitch = pitch
        self._rpm = rpm
        self._oil_temp = oil_temp
        self._manifold_pressure = manifold_pressure
        self._fuel_flow = fuel_flow

        # Velocità angolare (rad/s) e grandezze di virata coordinata
        self._omega = airspeed / radius
        self._bank_rad = math.atan(airspeed * airspeed / (radius * _G))
        self._turn_rate_deg = math.degrees(self._omega)

    def sample(self, t: float) -> TelemetryData:
        # Angolare sul cerchio
        theta = self._phase0 + self._direction * self._omega * t

        # Posizione sul cerchio
        pos_north = self._center_north + self._radius * math.cos(theta)
        pos_east = self._center_east + self._radius * math.sin(theta)
        pos_down = -self._altitude

        # Velocità (derivata della posizione) → prua tangente
        v_north = -self._direction * self._radius * self._omega * math.sin(theta)
        v_east = self._direction * self._radius * self._omega * math.cos(theta)
        heading = math.degrees(math.atan2(v_east, v_north)) % 360.0

        # Rollio e turn_rate con segno coerente alla direzione di virata
        roll = self._direction * math.degrees(self._bank_rad)
        turn_rate = self._direction * self._turn_rate_deg

        return TelemetryData(
            airspeed=self._airspeed,
            altitude=self._altitude,
            vertical_speed=0.0,          # orbita livellata
            heading=heading,
            pitch=self._pitch,
            roll=roll,
            turn_rate=turn_rate,
            rpm=self._rpm,
            oil_temp=self._oil_temp,
            manifold_pressure=self._manifold_pressure,
            fuel_flow=self._fuel_flow,
            pos_north=pos_north,
            pos_east=pos_east,
            pos_down=pos_down,
        )


class ClimbDescentTrajectory(TrajectoryGenerator):
    """
    Traiettoria rettilinea in salita o discesa.

    Il velivolo vola dritto (prua fissa, nessun rollio) variando la quota
    a velocità verticale costante. I campi sono coerenti:
      - pitch:           derivato dall'angolo di salita  asin(vs / V)
      - velocità orizz.: V · cos(angolo di salita)
      - quota:           start_altitude + vs · t

    airspeed è la velocità TOTALE lungo la traiettoria. Vincolo: |vs| < V.
    """

    def __init__(
        self,
        airspeed: float = 50.0,        # m/s (totale lungo la traiettoria)
        heading: float = 0.0,          # gradi, 0=Nord, 90=Est
        vertical_speed: float = 2.0,   # m/s (+ salita, - discesa)
        start_altitude: float = 1000.0,# m
        start_north: float = 0.0,      # m
        start_east: float = 0.0,       # m
        rpm: float = 2500.0,
        oil_temp: float = 80.0,
        manifold_pressure: float = 101.3,
        fuel_flow: float = 0.001,
    ) -> None:
        if airspeed <= 0:
            raise ValueError("airspeed deve essere > 0")
        if abs(vertical_speed) >= airspeed:
            raise ValueError("|vertical_speed| deve essere minore di airspeed")

        self._airspeed = airspeed
        self._heading = heading % 360.0
        self._vertical_speed = vertical_speed
        self._start_altitude = start_altitude
        self._start_north = start_north
        self._start_east = start_east
        self._rpm = rpm
        self._oil_temp = oil_temp
        self._manifold_pressure = manifold_pressure
        self._fuel_flow = fuel_flow

        # Angolo di salita e velocità orizzontale (coerenti con V e vs)
        self._gamma_rad = math.asin(vertical_speed / airspeed)
        self._pitch = math.degrees(self._gamma_rad)
        horiz_speed = airspeed * math.cos(self._gamma_rad)

        hdg_rad = math.radians(self._heading)
        self._v_north = horiz_speed * math.cos(hdg_rad)
        self._v_east = horiz_speed * math.sin(hdg_rad)

    def sample(self, t: float) -> TelemetryData:
        pos_north = self._start_north + self._v_north * t
        pos_east = self._start_east + self._v_east * t
        altitude = self._start_altitude + self._vertical_speed * t
        pos_down = -altitude

        return TelemetryData(
            airspeed=self._airspeed,
            altitude=altitude,
            vertical_speed=self._vertical_speed,
            heading=self._heading,       # prua fissa
            pitch=self._pitch,           # coerente con l'angolo di salita
            roll=0.0,                    # volo dritto
            turn_rate=0.0,               # nessuna virata
            rpm=self._rpm,
            oil_temp=self._oil_temp,
            manifold_pressure=self._manifold_pressure,
            fuel_flow=self._fuel_flow,
            pos_north=pos_north,
            pos_east=pos_east,
            pos_down=pos_down,
        )


# =========================================================================
# FACTORY — selezione della traiettoria per nome (riusabile)
# =========================================================================
# Registro dei preset disponibili. Chiave = nome breve usato anche dal menu.
TRAJECTORY_PRESETS = {
    "straight": StraightLineTrajectory,
    "orbit": OrbitTrajectory,
    "climb": ClimbDescentTrajectory,
}


def create_trajectory(name: str, **kwargs) -> TrajectoryGenerator:
    """
    Crea una traiettoria per nome, con eventuali parametri personalizzati.

    Nomi disponibili: 'straight', 'orbit', 'climb'.
    Esempio:
        traj = create_trajectory("orbit", airspeed=60.0, radius=800.0)
    """
    klass = TRAJECTORY_PRESETS.get(name)
    if klass is None:
        raise ValueError(
            f"Traiettoria sconosciuta: '{name}'. "
            f"Disponibili: {sorted(TRAJECTORY_PRESETS)}"
        )
    return klass(**kwargs)








