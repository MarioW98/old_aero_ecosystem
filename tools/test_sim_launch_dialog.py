# tools/test_sim_launch_dialog.py
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from gcs_ui.sim_ui.ui.sim_launch_dialog import SimLaunchDialog, SimLaunchConfig

def main():
    app = QApplication(sys.argv)
    config = SimLaunchConfig()
    dlg = SimLaunchDialog(config)
    if dlg.exec():
        print("Configurazione accettata:")
        print(f"  Velivolo: {config.aircraft}")
        print(f"  Quota: {config.altitude} m")
        print(f"  Velocità: {config.speed} m/s")
        print(f"  α: {config.alpha}°")
        print(f"  FC mode: {config.fc_mode}")
        print(f"  Gain schedule: {config.gain_schedule}")
    else:
        print("Annullato.")

if __name__ == "__main__":
    main()