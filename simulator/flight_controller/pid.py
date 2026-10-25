"""
flight_controller/pid.py

Controllore PID generico con le tre caratteristiche richieste da un FC reale:
- Anti-windup a back-calculation
- Derivative ON MEASUREMENT (non on error), con filtro passabasso
- Saturazione dell'output

Convenzione: error = setpoint − measurement.
Il termine D usa la derivata della MISURA (con segno −) per evitare spike
quando il setpoint cambia bruscamente (es. rilascio dello stick).
"""

from __future__ import annotations


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else (hi if value > hi else value)


class PIDController:
    """
    PID single-axis con anti-windup e derivative filter.

    Uso:
        pid = PIDController(kp=0.2, ki=0.01, kd=0.03, output_limit=0.4)
        out = pid.compute(setpoint=0.0, measurement=0.3, dt=0.02)
    """

    def __init__(self, kp: float, ki: float, kd: float,
                 output_limit: float, deriv_filter_alpha: float = 0.5):
        """
        Args:
            kp, ki, kd: guadagni proporzionale, integrale, derivativo.
            output_limit: limite simmetrico dell'output [unità fisiche].
            deriv_filter_alpha: coefficiente del filtro passabasso sul D
                                (0=filtro forte/lento, 1=nessun filtro).
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limit = abs(output_limit)
        self.alpha = _clamp(deriv_filter_alpha, 0.0, 1.0)

        # Stati interni
        self._integral = 0.0
        self._meas_prev: float | None = None
        self._deriv_filtered = 0.0

        # Componenti dell'ultimo calcolo (per test/debug)
        self._p_term = 0.0
        self._d_term = 0.0

    # ------------------------------------------------------------------
    # Calcolo
    # ------------------------------------------------------------------
    def compute(self, setpoint: float, measurement: float, dt: float) -> float:
        """
        Esegue un passo di controllo.

        Args:
            setpoint: valore target.
            measurement: valore misurato.
            dt: passo temporale [s].

        Returns:
            Output saturato in [-output_limit, +output_limit].
        """
        error = setpoint - measurement

        # --- Proporzionale ---
        p = self.kp * error

        # --- Derivativo ON MEASUREMENT, filtrato ---
        # d(measure)/dt con segno − : se la misura cresce, il termine frena.
        if self._meas_prev is None or dt <= 1e-9:
            raw_deriv = 0.0
        else:
            raw_deriv = -(measurement - self._meas_prev) / dt
        self._deriv_filtered = (self.alpha * raw_deriv
                                + (1.0 - self.alpha) * self._deriv_filtered)
        d = self.kd * self._deriv_filtered
        self._meas_prev = measurement

        # --- Integrale (accumulo provvisorio) ---
        self._integral += self.ki * error * dt

        # --- Output raw e saturazione ---
        out_raw = p + self._integral + d
        out = _clamp(out_raw, -self.output_limit, self.output_limit)

        # --- Anti-windup a back-calculation ---
        # Se l'output è saturo, retrocede l'integrale in modo che
        # (p + I + d) tenda al valore saturato. Evita il windup.
        self._integral += (out - out_raw)

        # Memorizza componenti per test/debug
        self._p_term = p
        self._d_term = d

        return out

    # ------------------------------------------------------------------
    # Reset e accesso
    # ------------------------------------------------------------------
    def reset(self):
        """Azzera tutti gli stati interni (integrale, derivata, misura prev)."""
        self._integral = 0.0
        self._meas_prev = None
        self._deriv_filtered = 0.0
        self._p_term = 0.0
        self._d_term = 0.0

    @property
    def integral(self) -> float:
        """Valore corrente dell'integrale (read-only, per test/debug)."""
        return self._integral

    @property
    def p_term(self) -> float:
        return self._p_term

    @property
    def d_term(self) -> float:
        return self._d_term