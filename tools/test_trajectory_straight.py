"""
tools/test_trajectory_straight.py

Verifica della traiettoria rettilinea (gradino 2a).

Controlla:
  1. Integrazione corretta della posizione nel tempo.
  2. Coerenza dei campi (prua fissa, rollio zero, quota costante).
  3. Rispetto della convenzione NED e della prua aeronautica.
"""

import sys
import math
from pathlib import Path

# Rende importabile ipc_bus dalla root del progetto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ipc_bus.trajectory import StraightLineTrajectory


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def test_north():
    """Volo verso Nord a 50 m/s: dopo 10 s deve essere 500 m a Nord."""
    traj = StraightLineTrajectory(airspeed=50.0, heading=0.0, altitude=1000.0)

    d0 = traj.sample(0.0)
    check(abs(d0.pos_north) < 1e-6, f"t=0 nord atteso 0, ottenuto {d0.pos_north}")
    check(abs(d0.pos_east) < 1e-6, f"t=0 est atteso 0, ottenuto {d0.pos_east}")

    d10 = traj.sample(10.0)
    check(abs(d10.pos_north - 500.0) < 1e-6,
          f"t=10 nord atteso 500, ottenuto {d10.pos_north}")
    check(abs(d10.pos_east) < 1e-6,
          f"t=10 est atteso 0, ottenuto {d10.pos_east}")

    # Coerenza: prua fissa, nessun rollio, nessuna virata, quota costante
    check(abs(d10.heading - 0.0) < 1e-6, "la prua deve restare 0")
    check(abs(d10.roll) < 1e-6, "rollio deve essere 0 in volo rettilineo")
    check(abs(d10.turn_rate) < 1e-6, "turn_rate deve essere 0 in volo rettilineo")
    check(abs(d10.altitude - 1000.0) < 1e-6, "la quota deve restare costante")
    check(abs(d10.vertical_speed) < 1e-6, "vertical_speed deve essere 0 in volo livellato")
    # NED: pos_down = -quota
    check(abs(d10.pos_down + 1000.0) < 1e-6,
          f"pos_down atteso -1000, ottenuto {d10.pos_down}")


def test_east():
    """Volo verso Est (prua 90°) a 50 m/s: dopo 10 s deve essere 500 m a Est."""
    traj = StraightLineTrajectory(airspeed=50.0, heading=90.0, altitude=1000.0)
    d10 = traj.sample(10.0)
    check(abs(d10.pos_east - 500.0) < 1e-6,
          f"t=10 est atteso 500, ottenuto {d10.pos_east}")
    check(abs(d10.pos_north) < 1e-6,
          f"t=10 nord atteso 0, ottenuto {d10.pos_north}")


def test_diagonal():
    """Volo verso Nord-Est (prua 45°): le componenti N ed E devono essere uguali."""
    traj = StraightLineTrajectory(airspeed=50.0, heading=45.0, altitude=500.0)
    d10 = traj.sample(10.0)
    distanza = 50.0 * 10.0                                  # 500 m percorsi
    atteso = distanza * math.cos(math.radians(45.0))        # ~353.55 m per asse
    check(abs(d10.pos_north - atteso) < 1e-6,
          f"nord atteso {atteso:.2f}, ottenuto {d10.pos_north}")
    check(abs(d10.pos_east - atteso) < 1e-6,
          f"est atteso {atteso:.2f}, ottenuto {d10.pos_east}")


def test_speed_consistency():
    """La distanza percorsa in 1 s deve coincidere con l'airspeed (vento assente)."""
    traj = StraightLineTrajectory(airspeed=70.0, heading=30.0, altitude=1000.0)
    d1 = traj.sample(1.0)
    distanza = math.hypot(d1.pos_north, d1.pos_east)
    check(abs(distanza - 70.0) < 1e-6,
          f"distanza in 1 s attesa 70, ottenuta {distanza}")


if __name__ == "__main__":
    test_north()
    test_east()
    test_diagonal()
    test_speed_consistency()
    print("PASS: traiettoria rettilinea corretta (posizione, coerenza, NED)")
    