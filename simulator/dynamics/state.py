"""
simulator/dynamics/state.py

Stato del velivolo e quaternioni per la rappresentazione dell'assetto.

D1.1: Fondamenta — quaternioni + stato velivolo.

Convenzioni:
- Quaternioni: q = (w, x, y, z), w parte scalare.
- Rotazione aeronautica 3-2-1: yaw (psi) -> pitch (theta) -> roll (phi).
- Angoli di Eulero in radianti nelle API interne; proprietà in gradi.
- Frame NED per la posizione, body frame per velocità e velocità angolari.
"""

from __future__ import annotations

import math
import numpy as np


class Quaternion:
    """
    Quaternione per la rappresentazione dell'assetto.

    Vantaggi rispetto agli angoli di Eulero: nessuna singolarità di
    gimbal lock, composizione di rotazioni stabile, integrazione numerica
    più robusta. Essenziale per un tailsitter che vola verticale (pitch ±90°).
    """

    __slots__ = ('w', 'x', 'y', 'z')

    def __init__(self, w: float = 1.0, x: float = 0.0,
                 y: float = 0.0, z: float = 0.0):
        self.w = w
        self.x = x
        self.y = y
        self.z = z

    # ------------------------------------------------------------------
    # Costruttori
    # ------------------------------------------------------------------
    @classmethod
    def identity(cls) -> Quaternion:
        """Quaternione identità (nessuna rotazione)."""
        return cls(1.0, 0.0, 0.0, 0.0)

    @classmethod
    def from_euler(cls, roll: float, pitch: float, yaw: float) -> Quaternion:
        """
        Crea un quaternione da angoli di Eulero (radianti).
        Convenzione 3-2-1: yaw -> pitch -> roll.
        """
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)

        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy

        return cls(w, x, y, z)

    # ------------------------------------------------------------------
    # Conversioni
    # ------------------------------------------------------------------
    def to_euler(self) -> tuple[float, float, float]:
        """
        Converte in angoli di Eulero (radianti).
        Restituisce (roll, pitch, yaw). Gestisce il gimbal lock a ±90° pitch.
        """
        # Roll (rotazione attorno a x)
        sinr_cosp = 2.0 * (self.w * self.x + self.y * self.z)
        cosr_cosp = 1.0 - 2.0 * (self.x * self.x + self.y * self.y)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        # Pitch (rotazione attorno a y) — con clamp per gimbal lock
        sinp = 2.0 * (self.w * self.y - self.z * self.x)
        if abs(sinp) >= 1.0:
            pitch = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch = math.asin(sinp)

        # Yaw (rotazione attorno a z)
        siny_cosp = 2.0 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1.0 - 2.0 * (self.y * self.y + self.z * self.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        return roll, pitch, yaw

    def to_rotation_matrix(self) -> np.ndarray:
        """
        Matrice di rotazione 3x3 che trasforma dal body frame al NED.
        v_NED = R @ v_body
        """
        q = self.normalize()
        w, x, y, z = q.w, q.x, q.y, q.z

        return np.array([
            [1.0 - 2.0*(y*y + z*z), 2.0*(x*y - w*z),     2.0*(x*z + w*y)],
            [2.0*(x*y + w*z),       1.0 - 2.0*(x*x + z*z), 2.0*(y*z - w*x)],
            [2.0*(x*z - w*y),       2.0*(y*z + w*x),       1.0 - 2.0*(x*x + y*y)],
        ])

    # ------------------------------------------------------------------
    # Operazioni
    # ------------------------------------------------------------------
    def __mul__(self, other: Quaternion) -> Quaternion:
        """Moltiplicazione di quaternioni (composizione di rotazioni)."""
        w = self.w*other.w - self.x*other.x - self.y*other.y - self.z*other.z
        x = self.w*other.x + self.x*other.w + self.y*other.z - self.z*other.y
        y = self.w*other.y - self.x*other.z + self.y*other.w + self.z*other.x
        z = self.w*other.z + self.x*other.y - self.y*other.x + self.z*other.w
        return Quaternion(w, x, y, z)

    def conjugate(self) -> Quaternion:
        """Quaternione coniugato (rotazione inversa)."""
        return Quaternion(self.w, -self.x, -self.y, -self.z)

    def magnitude(self) -> float:
        """Norma del quaternione."""
        return math.sqrt(self.w**2 + self.x**2 + self.y**2 + self.z**2)

    def normalize(self) -> Quaternion:
        """Restituisce il quaternione normalizzato (norma = 1)."""
        mag = self.magnitude()
        if mag < 1e-12:
            return Quaternion.identity()
        return Quaternion(self.w / mag, self.x / mag,
                          self.y / mag, self.z / mag)

    def rotate_vector(self, v: np.ndarray) -> np.ndarray:
        """Ruota un vettore 3D dal body frame al NED."""
        R = self.to_rotation_matrix()
        return R @ np.asarray(v, dtype=float)

    def __repr__(self) -> str:
        return (f"Quaternion(w={self.w:.4f}, x={self.x:.4f}, "
                f"y={self.y:.4f}, z={self.z:.4f})")


class AircraftState:
    """
    Stato completo del velivolo (6-DoF).

    Frame di riferimento:
    - Posizione: NED (North-East-Down) in metri
    - Velocità: body frame (u, v, w) in m/s
    - Assetto: quaternione (body -> NED)
    - Velocità angolari: body frame (p, q, r) in rad/s
    """

    def __init__(self):
        # Posizione NED (metri): [north, east, down]
        self.position = np.zeros(3)

        # Velocità body frame (m/s): [u, v, w]
        self.velocity_body = np.zeros(3)

        # Assetto (quaternione)
        self.attitude = Quaternion.identity()

        # Velocità angolari body frame (rad/s): [p, q, r]
        self.angular_velocity = np.zeros(3)

        # Tempo di simulazione (secondi)
        self.time = 0.0

    # ------------------------------------------------------------------
    # Proprietà derivate (comode per telemetria e validazione)
    # ------------------------------------------------------------------
    @property
    def altitude(self) -> float:
        """Quota in metri (NED down è negativo verso l'alto)."""
        return -self.position[2]

    @property
    def airspeed(self) -> float:
        """Velocità aerodinamica (m/s) — norma della velocità body."""
        return float(np.linalg.norm(self.velocity_body))

    @property
    def roll(self) -> float:
        """Rollio in gradi."""
        r, _, _ = self.attitude.to_euler()
        return math.degrees(r)

    @property
    def pitch(self) -> float:
        """Beccheggio in gradi."""
        _, p, _ = self.attitude.to_euler()
        return math.degrees(p)

    @property
    def heading(self) -> float:
        """Prua in gradi [0, 360)."""
        _, _, y = self.attitude.to_euler()
        return math.degrees(y) % 360.0