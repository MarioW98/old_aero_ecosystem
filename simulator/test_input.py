"""
simulator/test_input.py

Test I1: InputState e KeyboardInput.
Verifica la corretta produzione di InputState dalla tastiera.

Uso:
    python simulator/test_input.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from control_input.input_state import InputState
from control_input.keyboard_input import KeyboardInput


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual, expected, tol, msg):
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tol {tol})")
        sys.exit(1)


def test_input_state_default():
    """InputState di default ha tutti i valori a zero."""
    state = InputState()
    check_close(state.throttle, 0.0, 1e-9, "throttle default")
    check_close(state.pitch_stick, 0.0, 1e-9, "pitch default")
    check_close(state.roll_stick, 0.0, 1e-9, "roll default")
    check_close(state.yaw_stick, 0.0, 1e-9, "yaw default")


def test_input_state_clamp():
    """InputState.clamp() limita i valori nei range validi."""
    state = InputState(throttle=1.5, pitch_stick=-2.0, roll_stick=3.0, yaw_stick=-0.5)
    clamped = state.clamp()
    check_close(clamped.throttle, 1.0, 1e-9, "throttle clamp a 1.0")
    check_close(clamped.pitch_stick, -1.0, 1e-9, "pitch clamp a -1.0")
    check_close(clamped.roll_stick, 1.0, 1e-9, "roll clamp a 1.0")
    check_close(clamped.yaw_stick, -0.5, 1e-9, "yaw invariato")


def test_keyboard_initial_state():
    """KeyboardInput appena creato ha stato neutro."""
    kb = KeyboardInput()
    state = kb.get_state()
    check_close(state.throttle, 0.0, 1e-9, "throttle iniziale")
    check_close(state.pitch_stick, 0.0, 1e-9, "pitch iniziale")
    check_close(state.roll_stick, 0.0, 1e-9, "roll iniziale")
    check_close(state.yaw_stick, 0.0, 1e-9, "yaw iniziale")


def test_keyboard_pitch():
    """Freccia su = pitch positivo, freccia giù = pitch negativo."""
    kb = KeyboardInput()

    kb.key_pressed(Qt.Key_Up)
    state = kb.get_state()
    check_close(state.pitch_stick, 1.0, 1e-9, "freccia su = pitch +1")

    kb.key_pressed(Qt.Key_Down)
    state = kb.get_state()
    check_close(state.pitch_stick, 0.0, 1e-9, "entrambe le frecce = pitch 0")

    kb.key_released(Qt.Key_Up)
    state = kb.get_state()
    check_close(state.pitch_stick, -1.0, 1e-9, "freccia giù = pitch -1")

    kb.key_released(Qt.Key_Down)
    state = kb.get_state()
    check_close(state.pitch_stick, 0.0, 1e-9, "nessun tasto = pitch 0")


def test_keyboard_roll():
    """Freccia destra = roll positivo, freccia sinistra = roll negativo."""
    kb = KeyboardInput()

    kb.key_pressed(Qt.Key_Right)
    state = kb.get_state()
    check_close(state.roll_stick, 1.0, 1e-9, "freccia destra = roll +1")

    kb.key_released(Qt.Key_Right)
    kb.key_pressed(Qt.Key_Left)
    state = kb.get_state()
    check_close(state.roll_stick, -1.0, 1e-9, "freccia sinistra = roll -1")


def test_keyboard_yaw():
    """D = yaw positivo, A = yaw negativo."""
    kb = KeyboardInput()

    kb.key_pressed(Qt.Key_D)
    state = kb.get_state()
    check_close(state.yaw_stick, 1.0, 1e-9, "D = yaw +1")

    kb.key_released(Qt.Key_D)
    kb.key_pressed(Qt.Key_A)
    state = kb.get_state()
    check_close(state.yaw_stick, -1.0, 1e-9, "A = yaw -1")


def test_keyboard_throttle_increment():
    """W aumenta il throttle, S lo riduce (incrementale nel tempo)."""
    kb = KeyboardInput(initial_throttle=0.5)

    # Tieni premuto W per 1 secondo (in step da 0.1 s)
    kb.key_pressed(Qt.Key_W)
    for _ in range(10):
        kb.update(0.1)
    kb.key_released(Qt.Key_W)

    # Throttle dovrebbe essere aumentato di THROTTLE_RATE * 1.0 = 0.5
    check_close(kb.throttle, 1.0, 0.01, "throttle aumenta con W")

    # Tieni premuto S per 2 secondi
    kb.key_pressed(Qt.Key_S)
    for _ in range(20):
        kb.update(0.1)
    kb.key_released(Qt.Key_S)

    # Throttle dovrebbe essere 1.0 - 0.5*2.0 = 0.0
    check_close(kb.throttle, 0.0, 0.01, "throttle diminuisce con S")


def test_keyboard_throttle_clamp():
    """Il throttle non supera [0, 1]."""
    kb = KeyboardInput(initial_throttle=0.9)

    # Tieni premuto W per 1 secondo (dovrebbe andare a 1.4, ma clamp a 1.0)
    kb.key_pressed(Qt.Key_W)
    for _ in range(10):
        kb.update(0.1)
    kb.key_released(Qt.Key_W)

    check_close(kb.throttle, 1.0, 1e-9, "throttle clamp a 1.0")

    # Tieni premuto S per 3 secondi (dovrebbe andare a -0.5, ma clamp a 0.0)
    kb.key_pressed(Qt.Key_S)
    for _ in range(30):
        kb.update(0.1)
    kb.key_released(Qt.Key_S)

    check_close(kb.throttle, 0.0, 1e-9, "throttle clamp a 0.0")


def test_keyboard_clear():
    """clear() rilascia tutti i tasti."""
    kb = KeyboardInput()
    kb.key_pressed(Qt.Key_Up)
    kb.key_pressed(Qt.Key_Right)
    kb.key_pressed(Qt.Key_W)

    kb.clear()
    state = kb.get_state()
    check_close(state.pitch_stick, 0.0, 1e-9, "pitch dopo clear")
    check_close(state.roll_stick, 0.0, 1e-9, "roll dopo clear")


def test_keyboard_multiple_axes():
    """Più assi contemporaneamente."""
    kb = KeyboardInput(initial_throttle=0.7)
    kb.key_pressed(Qt.Key_Up)
    kb.key_pressed(Qt.Key_Right)
    kb.key_pressed(Qt.Key_A)

    state = kb.get_state()
    check_close(state.throttle, 0.7, 1e-9, "throttle invariato")
    check_close(state.pitch_stick, 1.0, 1e-9, "pitch attivo")
    check_close(state.roll_stick, 1.0, 1e-9, "roll attivo")
    check_close(state.yaw_stick, -1.0, 1e-9, "yaw attivo")


def main():
    test_input_state_default()
    test_input_state_clamp()
    test_keyboard_initial_state()
    test_keyboard_pitch()
    test_keyboard_roll()
    test_keyboard_yaw()
    test_keyboard_throttle_increment()
    test_keyboard_throttle_clamp()
    test_keyboard_clear()
    test_keyboard_multiple_axes()
    print("PASS: I1 InputState e KeyboardInput corretti")


if __name__ == "__main__":
    main()