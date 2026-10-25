"""
simulator/test_bindings_integration.py

Test K2: integrazione KeyBindingManager con KeyboardInput.
Verifica che la mappatura dinamica funzioni correttamente.

Uso:
    python simulator/test_bindings_integration.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from control_input.input_state import InputState
from control_input.keyboard_input import KeyboardInput
from control_input.bindings import KeyBindingManager


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def check_close(actual, expected, tol, msg):
    if abs(actual - expected) > tol:
        print(f"FAIL: {msg}: atteso {expected}, ottenuto {actual} (tol {tol})")
        sys.exit(1)


def test_default_bindings_work():
    """Con i binding di default, il comportamento è identico a prima."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr)

    # W = throttle up
    kb.key_pressed(Qt.Key_W)
    kb.update(1.0)  # 1 secondo
    kb.key_released(Qt.Key_W)
    check_close(kb.throttle, 0.5, 0.01, "W aumenta throttle")

    # Freccia su = pitch up
    kb.key_pressed(Qt.Key_Up)
    state = kb.get_state()
    check_close(state.pitch_stick, 1.0, 1e-9, "Freccia su = pitch +1")
    kb.key_released(Qt.Key_Up)

    # A = yaw left
    kb.key_pressed(Qt.Key_A)
    state = kb.get_state()
    check_close(state.yaw_stick, -1.0, 1e-9, "A = yaw -1")
    kb.key_released(Qt.Key_A)


def test_rebinding_changes_behavior():
    """Cambiare un binding cambia il comportamento."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr)

    # Rimappa pitch_up da Freccia Su a Q
    mgr.bind("pitch_up", Qt.Key_Q, force=True)

    # Freccia su non deve più fare pitch
    kb.key_pressed(Qt.Key_Up)
    state = kb.get_state()
    check_close(state.pitch_stick, 0.0, 1e-9,
                "Freccia su non è più pitch dopo rimappatura")
    kb.key_released(Qt.Key_Up)

    # Q ora fa pitch up
    kb.key_pressed(Qt.Key_Q)
    state = kb.get_state()
    check_close(state.pitch_stick, 1.0, 1e-9,
                "Q è pitch up dopo rimappatura")
    kb.key_released(Qt.Key_Q)


def test_rebinding_throttle():
    """Rimappare il throttle funziona."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr, initial_throttle=0.0)

    # Rimappa throttle_up da W a T
    mgr.bind("throttle_up", Qt.Key_T, force=True)

    # W non deve più aumentare il throttle
    kb.key_pressed(Qt.Key_W)
    kb.update(1.0)
    kb.key_released(Qt.Key_W)
    check_close(kb.throttle, 0.0, 1e-9,
                "W non aumenta throttle dopo rimappatura")

    # T ora aumenta il throttle
    kb.key_pressed(Qt.Key_T)
    kb.update(1.0)
    kb.key_released(Qt.Key_T)
    check_close(kb.throttle, 0.5, 0.01,
                "T aumenta throttle dopo rimappatura")


def test_momentary_events():
    """Le azioni momentanee generano eventi."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr)

    # P = pause
    kb.key_pressed(Qt.Key_P)
    events = kb.pop_momentary_events()
    check(len(events) == 1, f"1 evento momentaneo, trovato {len(events)}")
    check(events[0] == "pause", f"evento è 'pause', trovato '{events[0]}'")

    # La coda è vuota dopo il pop
    events = kb.pop_momentary_events()
    check(len(events) == 0, "coda vuota dopo pop")

    kb.key_released(Qt.Key_P)


def test_momentary_no_repeat():
    """L'auto-repeat non genera eventi momentanei multipli."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr)

    # Prima pressione
    kb.key_pressed(Qt.Key_P)
    # Auto-repeat (stesso tasto già premuto)
    kb.key_pressed(Qt.Key_P)
    kb.key_pressed(Qt.Key_P)

    events = kb.pop_momentary_events()
    check(len(events) == 1,
          f"auto-repeat non genera eventi multipli, trovato {len(events)}")

    kb.key_released(Qt.Key_P)


def test_momentary_reset():
    """R = reset genera evento momentaneo."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr)

    kb.key_pressed(Qt.Key_R)
    events = kb.pop_momentary_events()
    check(len(events) == 1, "1 evento reset")
    check(events[0] == "reset", f"evento è 'reset', trovato '{events[0]}'")
    kb.key_released(Qt.Key_R)


def test_unbound_key_ignored():
    """Un tasto non mappato viene ignorato."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr)

    # X non è mappato
    kb.key_pressed(Qt.Key_X)
    state = kb.get_state()
    check_close(state.pitch_stick, 0.0, 1e-9, "X non influenza pitch")
    check_close(state.roll_stick, 0.0, 1e-9, "X non influenza roll")
    check_close(state.yaw_stick, 0.0, 1e-9, "X non influenza yaw")

    events = kb.pop_momentary_events()
    check(len(events) == 0, "X non genera eventi momentanei")
    kb.key_released(Qt.Key_X)


def test_binding_manager_accessible():
    """Il binding manager è accessibile da KeyboardInput."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr)

    check(kb.binding_manager is mgr, "binding_manager accessibile")
    check(kb.binding_manager.get_key("throttle_up") == Qt.Key_W,
          "query tramite binding_manager funziona")


def test_multiple_simultaneous_inputs():
    """Più input contemporaneamente con binding dinamici."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    kb = KeyboardInput(binding_manager=mgr, initial_throttle=0.5)

    kb.key_pressed(Qt.Key_W)       # throttle up
    kb.key_pressed(Qt.Key_Up)      # pitch up
    kb.key_pressed(Qt.Key_Right)   # roll right
    kb.key_pressed(Qt.Key_A)       # yaw left

    kb.update(0.1)
    state = kb.get_state()

    check_close(state.throttle, 0.55, 0.01, "throttle incrementato")
    check_close(state.pitch_stick, 1.0, 1e-9, "pitch attivo")
    check_close(state.roll_stick, 1.0, 1e-9, "roll attivo")
    check_close(state.yaw_stick, -1.0, 1e-9, "yaw attivo")

    kb.key_released(Qt.Key_W)
    kb.key_released(Qt.Key_Up)
    kb.key_released(Qt.Key_Right)
    kb.key_released(Qt.Key_A)


def main():
    test_default_bindings_work()
    test_rebinding_changes_behavior()
    test_rebinding_throttle()
    test_momentary_events()
    test_momentary_no_repeat()
    test_momentary_reset()
    test_unbound_key_ignored()
    test_binding_manager_accessible()
    test_multiple_simultaneous_inputs()
    print("PASS: K2 integrazione KeyBindingManager corretta")


if __name__ == "__main__":
    main()