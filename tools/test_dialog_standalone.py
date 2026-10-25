"""
tools/test_dialog_standalone.py — Test manuale del KeyBindingDialog.
Esegui con: python tools/test_dialog_standalone.py
"""
import sys
from pathlib import Path

# La ROOT del progetto è il genitore della directory del test
# tools/ → aero-ecosystem/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from control_input.bindings import KeyBindingManager
from gcs_ui.sim_ui.ui.key_binding_dialog import KeyBindingDialog


def main():
    app = QApplication(sys.argv)

    # Crea un manager con i defaults
    mgr = KeyBindingManager()
    mgr.load_defaults()

    print("Prima del dialog:")
    print(f"  throttle_up → {mgr.get_key('throttle_up')} (W={Qt.Key.Key_W})")
    print(f"  pitch_up    → {mgr.get_key('pitch_up')} (Up={Qt.Key.Key_Up})")

    # Apri il dialog
    dlg = KeyBindingDialog(mgr)
    result = dlg.exec()

    if result == KeyBindingDialog.DialogCode.Accepted:
        print("\nSalvato. Dopo il dialog:")
        print(f"  throttle_up → {mgr.get_key('throttle_up')}")
        print(f"  pitch_up    → {mgr.get_key('pitch_up')}")
    else:
        print("\nAnnullato. Nessun cambiamento.")
        print(f"  throttle_up → {mgr.get_key('throttle_up')}")

    # Verifica che il comportamento sia coerente
    from control_input.keyboard_input import KeyboardInput
    kb = KeyboardInput(binding_manager=mgr)

    key = mgr.get_key("throttle_up")
    if key:
        kb.key_pressed(key)
        kb.update(1.0)
        kb.key_released(key)
        print(f"\nTest input: throttle dopo 1s con tasto "
              f"{key} = {kb.throttle:.2f} (atteso ~0.50)")


if __name__ == "__main__":
    main()