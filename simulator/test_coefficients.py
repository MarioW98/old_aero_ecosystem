"""
simulator/test_coefficients.py

Test D2.1: tabelle aerodinamiche e interpolazione.
Verifica valori noti, continuità, e comportamento in stallo.

Uso:
    python simulator/test_coefficients.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
from dynamics.aero.coefficients import (
    AeroConfig, AeroCoefficients,
    make_c172_config, make_generic_config,
)


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual: float, expected: float, tol: float, msg: str) -> None:
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


def test_c172_config_valid():
    """La configurazione C172 deve avere tabelle coerenti."""
    cfg = make_c172_config()
    n = len(cfg.alpha_table)
    check(n == len(cfg.CL_table), "lunghezza CL_table coerente")
    check(n == len(cfg.CD_table), "lunghezza CD_table coerente")
    check(n == len(cfg.Cm_table), "lunghezza Cm_table coerente")
    check(cfg.S_ref > 0, "S_ref positiva")
    check(cfg.b_ref > 0, "b_ref positiva")
    check(cfg.c_ref > 0, "c_ref positiva")
    check(cfg.AR > 0, "aspect ratio positivo")


def test_cl_linear_region():
    """Nella regione lineare, CL deve crescere con alpha."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    # Alpha = 4° e alpha = 8°: CL deve crescere
    result_4 = aero.compute(alpha=math.radians(4.0))
    result_8 = aero.compute(alpha=math.radians(8.0))

    check(result_8['CL'] > result_4['CL'],
          "CL a 8° deve essere > CL a 4° (regione lineare)")


def test_stall_behavior():
    """Dopo lo stallo (~16°), CL deve diminuire."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    result_14 = aero.compute(alpha=math.radians(14.0))
    result_16 = aero.compute(alpha=math.radians(16.0))
    result_20 = aero.compute(alpha=math.radians(20.0))

    # CL_max è attorno a 16°
    check(result_16['CL'] > result_20['CL'],
          "CL a 20° deve essere < CL a 16° (post-stallo)")
    check(result_16['CL'] >= result_14['CL'],
          "CL a 16° deve essere >= CL a 14° (CL_max)")


def test_cd_always_positive():
    """CD deve essere sempre positivo (la resistenza non spinge)."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    for alpha_deg in range(-90, 91, 5):
        result = aero.compute(alpha=math.radians(float(alpha_deg)))
        check(result['CD'] > 0,
              f"CD a alpha={alpha_deg}° deve essere positivo, ottenuto {result['CD']}")


def test_cd_increases_at_stall():
    """CD deve aumentare significativamente in stallo."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    result_5 = aero.compute(alpha=math.radians(5.0))
    result_20 = aero.compute(alpha=math.radians(20.0))

    check(result_20['CD'] > result_5['CD'] * 2,
          "CD a 20° deve essere almeno 2x CD a 5° (stallo)")


def test_interpolation_continuity():
    """L'interpolazione deve essere continua (nessun salto)."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    # Campiona alpha con passo piccolo e verifica che CL non faccia salti
    prev_CL = None
    for i in range(-900, 901):
        alpha = math.radians(i * 0.1)
        result = aero.compute(alpha=alpha)
        CL = result['CL']
        if prev_CL is not None:
            delta = abs(CL - prev_CL)
            check(delta < 0.1,
                  f"salto di CL a alpha={i*0.1:.1f}°: delta={delta:.4f}")
        prev_CL = CL


def test_elevator_effect():
    """L'elevatore deve modificare CL e Cm."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    alpha = math.radians(5.0)
    result_neutral = aero.compute(alpha=alpha, delta_e=0.0)
    result_up = aero.compute(alpha=alpha, delta_e=math.radians(10.0))

    # Elevatore deflesso (delta_e > 0) aumenta CL e dà Cm negativo (nose-down)
    check(result_up['CL'] > result_neutral['CL'],
          "elevatore deflesso deve aumentare CL")
    check(result_up['Cm'] < result_neutral['Cm'],
          "elevatore deflesso deve dare Cm più negativo (nose-down)")


def test_aileron_effect():
    """Gli alettoni devono generare momento di rollio."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    alpha = math.radians(5.0)
    result_neutral = aero.compute(alpha=alpha, delta_a=0.0)
    result_roll = aero.compute(alpha=alpha, delta_a=math.radians(15.0))

    check(result_roll['Cl'] != result_neutral['Cl'],
          "alettoni devono generare momento di rollio")
    check(result_roll['Cl'] > result_neutral['Cl'],
          "delta_a positivo deve dare Cl positivo (roll destro)")


def test_rudder_effect():
    """Il timone deve generare momento di imbardata."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    alpha = math.radians(5.0)
    result_neutral = aero.compute(alpha=alpha, delta_r=0.0)
    result_yaw = aero.compute(alpha=alpha, delta_r=math.radians(10.0))

    check(result_yaw['Cn'] != result_neutral['Cn'],
          "timone deve generare momento di imbardata")


def test_q_damping():
    """Il pitch rate deve generare momento smorzante (Cm_q < 0)."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    alpha = math.radians(5.0)
    result_static = aero.compute(alpha=alpha, q_hat=0.0)
    result_pitching = aero.compute(alpha=alpha, q_hat=0.1)

    # Cm_q è negativo: q_hat positivo dà Cm più negativo
    check(result_pitching['Cm'] < result_static['Cm'],
          "q_hat positivo deve dare Cm più negativo (smorzamento)")


def test_symmetric_airfoil():
    """Con ala simmetrica (generic_config), CL(0) = 0."""
    cfg = make_generic_config()
    aero = AeroCoefficients(cfg)

    result = aero.compute(alpha=0.0)
    check_close(result['CL'], 0.0, 0.01, "CL a alpha=0 per ala simmetrica")
    check_close(result['Cm'], 0.0, 0.01, "Cm a alpha=0 per ala simmetrica")


def test_extreme_angles():
    """A ±90° il comportamento deve essere ragionevole (flat plate)."""
    cfg = make_c172_config()
    aero = AeroCoefficients(cfg)

    result_90 = aero.compute(alpha=math.radians(90.0))
    result_neg90 = aero.compute(alpha=math.radians(-90.0))

    # A ±90° CL deve essere vicino a 0 (flat plate perpendicolare al flusso)
    check(abs(result_90['CL']) < 0.3, "CL a 90° deve essere ~0 (flat plate)")
    check(abs(result_neg90['CL']) < 0.3, "CL a -90° deve essere ~0 (flat plate)")

    # A ±90° CD deve essere alto
    check(result_90['CD'] > 1.0, "CD a 90° deve essere alto")
    check(result_neg90['CD'] > 1.0, "CD a -90° deve essere alto")


def main():
    test_c172_config_valid()
    test_cl_linear_region()
    test_stall_behavior()
    test_cd_always_positive()
    test_cd_increases_at_stall()
    test_interpolation_continuity()
    test_elevator_effect()
    test_aileron_effect()
    test_rudder_effect()
    test_q_damping()
    test_symmetric_airfoil()
    test_extreme_angles()
    print("PASS: D2.1 tabelle aerodinamiche e interpolazione corrette")


if __name__ == "__main__":
    main()