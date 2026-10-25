"""
tools/PFD_full_test.py

Tool di test standalone per il PFD di test (type_id="pfd-test").
Riusa la stessa classe PFD_test registrata nell'hangar della GCS.

Uso:
    cd aerospace-ecosystem
    python3 tools/PFD_full_test.py
"""

import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gcs_ui"))

from PySide6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter

from sim_ui.instruments.factory import InstrumentFactory
from sim_ui.core.prototype import build_default_registry
from sim_ui.core.telemetry import TelemetryData


# ---------------------------------------------------------------------------
# GENERATORE DATI MOCK (tutti i campi, pronti per il futuro)
# ---------------------------------------------------------------------------
class MockDataGenerator:
    def __init__(self):
        self._t = 0.0

    def tick(self, dt: float) -> TelemetryData:
        self._t += dt
        t = self._t
        return TelemetryData(
            airspeed=50.0 + 20.0 * math.sin(t * 0.5),
            altitude=1000.0 + 500.0 * math.sin(t * 0.2),
            vertical_speed=2.0 * math.sin(t * 0.3),
            heading=(t * 10.0) % 360.0,
            pitch=5.0 * math.sin(t * 0.4),
            roll=10.0 * math.sin(t * 0.6),
            turn_rate=2.0 * math.sin(t * 0.5),
            rpm=2500.0 + 500.0 * math.sin(t * 0.3),
            oil_temp=80.0 + 10.0 * math.sin(t * 0.1),
            manifold_pressure=101.3 + 5.0 * math.sin(t * 0.2),
            fuel_flow=0.001 + 0.0005 * math.sin(t * 0.4),
        )


# ---------------------------------------------------------------------------
# FINESTRA DI TEST
# ---------------------------------------------------------------------------
class PFDTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PFD Full Test — pfd-test")
        self.resize(1000, 780)

        # Ottiene il prototype "pfd-test" dal registry (lo stesso dell'hangar)
        registry = build_default_registry()
        proto = registry.get("pfd-test")
        if proto is None:
            raise RuntimeError(
                "Prototype 'pfd-test' non trovato nel registry. "
                "Verifica la registrazione in prototype.py"
            )

        # Crea lo strumento usando la factory (stessa strada dell'hangar)
        self._scene = QGraphicsScene(self)
        self._pfd = InstrumentFactory.create_item(proto)
        self._scene.addItem(self._pfd)

        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setCentralWidget(self._view)

        # Generatore mock + timer 20 Hz
        self._gen = MockDataGenerator()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def _tick(self):
        data = self._gen.tick(0.05)
        self._pfd.update_data(data)

    def closeEvent(self, e):
        self._timer.stop()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    win = PFDTestWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()