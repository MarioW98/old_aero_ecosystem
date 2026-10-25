"""
flight_controller/gain_scheduler.py

Gain scheduling: griglia di punti di volo → tabella di guadagni PID.

T3. Costruisce una griglia 2D (V × quota) di punti di volo, sintetizza
i guadagni PID in ogni punto (riusando T1+T2), e fornisce interpolazione
bilineare per selezionare i guadagni in tempo reale.

Struttura:
- SchedulePoint: un singolo punto della griglia
- GainScheduleGrid: costruzione e query della griglia
- GainScheduler: wrapper runtime con smoothing

Il gain scheduling è necessario perché la pianta del rate loop cambia
con V, quota, e α. Un singolo set di guadagni è valido solo in un
intorno del punto di trim. Su tutto l'inviluppo, servono guadagni
diversi per ogni condizione di volo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

from .plant import RatePlantBundle, extract_rate_plant
from .fc_config import AxisGains, RateConfig, ActuatorLimits
from .performance_spec import PerformanceSpec
from .synthesis import synthesize_full_rate_config


# ======================================================================
# SINGOLO PUNTO DELLA GRIGLIA
# ======================================================================

@dataclass
class SchedulePoint:
    """Un singolo punto della griglia di gain scheduling."""
    V: float
    altitude: float
    valid: bool = False
    bundle: Optional[RatePlantBundle] = None
    gains: Dict[str, AxisGains] = field(default_factory=dict)
    trim_delta_e: float = 0.0
    trim_delta_a: float = 0.0
    trim_delta_r: float = 0.0
    sign_roll: float = 1.0
    sign_pitch: float = -1.0
    sign_yaw: float = 1.0
    message: str = ""


# ======================================================================
# GRIGLIA DI GAIN SCHEDULING
# ======================================================================

class GainScheduleGrid:
    """
    Griglia 2D di guadagni PID pre-calcolati.

    Dimensioni: V × quota.
    Ogni punto contiene i guadagni sintetizzati per tutti e tre gli assi.

    Uso:
        grid = GainScheduleGrid()
        grid.build(aircraft_config, V_values, alt_values, spec, limits)
        config = grid.interpolate(V=45.0, altitude=500.0)
    """

    def __init__(self):
        self.V_values: List[float] = []
        self.alt_values: List[float] = []
        self.grid: Dict[Tuple[int, int], SchedulePoint] = {}
        self.limits: Optional[ActuatorLimits] = None
        self.deriv_filter_alpha: float = 0.5

    # ------------------------------------------------------------------
    # COSTRUZIONE
    # ------------------------------------------------------------------

    def build(
        self,
        aircraft_config,
        V_values: List[float],
        alt_values: List[float],
        spec: PerformanceSpec,
        limits: ActuatorLimits,
        dt: float = 0.02,
        alpha_deriv: float = 0.5,
        kd_ratio: float = 0.15,
        q_cmd_step: float = 0.1,
    ) -> None:
        """
        Costruisce la griglia sintetizzando guadagni in ogni punto.

        Args:
            aircraft_config: AircraftConfig del velivolo.
            V_values: Lista di velocità [m/s] per la griglia.
            alt_values: Lista di quote [m] per la griglia.
            spec: PerformanceSpec per la sintesi.
            limits: ActuatorLimits del velivolo.
            dt, alpha_deriv, kd_ratio, q_cmd_step: parametri di sintesi.
        """
        self.V_values = sorted(set(V_values))
        self.alt_values = sorted(set(alt_values))
        self.limits = limits
        self.deriv_filter_alpha = alpha_deriv
        self.grid.clear()

        for i, V in enumerate(self.V_values):
            for j, alt in enumerate(self.alt_values):
                point = self._build_point(
                    aircraft_config, V, alt, spec, limits,
                    dt, alpha_deriv, kd_ratio, q_cmd_step,
                )
                self.grid[(i, j)] = point

    def _build_point(
        self, aircraft_config, V, alt, spec, limits,
        dt, alpha_deriv, kd_ratio, q_cmd_step,
    ) -> SchedulePoint:
        """Costruisce un singolo punto della griglia."""
        try:
            bundle = extract_rate_plant(
                aircraft_config, V, alt, strict=False)

            if bundle is None:
                return SchedulePoint(
                    V=V, altitude=alt, valid=False,
                    message="Trim non converguto",
                )

            config, results = synthesize_full_rate_config(
                bundle, spec, limits,
                dt=dt, alpha_deriv=alpha_deriv,
                kd_ratio=kd_ratio, q_cmd_step=q_cmd_step,
            )

            all_pass = all(r.success for r in results.values())

            return SchedulePoint(
                V=V, altitude=alt,
                valid=all_pass,
                bundle=bundle,
                gains={
                    "roll": config.roll,
                    "pitch": config.pitch,
                    "yaw": config.yaw,
                },
                trim_delta_e=config.trim_delta_e,
                trim_delta_a=config.trim_delta_a,
                trim_delta_r=config.trim_delta_r,
                sign_roll=config.sign_roll,
                sign_pitch=config.sign_pitch,
                sign_yaw=config.sign_yaw,
                message="" if all_pass else "Alcuni assi non passano il gate",
            )

        except Exception as e:
            return SchedulePoint(
                V=V, altitude=alt, valid=False,
                message=f"Errore: {e}",
            )

    # ------------------------------------------------------------------
    # QUERY — INTERPOLAZIONE
    # ------------------------------------------------------------------

    def _find_cell(
        self, V: float, altitude: float
    ) -> Tuple[int, int, float, float]:
        """
        Trova la cella della griglia contenente (V, altitude).
        Ritorna (i, j, tV, ta) dove tV e ta sono i pesi di interpolazione
        in [0, 1].
        """
        V = max(self.V_values[0], min(V, self.V_values[-1]))
        altitude = max(self.alt_values[0], min(altitude, self.alt_values[-1]))

        # Find V index
        i = len(self.V_values) - 2
        for k in range(len(self.V_values) - 1):
            if self.V_values[k] <= V <= self.V_values[k + 1]:
                i = k
                break

        # Find alt index
        j = len(self.alt_values) - 2
        for k in range(len(self.alt_values) - 1):
            if self.alt_values[k] <= altitude <= self.alt_values[k + 1]:
                j = k
                break

        # Interpolation weights
        V0 = self.V_values[i]
        V1 = self.V_values[min(i + 1, len(self.V_values) - 1)]
        a0 = self.alt_values[j]
        a1 = self.alt_values[min(j + 1, len(self.alt_values) - 1)]

        tV = (V - V0) / (V1 - V0) if V1 != V0 else 0.0
        ta = (altitude - a0) / (a1 - a0) if a1 != a0 else 0.0

        tV = max(0.0, min(1.0, tV))
        ta = max(0.0, min(1.0, ta))

        return i, j, tV, ta

    def get_nearest_valid(
        self, V: float, altitude: float
    ) -> Optional[SchedulePoint]:
        """Ritorna il punto valido più vicino a (V, altitude)."""
        best = None
        best_dist = float('inf')

        V_span = max(
            abs(self.V_values[-1] - self.V_values[0]), 1e-9)
        a_span = max(
            abs(self.alt_values[-1] - self.alt_values[0]), 1e-9)

        for point in self.grid.values():
            if not point.valid:
                continue
            dV = (point.V - V) / V_span
            da = (point.altitude - altitude) / a_span
            dist = dV * dV + da * da
            if dist < best_dist:
                best_dist = dist
                best = point

        return best

    def interpolate(
        self, V: float, altitude: float
    ) -> Optional[RateConfig]:
        """
        Interpola i guadagni per la condizione di volo (V, altitude).

        Usa interpolazione bilineare se tutti e 4 i vertici della cella
        sono validi. Altrimenti, usa il punto valido più vicino.

        Returns:
            RateConfig interpolato, o None se nessun punto valido.
        """
        if not self.grid:
            return None

        i, j, tV, ta = self._find_cell(V, altitude)

        i1 = min(i + 1, len(self.V_values) - 1)
        j1 = min(j + 1, len(self.alt_values) - 1)

        corners = [
            self.grid.get((i, j)),
            self.grid.get((i1, j)),
            self.grid.get((i, j1)),
            self.grid.get((i1, j1)),
        ]

        # Bilinear if all corners valid
        if all(c is not None and c.valid for c in corners):
            return self._bilinear_interp(corners, tV, ta)

        # Fallback: nearest valid
        nearest = self.get_nearest_valid(V, altitude)
        if nearest is None:
            return None
        return self._point_to_config(nearest)

    def _bilinear_interp(
        self, corners: List[SchedulePoint], tV: float, ta: float
    ) -> RateConfig:
        """Interpolazione bilineare dei guadagni dai 4 vertici."""
        g00, g10, g01, g11 = corners

        def lerp(a, b, t):
            return a + t * (b - a)

        def bilerp(v00, v10, v01, v11):
            return lerp(lerp(v00, v10, tV), lerp(v01, v11, tV), ta)

        def interp_axis(a00, a10, a01, a11):
            return AxisGains(
                kp=bilerp(a00.kp, a10.kp, a01.kp, a11.kp),
                ki=bilerp(a00.ki, a10.ki, a01.ki, a11.ki),
                kd=bilerp(a00.kd, a10.kd, a01.kd, a11.kd),
            )

        roll = interp_axis(
            g00.gains["roll"], g10.gains["roll"],
            g01.gains["roll"], g11.gains["roll"])
        pitch = interp_axis(
            g00.gains["pitch"], g10.gains["pitch"],
            g01.gains["pitch"], g11.gains["pitch"])
        yaw = interp_axis(
            g00.gains["yaw"], g10.gains["yaw"],
            g01.gains["yaw"], g11.gains["yaw"])

        return RateConfig(
            roll=roll, pitch=pitch, yaw=yaw,
            limits=self.limits,
            trim_delta_e=bilerp(
                g00.trim_delta_e, g10.trim_delta_e,
                g01.trim_delta_e, g11.trim_delta_e),
            trim_delta_a=bilerp(
                g00.trim_delta_a, g10.trim_delta_a,
                g01.trim_delta_a, g11.trim_delta_a),
            trim_delta_r=bilerp(
                g00.trim_delta_r, g10.trim_delta_r,
                g01.trim_delta_r, g11.trim_delta_r),
            sign_roll=g00.sign_roll,
            sign_pitch=g00.sign_pitch,
            sign_yaw=g00.sign_yaw,
            deriv_filter_alpha=self.deriv_filter_alpha,
        )

    def _point_to_config(self, point: SchedulePoint) -> RateConfig:
        """Converte un SchedulePoint in RateConfig."""
        return RateConfig(
            roll=point.gains["roll"],
            pitch=point.gains["pitch"],
            yaw=point.gains["yaw"],
            limits=self.limits,
            trim_delta_e=point.trim_delta_e,
            trim_delta_a=point.trim_delta_a,
            trim_delta_r=point.trim_delta_r,
            sign_roll=point.sign_roll,
            sign_pitch=point.sign_pitch,
            sign_yaw=point.sign_yaw,
            deriv_filter_alpha=self.deriv_filter_alpha,
        )

    # ------------------------------------------------------------------
    # DIAGNOSTICA
    # ------------------------------------------------------------------

    @property
    def total_count(self) -> int:
        return len(self.grid)

    @property
    def valid_count(self) -> int:
        return sum(1 for p in self.grid.values() if p.valid)

    @property
    def coverage_pct(self) -> float:
        if self.total_count == 0:
            return 0.0
        return 100.0 * self.valid_count / self.total_count

    def summary(self) -> str:
        """Ritorna una tabella riassuntiva della griglia."""
        lines = [
            "=" * 60,
            "GAIN SCHEDULE GRID",
            "=" * 60,
            f"V range: {self.V_values[0]:.0f} .. {self.V_values[-1]:.0f} m/s "
            f"({len(self.V_values)} punti)",
            f"Alt range: {self.alt_values[0]:.0f} .. "
            f"{self.alt_values[-1]:.0f} m ({len(self.alt_values)} punti)",
            f"Totale: {self.total_count} punti, "
            f"validi: {self.valid_count} ({self.coverage_pct:.0f}%)",
            "-" * 60,
        ]

        for i, V in enumerate(self.V_values):
            for j, alt in enumerate(self.alt_values):
                p = self.grid.get((i, j))
                if p is None:
                    status = "MISSING"
                elif p.valid:
                    status = "OK"
                else:
                    status = f"FAIL ({p.message})"
                lines.append(
                    f"  V={V:5.1f}  alt={alt:5.0f}  [{status}]")

        lines.append("=" * 60)
        return "\n".join(lines)


# ======================================================================
# SCHEDULER RUNTIME CON SMOOTHING
# ======================================================================

class GainScheduler:
    """
    Scheduler runtime con smoothing esponenziale.

    Wrappa GainScheduleGrid e fornisce transizioni fluide dei guadagni
    quando la condizione di volo cambia. Previene salti bruschi che
    potrebbero destabilizzare l'anello chiuso.

    Uso nel loop di simulazione (50 Hz):
        scheduler = GainScheduler(grid, smoothing_alpha=0.05)
        config = scheduler.update(V=airspeed, altitude=alt)
        rate_controller.update_gains(config)
    """

    def __init__(self, grid: GainScheduleGrid,
                 smoothing_alpha: float = 0.05):
        """
        Args:
            grid: GainScheduleGrid pre-costruita.
            smoothing_alpha: Coefficiente di smoothing [0, 1].
                            0 = nessun cambiamento, 1 = istantaneo.
                            Tipico: 0.02–0.1.
        """
        self.grid = grid
        self.alpha = max(0.0, min(1.0, smoothing_alpha))
        self._current_config: Optional[RateConfig] = None

    def update(self, V: float, altitude: float) -> Optional[RateConfig]:
        """
        Aggiorna i guadagni per la condizione di volo corrente.

        Args:
            V: Velocità corrente [m/s].
            altitude: Quota corrente [m].

        Returns:
            RateConfig smorzato, o None se nessun punto valido.
        """
        target = self.grid.interpolate(V, altitude)

        if target is None:
            return self._current_config

        if self._current_config is None:
            self._current_config = target
            return target

        self._current_config = self._smooth(
            self._current_config, target)
        return self._current_config

    def _smooth(self, current: RateConfig,
                target: RateConfig) -> RateConfig:
        """Smoothing esponenziale sui guadagni."""
        a = self.alpha

        def lerp(cur, tgt):
            return cur + a * (tgt - cur)

        def smooth_axis(cur, tgt):
            return AxisGains(
                kp=lerp(cur.kp, tgt.kp),
                ki=lerp(cur.ki, tgt.ki),
                kd=lerp(cur.kd, tgt.kd),
            )

        return RateConfig(
            roll=smooth_axis(current.roll, target.roll),
            pitch=smooth_axis(current.pitch, target.pitch),
            yaw=smooth_axis(current.yaw, target.yaw),
            limits=target.limits,
            trim_delta_e=lerp(
                current.trim_delta_e, target.trim_delta_e),
            trim_delta_a=lerp(
                current.trim_delta_a, target.trim_delta_a),
            trim_delta_r=lerp(
                current.trim_delta_r, target.trim_delta_r),
            sign_roll=target.sign_roll,
            sign_pitch=target.sign_pitch,
            sign_yaw=target.sign_yaw,
            deriv_filter_alpha=target.deriv_filter_alpha,
        )

    def reset(self):
        """Reset dello stato di smoothing."""
        self._current_config = None

    @property
    def current_config(self) -> Optional[RateConfig]:
        return self._current_config