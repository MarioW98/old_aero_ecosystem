"""
tools/test_sim_manager.py — Test manuale del SimManager.

La finestra RESTA APERTA: usa "Avvia" e "Ferma" manualmente.
L'output viene scritto anche in sim_console.log per debug.

Uso:
    py -3.12 tools/test_sim_manager.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QMessageBox,
)

from gcs_ui.sim_ui.sim_manager import SimManager
from gcs_ui.sim_ui.ui.sim_launch_dialog import SimLaunchConfig


LOG_FILE = ROOT / "sim_console.log"


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test SimManager — la finestra resta aperta")
        self.resize(820, 560)

        self._manager = SimManager(self)
        self._log_handle = None
        self._line_count = 0

        layout = QVBoxLayout(self)

        # --- Pulsanti ---
        btn_row = QHBoxLayout()

        self._btn_start = QPushButton("▶ Avvia simulazione")
        self._btn_start.clicked.connect(self._start)
        btn_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("■ Ferma")
        self._btn_stop.clicked.connect(self._stop)
        self._btn_stop.setEnabled(False)
        btn_row.addWidget(self._btn_stop)

        self._btn_clear = QPushButton("Pulisci log")
        self._btn_clear.clicked.connect(lambda: self._log.clear())
        btn_row.addWidget(self._btn_clear)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # --- Stato ---
        self._label = QLabel(
            "Pronto. Premi Avvia. "
            f"(Simulatore: {'OK' if self._manager.is_simulator_available() else 'NON TROVATO'})"
        )
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        # --- Log ---
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._log, stretch=1)

        # --- Contatore ---
        self._counter = QLabel("Righe output: 0")
        layout.addWidget(self._counter)

        # --- Segnali ---
        self._manager.sim_started.connect(self._on_started)
        self._manager.sim_stopped.connect(self._on_stopped)
        self._manager.sim_error.connect(self._on_error)
        self._manager.sim_output.connect(self._on_output)

    # ------------------------------------------------------------------
    def _open_log(self):
        try:
            self._log_handle = open(LOG_FILE, "w", encoding="utf-8")
            self._log_handle.write(f"Project root: {self._manager.project_root}\n")
            self._log_handle.flush()
        except OSError as e:
            self._append(f"[WARN] impossibile aprire il log: {e}")

    def _close_log(self):
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _append(self, text: str):
        self._log.append(text)
        if self._log_handle is not None:
            self._log_handle.write(text + "\n")
            self._log_handle.flush()

    # ------------------------------------------------------------------
    def _start(self):
        if self._manager.is_running:
            return

        self._log.clear()
        self._line_count = 0
        self._open_log()

        config = SimLaunchConfig()
        config.altitude = 0.0
        config.speed = 45.0
        config.alpha = 5.0
        config.throttle = 0.9
        config.fc_mode = "stabilize"
        config.gain_schedule = False

        self._append(f"ROOT: {self._manager.project_root}")
        self._append(f"PYTHON: {sys.executable}")
        self._append("--- Avvio richiesto ---")

        ok = self._manager.launch(config)
        if not ok:
            self._append("[ERRORE] launch() ha ritornato False")

    def _stop(self):
        self._append("--- Stop richiesto ---")
        self._manager.stop()   # NON bloccante

    # ------------------------------------------------------------------
    def _on_started(self):
        self._label.setText("✓ SIMULATORE AVVIATO — in attesa di output...")
        self._label.setStyleSheet("color: green; font-weight: bold;")
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._append("--- SIMULATORE AVVIATO ---")

    def _on_stopped(self, exit_code):
        self._label.setText(f"■ SIMULATORE FERMATO (exit code {exit_code})")
        self._label.setStyleSheet("color: #a00; font-weight: bold;")
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._append(f"--- SIMULATORE FERMATO (exit={exit_code}) ---")
        self._close_log()

    def _on_error(self, msg):
        self._label.setText(f"✗ ERRORE: {msg}")
        self._label.setStyleSheet("color: red; font-weight: bold;")
        self._append(f"[ERRORE] {msg}")

    def _on_output(self, line):
        self._line_count += 1
        self._append(line)
        self._counter.setText(f"Righe output: {self._line_count}")

        # Il primo output reale conferma che il buffering è risolto
        if self._line_count == 1:
            self._label.setText("✓ SIMULATORE AVVIATO — output in arrivo")
            self._label.setStyleSheet("color: green; font-weight: bold;")

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        if self._manager.is_running:
            reply = QMessageBox.question(
                self, "Chiudere",
                "Il simulatore è ancora in esecuzione. Fermarlo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._manager.stop()
                self._manager.wait_for_stop(5000)  # solo in shutdown
        self._close_log()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()