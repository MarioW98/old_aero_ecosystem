"""
flight_controller/performance_spec.py

Definizione OGGETTIVA e CONFIGURABILE dei criteri di accettazione
del flight controller.

T0: il "se OK" del workflow non è più soggettivo. PerformanceSpec contiene
i target numerici (default aerospaziali, sovrascrivibili al bisogno per
velivolo / regime / punto di gain-scheduling); Metrics contiene i numeri
misurati o calcolati; evaluate() confronta e restituisce un verdetto
strutturato + report leggibile.

Nessuna dipendenza da pianta o simulazione: T0 è logica pura di confronto.
I numeri in Metrics saranno prodotti da T1 (analisi della pianta lineare)
o dalla validazione in simulazione.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CheckStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"   # metrica non ancora calcolata → non blocca


# ======================================================================
# SPECIFICA DI PRESTAZIONI (i tuoi target, configurabili)
# ======================================================================

@dataclass
class PerformanceSpec:
    """
    Target numerici di accettazione per un anello di controllo.

    Default = punto di partenza conservativo per un rate loop aerospaziale.
    Ogni campo è sovrascrivibile (dataclasses.replace o costruzione diretta),
    ad es. per velivoli aggressivi (bandwidth più alta) o per il punto di
    transizione di un tailsitter (margini più larghi).

    Convenzione direzioni:
    - *_min  → il valore misurato deve essere >= (più grande = meglio)
    - *_max  → il valore misurato deve essere <= (più piccolo = meglio)
    - damping → banda [zeta_min, zeta_max]: né sotto-smorzato né molle
    """
    label: str = "rate_loop_default"

    # Risposta temporale
    bandwidth_wn_min: float = 7.0          # rad/s (banda 5–10 tipica)
    damping_zeta_min: float = 0.5
    damping_zeta_max: float = 0.9
    overshoot_max_pct: float = 15.0        # %
    settling_time_2pct_max_s: float = 0.8  # s

    # Errore a regime (tracking del rate command)
    ss_rate_tracking_err_max_pct: float = 5.0  # %

    # Robustezza (margini di anello aperto)
    phase_margin_min_deg: float = 45.0     # °
    gain_margin_min_db: float = 6.0        # dB

    # Attuatori
    saturation_frac_max_pct: float = 20.0  # % di tempo in saturazione

    # Sicurezza
    divergence_allowed: bool = False       # True solo per test volutamente instabili


# ======================================================================
# METRICHE MISURATE / CALCOLATE
# ======================================================================

@dataclass
class Metrics:
    """
    Numeri di prestazione. I campi sono Optional: None = non ancora
    calcolato → la check corrispondente è PENDING (non FAIL).
    `diverged` è sempre noto (bool).
    """
    bandwidth_wn: Optional[float] = None
    damping_zeta: Optional[float] = None
    overshoot_pct: Optional[float] = None
    settling_time_2pct_s: Optional[float] = None
    ss_rate_tracking_err_pct: Optional[float] = None
    phase_margin_deg: Optional[float] = None
    gain_margin_db: Optional[float] = None
    saturation_frac_pct: Optional[float] = None
    diverged: bool = False


# ======================================================================
# RISULTATO DI UNA SINGOLA CHECK
# ======================================================================

@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    expected: str          # forma leggibile, es. "<= 15.0%"
    actual: str            # forma leggibile, es. "8.00%" o "n/d"
    limit: Optional[float] = None
    value: Optional[float] = None


# ======================================================================
# VERDETTO COMPLESSIVO
# ======================================================================

@dataclass
class GateResult:
    passed: bool                       # True se nessuna check è FAIL
    fully_evaluated: bool              # True se nessuna check è PENDING
    checks: list[CheckResult] = field(default_factory=list)
    report: str = ""

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def pending_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PENDING)


# ======================================================================
# VALUTAZIONE
# ======================================================================

def _fmt(v: Optional[float], unit: str) -> str:
    return "n/d" if v is None else f"{v:.2f}{unit}"


def _le(name: str, value: Optional[float], limit: float, unit: str) -> CheckResult:
    exp = f"<= {limit:g}{unit}"
    if value is None:
        return CheckResult(name, CheckStatus.PENDING, exp, "n/d", limit, None)
    ok = value <= limit
    return CheckResult(name, CheckStatus.PASS if ok else CheckStatus.FAIL,
                       exp, _fmt(value, unit), limit, value)


def _ge(name: str, value: Optional[float], limit: float, unit: str) -> CheckResult:
    exp = f">= {limit:g}{unit}"
    if value is None:
        return CheckResult(name, CheckStatus.PENDING, exp, "n/d", limit, None)
    ok = value >= limit
    return CheckResult(name, CheckStatus.PASS if ok else CheckStatus.FAIL,
                       exp, _fmt(value, unit), limit, value)


def _band(name: str, value: Optional[float], lo: float, hi: float,
          unit: str) -> CheckResult:
    exp = f"in [{lo:g}, {hi:g}]{unit}"
    if value is None:
        return CheckResult(name, CheckStatus.PENDING, exp, "n/d", None, None)
    ok = lo <= value <= hi
    return CheckResult(name, CheckStatus.PASS if ok else CheckStatus.FAIL,
                       exp, _fmt(value, unit), None, value)


def evaluate(spec: PerformanceSpec, metrics: Metrics) -> GateResult:
    """
    Confronta Metrics con PerformanceSpec.

    Verdetto: passed = nessuna check FAIL. Le PENDING non fanno fallire il
    gate ma lo rendono "non completo" (fully_evaluated=False), così il
    sistema è usabile incrementalmente mentre T1/T2 riempiono le metriche.
    """
    checks: list[CheckResult] = [
        _ge("Bandwidth ωn", metrics.bandwidth_wn,
            spec.bandwidth_wn_min, " rad/s"),
        _band("Smorzamento ζ", metrics.damping_zeta,
              spec.damping_zeta_min, spec.damping_zeta_max, ""),
        _le("Overshoot", metrics.overshoot_pct,
            spec.overshoot_max_pct, "%"),
        _le("Settling 2%", metrics.settling_time_2pct_s,
            spec.settling_time_2pct_max_s, " s"),
        _le("Err. regime rate", metrics.ss_rate_tracking_err_pct,
            spec.ss_rate_tracking_err_max_pct, "%"),
        _ge("Margine di fase", metrics.phase_margin_deg,
            spec.phase_margin_min_deg, "°"),
        _ge("Margine di guadagno", metrics.gain_margin_db,
            spec.gain_margin_min_db, " dB"),
        _le("Saturazione attuatori", metrics.saturation_frac_pct,
            spec.saturation_frac_max_pct, "%"),
    ]

    # Divergenza: check booleana, sempre nota
    if metrics.diverged and not spec.divergence_allowed:
        checks.append(CheckResult(
            "Divergenza", CheckStatus.FAIL,
            "nessuna divergenza", "DIVARGITO", None, None))
    else:
        checks.append(CheckResult(
            "Divergenza", CheckStatus.PASS,
            "nessuna divergenza", "assente", None, None))

    failed = [c for c in checks if c.status == CheckStatus.FAIL]
    pending = [c for c in checks if c.status == CheckStatus.PENDING]
    passed = len(failed) == 0
    fully = len(pending) == 0

    report = _build_report(spec, checks, passed, fully, len(failed), len(pending))
    return GateResult(passed=passed, fully_evaluated=fully,
                      checks=checks, report=report)


def _build_report(spec: PerformanceSpec, checks: list[CheckResult],
                  passed: bool, fully: bool,
                  n_fail: int, n_pending: int) -> str:
    lines = [
        "=" * 60,
        f"GATE DI ACCETTAZIONE — {spec.label}",
        "=" * 60,
    ]
    tag = {"PASS": "[ OK ]", "FAIL": "[FAIL]", "PENDING": "[ .... ]"}
    for c in checks:
        lines.append(f"  {tag[c.status.value]} {c.name:<22} "
                     f"{c.actual:>12}   (atteso {c.expected})")
    lines.append("-" * 60)
    if passed and fully:
        lines.append("ESITO: PASSO — tutti i criteri soddisfatti.")
    elif passed and not fully:
        lines.append(f"ESITO: PASSO PARZIALE — nessun fallimento, "
                     f"ma {n_pending} criteri in attesa di calcolo.")
    else:
        lines.append(f"ESITO: FALLITO — {n_fail} criteri non soddisfatti"
                     + (f", {n_pending} in attesa." if n_pending else "."))
    lines.append("=" * 60)
    return "\n".join(lines)