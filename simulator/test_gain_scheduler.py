"""
simulator/test_gain_scheduler.py

Test T3: Gain scheduling.
Verifica costruzione griglia, interpolazione, smoothing,
e gestione dei punti non trimmabili.

Uso:
    py -3.12 -m simulator.test_gain_scheduler
"""

import sys
import math
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent
ROOT = SIM_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM_DIR))

from aircraft.c172 import make_c172_aircraft
from flight_controller.fc_config import ActuatorLimits
from flight_controller.performance_spec import PerformanceSpec
from flight_controller.gain_scheduler import (
    GainScheduleGrid, GainScheduler, SchedulePoint,
)
from flight_controller.rate_controller import RateController


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


_CFG = None
_GRID = None
_LIMITS = None
_SPEC = None


def _get_grid():
    """Costruisce (una sola volta) una griglia 3×2 per il C172."""
    global _CFG, _GRID, _LIMITS, _SPEC
    if _GRID is not None:
        return _GRID

    _CFG = make_c172_aircraft()
    _LIMITS = ActuatorLimits(
        max_delta_a=0.35, max_delta_e=0.40, max_delta_r=0.35)
    _SPEC = PerformanceSpec(label="grid_test")

    grid = GainScheduleGrid()
    grid.build(
        _CFG,
        V_values=[42.0, 45.0, 50.0],
        alt_values=[0.0, 1000.0],
        spec=_SPEC,
        limits=_LIMITS,
        dt=0.02,
    )
    _GRID = grid
    return grid


# ======================================================================
# TEST 1 — Costruzione griglia
# ======================================================================

def test_grid_construction():
    grid = _get_grid()
    check(grid.total_count == 6,
          f"griglia 3×2 = 6 punti, trovato {grid.total_count}")
    check(grid.valid_count >= 4,
          f"almeno 4 punti validi, trovati {grid.valid_count}")
    check(grid.coverage_pct > 50.0,
          f"copertura > 50%, trovata {grid.coverage_pct:.0f}%")
    check(grid.limits is not None, "limits salvati nella griglia")


# ======================================================================
# TEST 2 — Lookup esatto ai punti della griglia
# ======================================================================

def test_exact_lookup():
    grid = _get_grid()

    for i, V in enumerate(grid.V_values):
        for j, alt in enumerate(grid.alt_values):
            point = grid.grid.get((i, j))
            if point is None or not point.valid:
                continue

            config = grid.interpolate(V, alt)
            check(config is not None,
                  f"config non None a V={V}, alt={alt}")
            check(config.roll.kp > 0,
                  f"roll Kp > 0 a V={V}, alt={alt}")
            check(config.pitch.kp > 0,
                  f"pitch Kp > 0 a V={V}, alt={alt}")
            check(config.yaw.kp > 0,
                  f"yaw Kp > 0 a V={V}, alt={alt}")


# ======================================================================
# TEST 3 — Interpolazione tra punti della griglia
# ======================================================================

def test_interpolation_between_points():
    grid = _get_grid()

    # Punto intermedio tra V=42 e V=45, alt=0
    V_mid = 0.5 * (grid.V_values[0] + grid.V_values[1])
    config = grid.interpolate(V_mid, 0.0)

    check(config is not None,
          "config interpolato non None")
    check(config.roll.kp > 0, "roll Kp > 0 interpolato")
    check(config.pitch.kp > 0, "pitch Kp > 0 interpolato")
    check(config.yaw.kp > 0, "yaw Kp > 0 interpolato")

    # I guadagni interpolati devono essere tra quelli dei vertici
    c_lo = grid.interpolate(grid.V_values[0], 0.0)
    c_hi = grid.interpolate(grid.V_values[1], 0.0)

    if c_lo is not None and c_hi is not None:
        lo_kp = min(c_lo.pitch.kp, c_hi.pitch.kp)
        hi_kp = max(c_lo.pitch.kp, c_hi.pitch.kp)
        mid_kp = config.pitch.kp
        check(lo_kp - 1e-6 <= mid_kp <= hi_kp + 1e-6,
              f"Kp interpolato in [{lo_kp:.4f}, {hi_kp:.4f}], "
              f"trovato {mid_kp:.4f}")


# ======================================================================
# TEST 4 — Clamping ai bordi della griglia
# ======================================================================

def test_clamping_at_boundaries():
    grid = _get_grid()

    # V sotto il minimo → clamp al minimo
    config_low = grid.interpolate(10.0, 0.0)
    config_min = grid.interpolate(grid.V_values[0], 0.0)
    if config_low is not None and config_min is not None:
        check(abs(config_low.pitch.kp - config_min.pitch.kp) < 1e-6,
              "V sotto min → clamp al min")

    # V sopra il massimo → clamp al massimo
    config_high = grid.interpolate(100.0, 0.0)
    config_max = grid.interpolate(grid.V_values[-1], 0.0)
    if config_high is not None and config_max is not None:
        check(abs(config_high.pitch.kp - config_max.pitch.kp) < 1e-6,
              "V sopra max → clamp al max")


# ======================================================================
# TEST 5 — GainScheduler con smoothing
# ======================================================================

def test_gain_scheduler_smoothing():
    grid = _get_grid()
    scheduler = GainScheduler(grid, smoothing_alpha=0.1)

    # Primo aggiornamento: nessun smoothing (config iniziale)
    c1 = scheduler.update(42.0, 0.0)
    check(c1 is not None, "primo aggiornamento non None")

    # Secondo aggiornamento a condizione diversa
    c2 = scheduler.update(50.0, 0.0)
    check(c2 is not None, "secondo aggiornamento non None")

    # Con smoothing, c2 deve essere diverso dal target puro
    target = grid.interpolate(50.0, 0.0)
    if target is not None and c2 is not None:
        # c2 dovrebbe essere tra c1 e target (smoothing)
        # Verifica che non sia esattamente uguale al target
        diff = abs(c2.pitch.kp - target.pitch.kp)
        check(diff > 1e-9 or abs(c1.pitch.kp - target.pitch.kp) < 1e-9,
              "smoothing produce transizione graduale")

    # Dopo molti aggiornamenti, converge al target
    for _ in range(200):
        c = scheduler.update(50.0, 0.0)
    if c is not None and target is not None:
        check(abs(c.pitch.kp - target.pitch.kp) < 1e-4,
              "dopo molti step, converge al target")


def test_gain_scheduler_reset():
    grid = _get_grid()
    scheduler = GainScheduler(grid, smoothing_alpha=0.1)

    scheduler.update(42.0, 0.0)
    check(scheduler.current_config is not None,
          "config presente dopo update")

    scheduler.reset()
    check(scheduler.current_config is None,
          "config None dopo reset")


# ======================================================================
# TEST 6 — Integrazione con RateController.update_gains
# ======================================================================

def test_rate_controller_update_gains():
    grid = _get_grid()

    # Crea un RateController con i guadagni del primo punto valido
    config = grid.interpolate(grid.V_values[0], 0.0)
    if config is None:
        print("SKIP: nessun punto valido per il test")
        return

    rc = RateController(config)

    # Aggiorna con guadagni di un altro punto
    config2 = grid.interpolate(grid.V_values[-1], 0.0)
    if config2 is None:
        print("SKIP: nessun secondo punto valido")
        return

    rc.update_gains(config2)

    check(abs(rc._pid_pitch.kp - config2.pitch.kp) < 1e-9,
          "update_gains aggiorna Kp pitch")
    check(abs(rc._pid_roll.ki - config2.roll.ki) < 1e-9,
          "update_gains aggiorna Ki roll")
    check(rc.config is config2,
          "update_gains aggiorna il riferimento config")


# ======================================================================
# TEST 7 — Summary
# ======================================================================

def test_summary():
    grid = _get_grid()
    s = grid.summary()
    check("GAIN SCHEDULE GRID" in s, "summary ha header")
    check("V range" in s, "summary ha V range")
    check("OK" in s or "FAIL" in s, "summary ha stato punti")


# ======================================================================
# MAIN + DIAGNOSTICA
# ======================================================================

def main():
    test_grid_construction()
    test_exact_lookup()
    test_interpolation_between_points()
    test_clamping_at_boundaries()
    test_gain_scheduler_smoothing()
    test_gain_scheduler_reset()
    test_rate_controller_update_gains()
    test_summary()

    # ------------------------------------------------------------------
    # Diagnostica
    # ------------------------------------------------------------------
    grid = _get_grid()

    print()
    print(grid.summary())
    print()

    # Mostra guadagni interpolati lungo una scansione di V
    print("Scansione V a quota 0:")
    print(f"  {'V':>6}  {'Kp_pitch':>10}  {'Ki_pitch':>10}  "
          f"{'Kd_pitch':>10}  {'trim_de':>10}")
    print("  " + "-" * 54)

    for V in [v * 1.0 for v in range(40, 56, 2)]:
        config = grid.interpolate(V, 0.0)
        if config is None:
            print(f"  {V:6.1f}  {'n/a':>10}  {'n/a':>10}  "
                  f"{'n/a':>10}  {'n/a':>10}")
        else:
            print(f"  {V:6.1f}  {config.pitch.kp:10.4f}  "
                  f"{config.pitch.ki:10.4f}  "
                  f"{config.pitch.kd:10.5f}  "
                  f"{config.trim_delta_e:10.4f}")

    print()
    print("PASS: T3 gain scheduling corretto")


if __name__ == "__main__":
    main()


'''
NOTE
1. Trim fallito a quota 1000 (V=42, V=45):
A livello del mare il trim a V=42 richiede già thr=0.916 — il modello 
di propulsione è vicino al limite. A 1000 m la densità cala 
(~1.112 vs 1.225 kg/m³), la spinta disponibile scende, e il throttle 
richiesto supera 1.0. È un limite fisico del modello, non del codice. 
Il gain scheduler lo gestisce correttamente marcando il punto invalido.
2. Interpolazione a gradini nella scansione:
è una conseguenza del punto 1. L'interpolazione bilineare richiede 
tutti e 4 i vertici della cella validi. Poiché la riga alt=1000 ha 
dei buchi, il metodo degrada a nearest-neighbor anche a alt=0. 
Il comportamento è conservativo e sicuro, ma migliorabile.
3. Il valore thr=0.916 a crociera è irrealistico per un C172 reale 
(sarebbe ~0.4-0.5). Questo indica che il modello di drag o la potenza 
del motore nel simulatore andrebbero rivisti. È un problema di Fase 1 
(simulatore), non del flight controller. Lo segnalo per il futuro.
'''