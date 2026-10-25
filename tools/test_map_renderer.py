"""
tools/test_map_renderer.py

Verifica del MapRenderer in isolamento (gradino M1).
Apre una finestra con la mappa alimentata da una traiettoria orbitale.

Uso:
    cd aerospace-ecosystem
    python3 tools/test_map_renderer.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "gcs_ui"))

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter

from ipc_bus.trajectory import create_trajectory
from sim_ui.core.map_renderer import MapRenderer


class MapWidget(QWidget):
    """Widget minimale che ospita il MapRenderer per il test."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._renderer = MapRenderer(pixels_per_meter=0.4, grid_spacing=100.0)
        self._data = None

    def set_data(self, data):
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._data is not None:
            self._renderer.render(painter, self.rect(), self._data)
        painter.end()


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Map Renderer Test — Orbita")
        self.resize(600, 600)

        self._map_widget = MapWidget()
        self.setCentralWidget(self._map_widget)

        # Traiettoria orbitale per verificare scorrimento + rotazione prua
        self._trajectory = create_trajectory(
            "orbit", airspeed=50.0, radius=500.0, altitude=1000.0)
        self._t = 0.0
        self._dt = 0.05

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)  # 20 Hz

    def _tick(self):
        data = self._trajectory.sample(self._t)
        self._t += self._dt
        self._map_widget.set_data(data)

    def closeEvent(self, e):
        self._timer.stop()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    win = TestWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()