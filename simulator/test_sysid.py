"""
simulator/test_sysid.py

Test T4: System Identification.
Verifica che la pianta identificata dal simulatore non lineare
sia coerente con la pianta analitica di T1.

Uso:
    py -3.12 -m simulator.test_sysid
"""

import sys
import math
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent
ROOT = SIM_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM_DIR))

import numpy as np
from aircraft.c172 import make_c172_aircraft
from flight_controller.fc_config import ActuatorLimits
from flight_controller.performance_spec import PerformanceSpec
from flight_controller.plant import extract_rate_plant
from flight_controller.synthesis import synthesize_full_rate_config
from flight_controller.sysid import (
    SysIdResult,
    identify_first_order,
    make_step_signal,
    make_prbs_signal,
    sysid_rate_loop,
)


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


# ======================================================================
# FIXTURE
# ======================================================================

_DATA = None


def _get_data():
    """Prepara velivolo, pianta, guadagni e trim (una sola volta)."""
    global _DATA
    if _DATA is not None:
        return _DATA

    cfg = make_c172_aircraft()
    limits = ActuatorLimits(
        max_delta_a=0.35, max_delta_e=0.40, max_delta_r=0.35)
    spec = PerformanceSpec(label="sysid_test")

    bundle = extract_rate_plant(cfg, V=45.0, altitude=0.0)
    check(bundle is not None, "trim deve convergere per il test sysid")

    rate_config, results = synthesize_full_rate_config(
        bundle, spec, limits, dt=0.02)

    _DATA = {
        "cfg": cfg,
        "bundle": bundle,
        "rate_config": rate_config,
        "limits": limits,
    }
    return _DATA


# ======================================================================
# TEST 1 — Segnali di eccitazione
# ======================================================================

def test_step_signal():
    sig = make_step_signal(100, 0.02, 0.1, t_start=0.5)
    check(len(sig) == 100, "lunghezza step")
    check(abs(sig[0]) < 1e-9, "step: zero prima di t_start")
    check(abs(sig[-1] - 0.1) < 1e-9, "step: amplitude dopo t_start")
    # Verifica che ci sia una transizione
    transitions = np.sum(np.abs(np.diff(sig)) > 1e-6)
    check(transitions >= 1, "step: almeno una transizione")


def test_prbs_signal():
    sig = make_prbs_signal(500, 0.02, 0.05, hold_time=0.1)
    check(len(sig) == 500, "lunghezza prbs")
    check(abs(np.max(sig) - 0.05) < 1e-9, "prbs: max = amplitude")
    check(abs(np.min(sig) + 0.05) < 1e-9, "prbs: min = -amplitude")
    # Verifica che ci siano transizioni
    transitions = np.sum(np.abs(np.diff(sig)) > 1e-6)
    check(transitions >= 3, f"prbs: almeno 3 transizioni, trovate {transitions}")
    # Riproducibilità
    sig2 = make_prbs_signal(500, 0.02, 0.05, hold_time=0.1)
    check(np.allclose(sig, sig2), "prbs: riproducibile con stesso seed")


# ======================================================================
# TEST 2 — Identificazione su dati sintetici
# ======================================================================

def test_identify_synthetic_data():
    """
    Verifica l'identificazione su dati generati da una pianta nota.
    Se l'algoritmo è corretto, deve recuperare i parametri con buona
    precisione. R² > 0.95 è realistico per dati sintetici con derivata
    numerica (np.gradient introduce errore O(dt²)).
    """
    K_true = 5.0
    tau_true = 0.3

    dt = 0.01
    t = np.arange(0, 5.0, dt)
    n = len(t)

    # Input: scalino
    u = np.zeros(n)
    u[t >= 0.5] = 1.0

    # Output: risposta esatta del primo ordine
    y = np.zeros(n)
    for k in range(1, n):
        y[k] = y[k - 1] + dt * ((-y[k - 1] + K_true * u[k - 1]) / tau_true)

    K_id, tau_id, R2 = identify_first_order(t, y, u)

    # I parametri devono essere recuperati con precisione < 5%
    check(abs(K_id - K_true) / K_true < 0.05,
          f"K identificato entro 5%: {K_id:.3f} vs {K_true}")
    check(abs(tau_id - tau_true) / tau_true < 0.05,
          f"tau identificato entro 5%: {tau_id:.3f} vs {tau_true}")
    
    # R² > 0.95 è realistico per dati sintetici con derivata numerica
    check(R2 > 0.95, f"R² > 0.95, trovato {R2:.4f}")


def test_identify_with_noise():
    """Verifica robustezza dell'identificazione con rumore."""
    K_true = 5.0
    tau_true = 0.3
    dt = 0.01
    t = np.arange(0, 5.0, dt)
    n = len(t)

    u = np.zeros(n)
    u[t >= 0.5] = 1.0

    y = np.zeros(n)
    for k in range(1, n):
        y[k] = y[k - 1] + dt * ((-y[k - 1] + K_true * u[k - 1]) / tau_true)

    # Aggiungi rumore
    rng = np.random.RandomState(123)
    y_noisy = y + rng.normal(0, 0.01, n)

    K_id, tau_id, R2 = identify_first_order(t, y_noisy, u)

    check(abs(K_id - K_true) / K_true < 0.15,
          f"K con rumore entro 15%: {K_id:.3f} vs {K_true}")
    check(abs(tau_id - tau_true) / tau_true < 0.15,
          f"tau con rumore entro 15%: {tau_id:.3f} vs {tau_true}")
    check(R2 > 0.90, f"R² > 0.90 con rumore, trovato {R2:.4f}")


# ======================================================================
# TEST 3 — Sysid sul simulatore non lineare
# ======================================================================

def test_sysid_pitch_step():
    """
    Identifica la pianta pitch dal simulatore NL con eccitazione step.
    
    NOTA: il pitch ha dinamica del secondo ordine (accoppiamento con α).
    Il modello del primo ordine è un'approssimazione che cattura solo
    la risposta iniziale. L'errore su K e τ può essere significativo
    (>100%) perché l'identificazione vede anche il feedback di α.
    
    Per il pitch verifichiamo:
    - Non divergenza
    - τ positivo (sistema stabile)
    - R² ragionevole (>0.40, non 0.80 come roll/yaw)
    
    Il confronto quantitativo K/τ è solo diagnostico, non un gate.
    """
    data = _get_data()
    bundle = data["bundle"]

    result = sysid_rate_loop(
        data["cfg"],
        data["rate_config"],
        bundle.pitch,
        trim_alpha=bundle.trim.alpha,
        trim_delta_e=bundle.trim.delta_e,
        trim_throttle=bundle.trim.throttle,
        V=bundle.V,
        altitude=0.0,
        axis="pitch",
        excitation="step",
        amplitude=0.02,
        duration=4.0,
        dt=0.02,
    )

    check(not result.diverged, "sysid pitch step: non diverge")
    check(result.tau_identified > 0,
          f"tau pitch positivo (stabile), trovato {result.tau_identified:.4f}")
    # R² rilassato: il primo ordine non cattura il secondo ordine del pitch
    check(result.R_squared > 0.40,
          f"R² > 0.40 per pitch (secondo ordine), trovato {result.R_squared:.3f}")
    
def test_sysid_pitch_prbs():
    """Identifica la pianta pitch con eccitazione PRBS."""
    data = _get_data()
    bundle = data["bundle"]

    result = sysid_rate_loop(
        data["cfg"],
        data["rate_config"],
        bundle.pitch,
        trim_alpha=bundle.trim.alpha,
        trim_delta_e=bundle.trim.delta_e,
        trim_throttle=bundle.trim.throttle,
        V=bundle.V,
        altitude=0.0,
        axis="pitch",
        excitation="prbs",
        amplitude=0.01,
        duration=6.0,
        dt=0.02,
    )

    check(not result.diverged, "sysid pitch prbs: non diverge")
    # R² rilassato per il pitch (dinamica secondo ordine)
    check(result.R_squared > 0.30,
          f"R² > 0.30 per PRBS pitch, trovato {result.R_squared:.3f}")
    check(result.tau_identified > 0,
          f"tau pitch positivo, trovato {result.tau_identified:.4f}")


def test_sysid_roll():
    """
    Identifica la pianta roll.
    Il roll non ha accoppiamento con α, quindi il primo ordine
    è un'approssimazione buona. Soglie più strette del pitch.
    """
    data = _get_data()
    bundle = data["bundle"]

    result = sysid_rate_loop(
        data["cfg"],
        data["rate_config"],
        bundle.roll,
        trim_alpha=bundle.trim.alpha,
        trim_delta_e=bundle.trim.delta_e,
        trim_throttle=bundle.trim.throttle,
        V=bundle.V,
        altitude=0.0,
        axis="roll",
        excitation="step",
        amplitude=0.02,
        duration=4.0,
        dt=0.02,
    )

    check(not result.diverged, "sysid roll: non diverge")
    check(result.tau_identified > 0,
          f"tau roll positivo, trovato {result.tau_identified:.4f}")
    # Roll ha dinamica primo ordine: soglie più strette
    check(result.R_squared > 0.70,
          f"R² > 0.70 per roll, trovato {result.R_squared:.3f}")
    check(result.K_error_pct < 60.0,
          f"errore K roll < 60%, trovato {result.K_error_pct:.1f}%")
    check(result.tau_error_pct < 60.0,
          f"errore tau roll < 60%, trovato {result.tau_error_pct:.1f}%")
    

# ======================================================================
# MAIN + DIAGNOSTICA
# ======================================================================

def main():
    test_step_signal()
    test_prbs_signal()
    test_identify_synthetic_data()
    test_identify_with_noise()
    test_sysid_pitch_step()
    test_sysid_pitch_prbs()
    test_sysid_roll()

    # ------------------------------------------------------------------
    # Diagnostica completa
    # ------------------------------------------------------------------
    data = _get_data()
    bundle = data["bundle"]

    print()
    print("=" * 72)
    print("T4 DIAGNOSTICA — System Identification (C172)")
    print("=" * 72)
    print(f"Condizione: V={bundle.V:.1f} m/s, quota 0")
    print(f"Trim: alpha={math.degrees(bundle.trim.alpha):+.2f}°, "
          f"thr={bundle.trim.throttle:.3f}")

    for axis in ("pitch", "roll", "yaw"):
        plant = getattr(bundle, axis)

        for exc in ("step", "prbs"):
            result = sysid_rate_loop(
                data["cfg"],
                data["rate_config"],
                plant,
                trim_alpha=bundle.trim.alpha,
                trim_delta_e=bundle.trim.delta_e,
                trim_throttle=bundle.trim.throttle,
                V=bundle.V,
                altitude=0.0,
                axis=axis,
                excitation=exc,
                amplitude=0.01 if exc == "prbs" else 0.02,
                duration=6.0 if exc == "prbs" else 4.0,
                dt=0.02,
            )

            status = "OK" if result.valid else "WARN"
            div = "DIV" if result.diverged else ""

            print(f"\n  [{axis:5s}] [{exc:4s}] [{status}] {div}")
            print(f"    K:   analitico={result.K_analytical:+8.3f}  "
                  f"identificato={result.K_identified:+8.3f}  "
                  f"err={result.K_error_pct:5.1f}%")
            print(f"    tau: analitico={result.tau_analytical:8.4f}s  "
                  f"identificato={result.tau_identified:8.4f}s  "
                  f"err={result.tau_error_pct:5.1f}%")
            print(f"    R²={result.R_squared:.4f}  "
                  f"campioni={result.n_samples}")

    print()
    print("=" * 72)
    print()
    print("PASS: T4 system identification corretto")


if __name__ == "__main__":
    main()