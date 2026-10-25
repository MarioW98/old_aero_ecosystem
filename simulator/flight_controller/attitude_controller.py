"""
flight_controller/attitude_controller.py

Middle loop del flight controller: angle target → rate target.

FC-2: l'AttitudeController riceve lo stick del pilota (angle rate command),
lo integra per ottenere un angle target (con limiti fisici), calcola l'errore
angolare, e produce un rate target per il RateController.

Struttura: P puro (no I, no D).
- No I: l'integrale sull'angolo causerebbe overshoot nel loop combinato.
        Il rate loop ha già il suo Ki per il tracking del rate.
- No D: il rate loop (con D on measurement) fornisce già lo smorzamento.

Convenzione angle rate:
- roll_stick > 0  → roll_target cresce → rollio destro
- pitch_stick > 0 → pitch_target cresce → cabrata (nose-up)
  (pitch positivo = nose-up nel frame NED/Eulero 3-2-1)

Il yaw NON è gestito qui: in FC-2 il pilota comanda r_cmd direttamente
(rate mode). L'heading controller sarà introdotto in FC-3/FC-4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class AttitudeConfig:
    """Configurazione dell'attitude controller."""
    kp_roll: float = 4.0          # rate target [rad/s] per rad di errore angolare
    kp_pitch: float = 4.0

    max_roll_rate: float = 0.5    # rad/s, rate max di cambiamento angolo rollio
    max_pitch_rate: float = 1.0   # rad/s, rate max di cambiamento angolo pitch

    max_roll_angle: float = math.radians(45.0)   # rad, angolo rollio max
    max_pitch_angle: float = math.radians(30.0)  # rad, angolo pitch max


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else (hi if value > hi else value)


class AttitudeController:
    """
    Attitude controller (middle loop): angle rate command → rate target.

    Uso:
        # L'AttitudeConfig è il RISULTATO del calcolo model-based (T2).
        ac = AttitudeController(cfg_da_sintesi_model_based)
        p_cmd, q_cmd = ac.compute(state, stick_roll, stick_pitch, dt)
        # poi: surfaces = rate_controller.compute(state, (p_cmd, q_cmd, r_cmd), dt)
    """

    def __init__(self, config: AttitudeConfig):
        self.config = config

        # Angle target correnti [rad].
        # Si congelano quando lo stick è neutro (angle rate = 0).
        self._roll_target: float = 0.0
        self._pitch_target: float = 0.0

    # ------------------------------------------------------------------
    # Calcolo
    # ------------------------------------------------------------------
    def compute(self, state, stick_roll: float, stick_pitch: float,
                dt: float) -> tuple[float, float]:
        """
        Calcola il rate target (p_cmd, q_cmd) a partire dallo stick.

        Args:
            state: AircraftState (legge attitude.to_euler() per roll, pitch).
            stick_roll: comando rollio normalizzato [-1, +1].
            stick_pitch: comando pitch normalizzato [-1, +1].
                         Positivo = cabrata (nose-up).
            dt: passo temporale [s].

        Returns:
            (p_cmd, q_cmd): rate target per il rate controller [rad/s].
        """
        cfg = self.config

        # Clamp stick
        stick_roll = _clamp(stick_roll, -1.0, 1.0)
        stick_pitch = _clamp(stick_pitch, -1.0, 1.0)

        # ==============================================================
        # 1. ANGLE RATE COMMAND → INTEGRAZIONE → ANGLE TARGET
        # ==============================================================
        # Lo stick comanda un rate di cambiamento dell'angolo.
        # L'integrazione con limiti produce l'angle target.
        roll_rate_cmd = stick_roll * cfg.max_roll_rate
        pitch_rate_cmd = stick_pitch * cfg.max_pitch_rate

        self._roll_target += roll_rate_cmd * dt
        self._pitch_target += pitch_rate_cmd * dt

        # Limiti fisici sull'angolo target
        self._roll_target = _clamp(
            self._roll_target, -cfg.max_roll_angle, cfg.max_roll_angle)
        self._pitch_target = _clamp(
            self._pitch_target, -cfg.max_pitch_angle, cfg.max_pitch_angle)

        # ==============================================================
        # 2. ERRORE ANGOLARE
        # ==============================================================
        roll_current, pitch_current, _ = state.attitude.to_euler()

        roll_error = self._roll_target - roll_current
        pitch_error = self._pitch_target - pitch_current

        # Normalizza l'errore di rollio a [-π, π] (per wrap-around)
        roll_error = math.atan2(math.sin(roll_error), math.cos(roll_error))

        # ==============================================================
        # 3. RATE TARGET (P puro)
        # ==============================================================
        p_cmd = cfg.kp_roll * roll_error
        q_cmd = cfg.kp_pitch * pitch_error

        # Limita il rate target a valori raggiungibili dal rate loop
        p_cmd = _clamp(p_cmd, -cfg.max_roll_rate, cfg.max_roll_rate)
        q_cmd = _clamp(q_cmd, -cfg.max_pitch_rate, cfg.max_pitch_rate)

        return p_cmd, q_cmd

    # ------------------------------------------------------------------
    # Gestione angle target
    # ------------------------------------------------------------------
    def set_targets_from_state(self, state):
        """
        Congela gli angle target al valore corrente del velivolo.
        Utile dopo un reset o al primo avvio del FC in ANGLE mode.
        """
        roll, pitch, _ = state.attitude.to_euler()
        self._roll_target = roll
        self._pitch_target = pitch

    def reset(self):
        """Azzera gli angle target a zero."""
        self._roll_target = 0.0
        self._pitch_target = 0.0

    # ------------------------------------------------------------------
    # Accesso (per debug/UI)
    # ------------------------------------------------------------------
    @property
    def roll_target(self) -> float:
        return self._roll_target

    @property
    def pitch_target(self) -> float:
        return self._pitch_target