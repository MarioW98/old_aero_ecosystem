"""
sim_ui/main.py

Entry point dell'applicazione.
MODIFICATO: Setup logging per ZMQ.
"""

import sys
import logging

from PySide6.QtWidgets import QApplication
from .ui.window import MainWindow


def setup_logging():
    """Configura logging per l'applicazione."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            # Opzionale: log su file
            # logging.FileHandler('sim_ui.log'),
        ]
    )
    
    # Riduci verbosità di librerie terze
    logging.getLogger('zmq').setLevel(logging.WARNING)


def main():
    """Entry point principale."""
    setup_logging()
    
    app = QApplication(sys.argv)
    app.setApplicationName("Flight Simulator MODULAR UI")
    app.setApplicationVersion("0.3.0")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()