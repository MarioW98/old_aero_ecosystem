"""
simulator/test_bindings.py

Test K1: catalogo azioni e KeyBindingManager.

Uso:
    python simulator/test_bindings.py
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from control_input.actions import (
    ACTIONS, ActionDef, ActionType,
    get_action, get_actions_by_category,
)
from control_input.bindings import KeyBindingManager, InputBinding


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


# ======================================================================
# TEST AZIONI
# ======================================================================

def test_actions_catalog():
    """Il catalogo contiene le azioni attese."""
    expected = [
        "throttle_up", "throttle_down",
        "pitch_up", "pitch_down",
        "roll_left", "roll_right",
        "yaw_left", "yaw_right",
        "pause", "reset",
    ]
    for action_id in expected:
        check(action_id in ACTIONS, f"azione '{action_id}' nel catalogo")

    check(len(ACTIONS) == 10, f"catalogo ha 10 azioni, trovato {len(ACTIONS)}")


def test_action_types():
    """I tipi delle azioni sono corretti."""
    check(ACTIONS["throttle_up"].action_type == ActionType.INCREMENTAL,
          "throttle_up è INCREMENTAL")
    check(ACTIONS["pitch_up"].action_type == ActionType.POSITIONAL,
          "pitch_up è POSITIONAL")
    check(ACTIONS["pause"].action_type == ActionType.MOMENTARY,
          "pause è MOMENTARY")


def test_get_action():
    """get_action ritorna la definizione corretta."""
    action = get_action("throttle_up")
    check(action is not None, "get_action('throttle_up') non None")
    check(action.display_name == "Throttle +", "display_name corretto")

    check(get_action("nonexistent") is None, "get_action sconosciuta → None")


def test_actions_by_category():
    """Le azioni sono raggruppate per categoria."""
    cats = get_actions_by_category()
    check("Motore" in cats, "categoria Motore esiste")
    check("Volo" in cats, "categoria Volo esiste")
    check("Sistema" in cats, "categoria Sistema esiste")
    check(len(cats["Motore"]) == 2, "2 azioni in Motore")
    check(len(cats["Volo"]) == 6, "6 azioni in Volo")
    check(len(cats["Sistema"]) == 2, "2 azioni in Sistema")


# ======================================================================
# TEST KEY BINDING MANAGER
# ======================================================================

def test_load_defaults():
    """load_defaults carica tutti i binding attesi."""
    mgr = KeyBindingManager()
    mgr.load_defaults()

    check(len(mgr) == 10, f"10 binding dopo defaults, trovato {len(mgr)}")
    check(mgr.get_key("throttle_up") == Qt.Key_W, "throttle_up → W")
    check(mgr.get_key("throttle_down") == Qt.Key_S, "throttle_down → S")
    check(mgr.get_key("pitch_up") == Qt.Key_Up, "pitch_up → Up")
    check(mgr.get_key("pitch_down") == Qt.Key_Down, "pitch_down → Down")
    check(mgr.get_key("roll_left") == Qt.Key_Left, "roll_left → Left")
    check(mgr.get_key("roll_right") == Qt.Key_Right, "roll_right → Right")
    check(mgr.get_key("yaw_left") == Qt.Key_A, "yaw_left → A")
    check(mgr.get_key("yaw_right") == Qt.Key_D, "yaw_right → D")
    check(mgr.get_key("pause") == Qt.Key_P, "pause → P")
    check(mgr.get_key("reset") == Qt.Key_R, "reset → R")


def test_reverse_lookup():
    """La ricerca inversa (tasto → azione) funziona."""
    mgr = KeyBindingManager()
    mgr.load_defaults()

    check(mgr.get_action_by_key(Qt.Key_W) == "throttle_up", "W → throttle_up")
    check(mgr.get_action_by_key(Qt.Key_Up) == "pitch_up", "Up → pitch_up")
    check(mgr.get_action_by_key(Qt.Key_A) == "yaw_left", "A → yaw_left")
    check(mgr.get_action_by_key(Qt.Key_X) is None, "X → None (non mappato)")


def test_bind_unbind():
    """bind e unbind funzionano correttamente."""
    mgr = KeyBindingManager()
    mgr.load_defaults()

    # Rimuovi il binding di throttle_up (W)
    check(mgr.unbind("throttle_up"), "unbind throttle_up riuscito")
    check(mgr.get_key("throttle_up") is None, "throttle_up senza binding")
    check(mgr.get_action_by_key(Qt.Key_W) is None, "W liberato")
    check(len(mgr) == 9, "9 binding dopo unbind")

    # Rilega throttle_up a un altro tasto
    check(mgr.bind("throttle_up", Qt.Key_Q), "bind throttle_up → Q")
    check(mgr.get_key("throttle_up") == Qt.Key_Q, "throttle_up → Q")
    check(mgr.get_action_by_key(Qt.Key_Q) == "throttle_up", "Q → throttle_up")


def test_conflict_detection():
    """I conflitti vengono rilevati correttamente."""
    mgr = KeyBindingManager()
    mgr.load_defaults()

    # Prova a legare pitch_up al tasto W (già usato da throttle_up)
    result = mgr.bind("pitch_up", Qt.Key_W, force=False)
    check(not result, "conflitto rilevato: W già usato")
    check(mgr.get_key("pitch_up") == Qt.Key_Up,
          "pitch_up mantiene il binding originale")

    # Con force=True, il conflitto viene risolto
    result = mgr.bind("pitch_up", Qt.Key_W, force=True)
    check(result, "force_bind riesce")
    check(mgr.get_key("pitch_up") == Qt.Key_W, "pitch_up → W dopo force")
    check(mgr.get_key("throttle_up") is None,
          "throttle_up perde il binding (sovrascritto)")


def test_bind_invalid_action():
    """bind con azione inesistente ritorna False."""
    mgr = KeyBindingManager()
    mgr.load_defaults()

    result = mgr.bind("nonexistent_action", Qt.Key_X)
    check(not result, "bind con azione inesistente → False")


def test_unbind_nonexistent():
    """unbind di azione senza binding ritorna False."""
    mgr = KeyBindingManager()
    check(not mgr.unbind("throttle_up"), "unbind senza binding → False")


def test_no_conflicts_after_operations():
    """Dopo varie operazioni, non ci sono conflitti interni."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    mgr.bind("throttle_up", Qt.Key_Q, force=True)
    mgr.unbind("pause")
    mgr.bind("pause", Qt.Key_Space)

    check(not mgr.has_conflicts(), "nessun conflitto interno")


def test_save_load_round_trip():
    """save → load produce lo stesso stato."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    mgr.bind("throttle_up", Qt.Key_Q, force=True)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = f.name

    try:
        check(mgr.save(tmp_path), "save riuscito")

        mgr2 = KeyBindingManager()
        check(mgr2.load(tmp_path), "load riuscito")

        check(len(mgr2) == len(mgr), "stesso numero di binding")
        check(mgr2.get_key("throttle_up") == Qt.Key_Q,
              "throttle_up → Q dopo round-trip")
        check(mgr2.get_key("pitch_up") == Qt.Key_Up,
              "pitch_up → Up dopo round-trip")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_load_nonexistent_file():
    """load di file inesistente ritorna False."""
    mgr = KeyBindingManager()
    result = mgr.load("/nonexistent/path/bindings.json")
    check(not result, "load file inesistente → False")


def test_load_invalid_json():
    """load di JSON non valido ritorna False."""
    with tempfile.NamedTemporaryFile(mode='w', suffix=".json",
                                     delete=False) as f:
        f.write("{ invalid json !!!")
        tmp_path = f.name

    try:
        mgr = KeyBindingManager()
        result = mgr.load(tmp_path)
        check(not result, "load JSON invalido → False")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_load_wrong_version():
    """load con versione diversa ritorna False."""
    import json

    with tempfile.NamedTemporaryFile(mode='w', suffix=".json",
                                     delete=False) as f:
        json.dump({"version": 999, "bindings": {}}, f)
        tmp_path = f.name

    try:
        mgr = KeyBindingManager()
        result = mgr.load(tmp_path)
        check(not result, "load versione sbagliata → False")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_load_ignores_unknown_actions():
    """load ignora azioni non nel catalogo (forward compatibility)."""
    import json

    data = {
        "version": 1,
        "bindings": {
            "throttle_up": {
                "action": "throttle_up",
                "source_type": "keyboard",
                "source_id": 87,
                "axis_direction": 0,
            },
            "future_action_xyz": {
                "action": "future_action_xyz",
                "source_type": "keyboard",
                "source_id": 88,
                "axis_direction": 0,
            },
        },
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix=".json",
                                     delete=False) as f:
        json.dump(data, f)
        tmp_path = f.name

    try:
        mgr = KeyBindingManager()
        check(mgr.load(tmp_path), "load con azione futura riuscito")
        check(mgr.get_key("throttle_up") == 87, "throttle_up caricato")
        check("future_action_xyz" not in mgr.get_all_bindings(),
              "azione futura ignorata")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_load_or_defaults():
    """load_or_defaults usa defaults se il file non esiste."""
    mgr = KeyBindingManager()
    result = mgr.load_or_defaults("/nonexistent/bindings.json")
    check(not result, "load_or_defaults ritorna False (usato defaults)")
    check(len(mgr) == 10, "defaults caricati")


def test_get_bound_unbound():
    """get_bound_actions e get_unbound_actions funzionano."""
    mgr = KeyBindingManager()
    mgr.load_defaults()
    mgr.unbind("pause")
    mgr.unbind("reset")

    bound = mgr.get_bound_actions()
    unbound = mgr.get_unbound_actions()

    check(len(bound) == 8, f"8 bound, trovato {len(bound)}")
    check(len(unbound) == 2, f"2 unbound, trovato {len(unbound)}")
    check("pause" in unbound, "pause in unbound")
    check("reset" in unbound, "reset in unbound")


def test_input_binding_model():
    """Il modello InputBinding è pronto per il joystick."""
    binding = InputBinding(
        action="throttle_up",
        source_type="joystick_axis",
        source_id=2,
        axis_direction=1,
    )
    check(binding.source_type == "joystick_axis", "source_type joystick")
    check(binding.source_id == 2, "source_id asse 2")
    check(binding.axis_direction == 1, "axis_direction +1")


def main():
    test_actions_catalog()
    test_action_types()
    test_get_action()
    test_actions_by_category()
    test_load_defaults()
    test_reverse_lookup()
    test_bind_unbind()
    test_conflict_detection()
    test_bind_invalid_action()
    test_unbind_nonexistent()
    test_no_conflicts_after_operations()
    test_save_load_round_trip()
    test_load_nonexistent_file()
    test_load_invalid_json()
    test_load_wrong_version()
    test_load_ignores_unknown_actions()
    test_load_or_defaults()
    test_get_bound_unbound()
    test_input_binding_model()
    print("PASS: K1 catalogo azioni e KeyBindingManager corretti")


if __name__ == "__main__":
    main()