"""
tools/test_trajectory_orbit_climb.py

Verifica delle traiettorie orbita e salita/discesa (gradino 2b).

Controlla:
  1. Orbita: posizione sul cerchio, prua tangente, bank e turn_rate coerenti.
  2. Direzione di virata (destra/sinistra).
  3. Salita/discesa: quota, vertical_speed, pitch e velocità orizzontale.
  4. Validazione dei parametri.
"""

import sys
import math
from pathlib import Path

# Rende importabile ipc_bus dalla root del progetto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ipc_bus.trajectory import OrbitTrajectory, ClimbDescentTrajectory

G = 9.81


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


# =========================================================================
# ORBITA
# =========================================================================
def test_orbit_geometry():
    """La posizione deve restare sul cerchio di raggio R, quota costante."""
    traj = OrbitTrajectory(airspeed=50.0, radius=500.0, altitude=1000.0)
    for t in [0.0, 5.0, 15.7, 31.4, 62.8, 100.0]:
        d = traj.sample(t)
        dist = math.hypot(d.pos_north, d.pos_east)
        check(abs(dist - 500.0) < 1e-3,
              f"t={t}: distanza dal centro attesa 500, ottenuta {dist:.4f}")
        check(abs(d.altitude - 1000.0) < 1e-6,
              f"t={t}: la quota deve restare costante")
        check(abs(d.pos_down + 1000.0) < 1e-6,
              f"t={t}: pos_down atteso -1000")


def test_orbit_coherence():
    """Prua tangente, bank coordinato, turn_rate e airspeed coerenti."""
    V, R = 50.0, 500.0
    traj = OrbitTrajectory(airspeed=V, radius=R, altitude=1000.0, direction=1)

    d0 = traj.sample(0.0)
    # A t=0 il velivolo è a Nord del centro, prua tangente verso Est (orario)
    check(abs(d0.pos_north - R) < 1e-6,
          f"t=0 nord atteso {R}, ottenuto {d0.pos_north}")
    check(abs(d0.pos_east) < 1e-6, f"t=0 est atteso 0, ottenuto {d0.pos_east}")
    check(abs(d0.heading - 90.0) < 1e-6,
          f"t=0 prua attesa 90, ottenuta {d0.heading}")

    # turn_rate = V/R espresso in deg/s
    expected_tr = math.degrees(V / R)
    check(abs(d0.turn_rate - expected_tr) < 1e-6,
          f"turn_rate atteso {expected_tr:.3f}, ottenuto {d0.turn_rate}")

    # rollio = bank di virata coordinata
    expected_bank = math.degrees(math.atan(V * V / (R * G)))
    check(abs(d0.roll - expected_bank) < 1e-6,
          f"roll atteso {expected_bank:.2f}, ottenuto {d0.roll}")

    # airspeed costante, vertical_speed nulla (orbita livellata)
    check(abs(d0.airspeed - V) < 1e-6, "airspeed deve restare costante")
    check(abs(d0.vertical_speed) < 1e-6,
          "vertical_speed deve essere 0 in orbita livellata")


def test_orbit_direction():
    """direction=-1 deve produrre virata sinistra (turn_rate e roll negativi)."""
    traj = OrbitTrajectory(airspeed=50.0, radius=500.0, direction=-1)
    d0 = traj.sample(0.0)
    check(d0.turn_rate < 0,
          f"turn_rate deve essere negativo per virata sinistra, ottenuto {d0.turn_rate}")
    check(d0.roll < 0,
          f"roll deve essere negativo per virata sinistra, ottenuto {d0.roll}")
    # A t=0, a Nord del centro con virata sinistra, la prua punta a Ovest
    check(abs(d0.heading - 270.0) < 1e-6,
          f"prua attesa 270, ottenuta {d0.heading}")


# =========================================================================
# SALITA / DISCESA
# =========================================================================
def test_climb():
    """Salita: quota e vertical_speed positive, pitch positivo."""
    traj = ClimbDescentTrajectory(airspeed=50.0, heading=0.0,
                                  vertical_speed=5.0, start_altitude=1000.0)

    d0 = traj.sample(0.0)
    check(abs(d0.altitude - 1000.0) < 1e-6, "quota iniziale non corretta")

    d10 = traj.sample(10.0)
    check(abs(d10.altitude - 1050.0) < 1e-6,
          f"quota a t=10 attesa 1050, ottenuta {d10.altitude}")
    check(abs(d10.vertical_speed - 5.0) < 1e-6, "vertical_speed atteso 5")

    expected_pitch = math.degrees(math.asin(5.0 / 50.0))
    check(abs(d10.pitch - expected_pitch) < 1e-6,
          f"pitch atteso {expected_pitch:.2f}, ottenuto {d10.pitch}")

    # Volo dritto: heading costante, roll e turn_rate nulli
    check(abs(d10.heading - 0.0) < 1e-6, "heading deve restare costante")
    check(abs(d10.roll) < 1e-6, "roll deve essere nullo in salita rettilinea")
    check(abs(d10.turn_rate) < 1e-6, "turn_rate nullo in salita rettilinea")

    # Velocità orizzontale = sqrt(V² - vs²), diretta a Nord (heading 0)
    horiz = math.sqrt(50.0 ** 2 - 5.0 ** 2)
    check(abs(d10.pos_north - horiz * 10.0) < 1e-3,
          f"pos_north atteso {horiz * 10:.2f}, ottenuto {d10.pos_north}")
    check(abs(d10.pos_east) < 1e-6, "pos_east deve essere nullo con heading 0")
    check(abs(d10.pos_down + 1050.0) < 1e-6, "pos_down deve essere -quota")


def test_descent():
    """Discesa: quota diminuisce, pitch negativo."""
    traj = ClimbDescentTrajectory(airspeed=50.0, heading=90.0,
                                  vertical_speed=-3.0, start_altitude=1000.0)
    d10 = traj.sample(10.0)
    check(abs(d10.altitude - 970.0) < 1e-6,
          f"quota a t=10 attesa 970, ottenuta {d10.altitude}")
    check(abs(d10.vertical_speed + 3.0) < 1e-6, "vertical_speed atteso -3")
    check(d10.pitch < 0, f"pitch deve essere negativo in discesa, ottenuto {d10.pitch}")
    # Heading 90 = Est: pos_east cresce, pos_north resta nullo
    check(d10.pos_east > 0, "pos_east deve crescere con heading 90")
    check(abs(d10.pos_north) < 1e-6, "pos_north deve essere nullo con heading 90")


def test_invalid_climb():
    """|vertical_speed| >= airspeed deve sollevare ValueError."""
    try:
        ClimbDescentTrajectory(airspeed=50.0, vertical_speed=60.0)
        check(False, "doveva sollevare ValueError per |vs| >= airspeed")
    except ValueError:
        pass


if __name__ == "__main__":
    test_orbit_geometry()
    test_orbit_coherence()
    test_orbit_direction()
    test_climb()
    test_descent()
    test_invalid_climb()
    print("PASS: traiettorie orbita e salita/discesa corrette")