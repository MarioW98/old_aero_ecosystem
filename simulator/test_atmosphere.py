"""
simulator/test_atmosphere.py

Test D1.2: modello atmosferico ISA.
Verifica con valori ISA standard noti.

Uso:
    python simulator/test_atmosphere.py
"""

import sys
from pathlib import Path

# Rende importabile dynamics/ dalla root del simulatore
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dynamics.atmosphere import Atmosphere


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual: float, expected: float, tol: float, msg: str) -> None:
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tolleranza {tol})")
        sys.exit(1)


def test_sea_level():
    """Al livello del mare: valori ISA standard."""
    check_close(Atmosphere.temperature(0.0), 288.15, 0.01, "T al livello del mare")
    check_close(Atmosphere.pressure(0.0), 101325.0, 1.0, "P al livello del mare")
    check_close(Atmosphere.density(0.0), 1.225, 0.001, "rho al livello del mare")


def test_1000m():
    """A 1000 m: valori ISA noti."""
    # T = 288.15 - 0.0065·1000 = 281.65 K
    check_close(Atmosphere.temperature(1000.0), 281.65, 0.01, "T a 1000 m")
    # P ≈ 89875 Pa
    check_close(Atmosphere.pressure(1000.0), 89875.0, 100.0, "P a 1000 m")
    # rho ≈ 1.112 kg/m³
    check_close(Atmosphere.density(1000.0), 1.112, 0.005, "rho a 1000 m")


def test_tropopause():
    """A 11000 m (tropopausa): T = 216.65 K, P ≈ 22632 Pa."""
    check_close(Atmosphere.temperature(11000.0), 216.65, 0.01, "T alla tropopausa")
    check_close(Atmosphere.pressure(11000.0), 22632.0, 100.0, "P alla tropopausa")
    check_close(Atmosphere.density(11000.0), 0.364, 0.005, "rho alla tropopausa")


def test_stratosphere():
    """A 15000 m (stratosfera): T costante, P e rho in calo esponenziale."""
    # T resta 216.65 K
    check_close(Atmosphere.temperature(15000.0), 216.65, 0.01,
                "T a 15000 m (stratosfera)")
    # P e rho devono essere minori che alla tropopausa
    check(Atmosphere.pressure(15000.0) < Atmosphere.P_TROPOPAUSE,
          "P a 15000 m < P alla tropopausa")
    check(Atmosphere.density(15000.0) < Atmosphere.RHO_TROPOPAUSE,
          "rho a 15000 m < rho alla tropopausa")
    # Valori ISA approssimativi a 15000 m: P ≈ 12045 Pa, rho ≈ 0.194 kg/m³
    check_close(Atmosphere.pressure(15000.0), 12045.0, 200.0, "P a 15000 m")
    check_close(Atmosphere.density(15000.0), 0.194, 0.01, "rho a 15000 m")


def test_speed_of_sound():
    """Velocità del suono: ~340 m/s al suolo, ~295 m/s alla tropopausa."""
    check_close(Atmosphere.speed_of_sound(0.0), 340.3, 1.0,
                "velocità del suono al suolo")
    check_close(Atmosphere.speed_of_sound(11000.0), 295.1, 1.0,
                "velocità del suono alla tropopausa")


def test_dynamic_pressure():
    """Pressione dinamica: q = ½·ρ·V²."""
    # Al suolo, V = 100 m/s: q = 0.5 · 1.225 · 10000 = 6125 Pa
    q = Atmosphere.dynamic_pressure(0.0, 100.0)
    check_close(q, 6125.0, 10.0, "pressione dinamica al suolo V=100 m/s")


def test_monotonicity():
    """In troposfera, T, P e rho devono decrescere con la quota."""
    altitudes = [0, 1000, 2000, 5000, 8000, 10000]
    for i in range(len(altitudes) - 1):
        h1, h2 = altitudes[i], altitudes[i + 1]
        check(Atmosphere.temperature(h1) > Atmosphere.temperature(h2),
              f"T deve decrescere tra {h1} m e {h2} m")
        check(Atmosphere.pressure(h1) > Atmosphere.pressure(h2),
              f"P deve decrescere tra {h1} m e {h2} m")
        check(Atmosphere.density(h1) > Atmosphere.density(h2),
              f"rho deve decrescere tra {h1} m e {h2} m")


def test_negative_altitude():
    """Quote leggermente negative (es. Mar Morto) non devono dare errori."""
    T = Atmosphere.temperature(-100.0)
    P = Atmosphere.pressure(-100.0)
    rho = Atmosphere.density(-100.0)
    # Sotto il livello del mare: T, P e rho sono maggiori che al suolo
    check(T > Atmosphere.T0, "T a -100 m deve essere > T al suolo")
    check(P > Atmosphere.P0, "P a -100 m deve essere > P al suolo")
    check(rho > Atmosphere.RHO0, "rho a -100 m deve essere > rho al suolo")


def test_continuity_at_tropopause():
    """P e rho devono essere continue alla tropopausa (nessun salto)."""
    h_below = Atmosphere.H_TROPOPAUSE - 0.01
    h_above = Atmosphere.H_TROPOPAUSE + 0.01

    P_below = Atmosphere.pressure(h_below)
    P_above = Atmosphere.pressure(h_above)
    check(abs(P_below - P_above) / P_below < 1e-4,
          "P deve essere continua alla tropopausa")

    rho_below = Atmosphere.density(h_below)
    rho_above = Atmosphere.density(h_above)
    check(abs(rho_below - rho_above) / rho_below < 1e-4,
          "rho deve essere continua alla tropopausa")


def main():
    test_sea_level()
    test_1000m()
    test_tropopause()
    test_stratosphere()
    test_speed_of_sound()
    test_dynamic_pressure()
    test_monotonicity()
    test_negative_altitude()
    test_continuity_at_tropopause()
    print("PASS: D1.2 atmosfera ISA corretta")


if __name__ == "__main__":
    main()