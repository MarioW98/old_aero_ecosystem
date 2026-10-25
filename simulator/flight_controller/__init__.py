"""
flight_controller/

Flight Controller Python, modulare e riusabile (futuro hardware).

Struttura (Fase 2, approccio model-based):
- pid.py                 : controllore PID generico
- rate_controller.py     : inner loop — rate (p,q,r) → superfici
- attitude_controller.py : middle loop — angle → rate
- fc_config.py           : dataclass contenitore dei parametri
- performance_spec.py    : T0 — gate di accettazione oggettivo
- trim_solver.py         : T1 — trim di volo livellato
- plant.py               : T1 — estrazione pianta rate loop
- analysis.py            : T1 — margini e metriche sulla linearizzazione
- synthesis.py           : T2 — sintesi automatica guadagni PID

I guadagni NON sono hardcoded: T1 estrae la pianta, T2 sintetizza.
"""

from .pid import PIDController
from .rate_controller import RateController
from .attitude_controller import AttitudeController, AttitudeConfig
from .fc_config import RateConfig, AxisGains, ActuatorLimits
from .performance_spec import (
    PerformanceSpec, Metrics, GateResult, CheckResult, CheckStatus, evaluate,
)
from .trim_solver import TrimSolver, TrimResult
from .plant import AxisPlant, RatePlantBundle, extract_rate_plant
from .analysis import closed_loop_metrics, open_loop_margins, derivative_filter_cutoff
from .synthesis import (
    SynthesisResult,
    synthesize_rate_gains,
    synthesize_full_rate_config,
    make_spec_from_aggressiveness,
)
from .gain_scheduler import (
    SchedulePoint, GainScheduleGrid, GainScheduler,
)

from .sysid import (
    SysIdResult,
    identify_first_order,
    make_step_signal,
    make_prbs_signal,
    sysid_rate_loop,
)