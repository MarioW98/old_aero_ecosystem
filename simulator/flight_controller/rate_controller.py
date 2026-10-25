"""
flight_controller/rate_controller.py

Inner loop del flight controller: rate (p,q,r) → superfici.

Il pilota comanda una VELOCITÀ ANGOLARE target (rate), non le superfici.
Il rate controller calcola le deflessioni necessarie per inseguire quel
rate e stabilizzare il velivolo. Questo è ciò che rende il velivolo
manovrabile: senza anello di retroazione, lo stick agisce a ciclo aperto.

Output: deflessioni superficie in RADIANTI, già saturate ai limiti
attuatori e con il trim di equilibrio applicato.
"""

from __future__ import annotations

from .pid import PIDController, _clamp
from .fc_config import RateConfig, AxisGains


class RateController:
    """
    Rate controller a 3 assi (roll, pitch, yaw).

    Uso:
        # La RateConfig è il RISULTATO del calcolo model-based (T2):
        # non si costruisce a mano. Vedi fc_config.py per i tipi contenitore.
        rc = RateController(cfg_da_sintesi_model_based)
        surfaces = rc.compute(state, rate_cmd=(p_cmd, q_cmd, r_cmd), dt=0.02)
        # surfaces = {'delta_a':..., 'delta_e':..., 'delta_r':...}  [rad]
    """

    def __init__(self, config: RateConfig):
        self.config = config
        lim = config.limits

        self._pid_roll = PIDController(
            config.roll.kp, config.roll.ki, config.roll.kd,
            lim.max_delta_a, config.deriv_filter_alpha)
        self._pid_pitch = PIDController(
            config.pitch.kp, config.pitch.ki, config.pitch.kd,
            lim.max_delta_e, config.deriv_filter_alpha)
        self._pid_yaw = PIDController(
            config.yaw.kp, config.yaw.ki, config.yaw.kd,
            lim.max_delta_r, config.deriv_filter_alpha)

    # ------------------------------------------------------------------
    # Calcolo
    # ------------------------------------------------------------------
    def compute(self, state, rate_cmd: tuple, dt: float) -> dict:
        """
        Calcola le deflessioni superficie per inseguire il rate target.

        Args:
            state: AircraftState (legge state.angular_velocity = [p,q,r]).
            rate_cmd: tuple (p_cmd, q_cmd, r_cmd) in rad/s.
            dt: passo temporale [s].

        Returns:
            dict {'delta_a', 'delta_e', 'delta_r'} in radianti, saturati.
        """
        cfg = self.config
        lim = cfg.limits
        p, q, r = state.angular_velocity
        p_cmd, q_cmd, r_cmd = rate_cmd

        # PID core (convenzione standard error = setpoint − measurement)
        out_roll = self._pid_roll.compute(p_cmd, p, dt)
        out_pitch = self._pid_pitch.compute(q_cmd, q, dt)
        out_yaw = self._pid_yaw.compute(r_cmd, r, dt)

        # Applicazione segni di direzione + trim + saturazione finale.
        # Il trim è un offset fisico assoluto della superficie.
        delta_a = _clamp(
            cfg.sign_roll * out_roll + cfg.trim_delta_a,
            -lim.max_delta_a, lim.max_delta_a)
        delta_e = _clamp(
            cfg.sign_pitch * out_pitch + cfg.trim_delta_e,
            -lim.max_delta_e, lim.max_delta_e)
        delta_r = _clamp(
            cfg.sign_yaw * out_yaw + cfg.trim_delta_r,
            -lim.max_delta_r, lim.max_delta_r)

        return {'delta_a': delta_a, 'delta_e': delta_e, 'delta_r': delta_r}

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
    def reset(self):
        """Azzera gli stati interni di tutti e tre i PID."""
        self._pid_roll.reset()
        self._pid_pitch.reset()
        self._pid_yaw.reset()

    def update_gains(self, config: RateConfig,
                     reset_integral: bool = False):
        """
        Aggiorna i guadagni PID da una nuova RateConfig.

        Usato dal GainScheduler per applicare guadagni interpolati
        in tempo reale senza ricreare il controllore.

        Args:
            config: Nuova RateConfig con guadagni aggiornati.
            reset_integral: Se True, azzera l'integrale per evitare
                           transitori. Se False (default), preserva
                           l'integrale per transizione fluida.
        """
        self.config = config

        self._pid_roll.kp = config.roll.kp
        self._pid_roll.ki = config.roll.ki
        self._pid_roll.kd = config.roll.kd
        self._pid_roll.output_limit = config.limits.max_delta_a

        self._pid_pitch.kp = config.pitch.kp
        self._pid_pitch.ki = config.pitch.ki
        self._pid_pitch.kd = config.pitch.kd
        self._pid_pitch.output_limit = config.limits.max_delta_e

        self._pid_yaw.kp = config.yaw.kp
        self._pid_yaw.ki = config.yaw.ki
        self._pid_yaw.kd = config.yaw.kd
        self._pid_yaw.output_limit = config.limits.max_delta_r

        if reset_integral:
            self.reset()