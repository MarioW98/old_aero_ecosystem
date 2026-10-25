"""
gcs_ui/sim_ui/sim_manager.py

SimManager: gestisce il ciclo di vita del processo simulatore.

Usa QProcess (integrazione nativa con l'event loop Qt).

PUNTI CRITICI DI PROGETTAZIONE:
1. stdout NON bufferizzato: -u + PYTHONUNBUFFERED=1 + PYTHONUTF8=1.
   Senza questi, Python bufferizza ~8KB quando stdout è una pipe,
   e la GUI non vede nulla per molti secondi.
2. Canali uniti (MergedChannels): preserva l'ordine cronologico
   tra stdout e stderr (fondamentale per leggere i traceback).
3. stop() NON bloccante: terminate() + QTimer di watchdog.
   waitForFinished() è ammesso solo in wait_for_stop(), da usare
   esclusivamente in closeEvent.
4. Buffer di righe: gestisce letture che spezzano una riga a metà.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import (
    QObject, QProcess, QProcessEnvironment, QTimer, Signal,
)

from .ui.sim_launch_dialog import SimLaunchConfig


class SimManager(QObject):
    """
    Gestore del processo simulatore.

    Segnali:
        sim_started()      : processo avviato
        sim_stopped(int)   : processo terminato (exit_code)
        sim_error(str)     : errore di avvio / crash
        sim_output(str)    : una riga di output del simulatore

    Uso:
        mgr = SimManager(parent=self)
        mgr.sim_output.connect(self._log_panel.append)
        mgr.sim_stopped.connect(self._on_sim_stopped)
        mgr.launch(config)
        ...
        mgr.stop()          # non blocca
    """

    sim_started = Signal()
    sim_stopped = Signal(int)
    sim_error = Signal(str)
    sim_output = Signal(str)

    KILL_TIMEOUT_MS = 1500

    def __init__(self, parent=None):
        super().__init__(parent)

        # gcs_ui/sim_ui/sim_manager.py → root progetto
        self._project_root = Path(__file__).resolve().parent.parent.parent

        self._process: QProcess | None = None
        self._config: SimLaunchConfig | None = None
        self._stopping = False

        # Buffer per righe spezzate tra due letture
        self._line_buffer = ""

        # Storia output (utile se il pannello log viene creato dopo)
        self._history: deque[str] = deque(maxlen=2000)

        # Watchdog per stop non bloccante
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.setInterval(self.KILL_TIMEOUT_MS)
        self._kill_timer.timeout.connect(self._force_kill)

    # ------------------------------------------------------------------
    # PROPRIETÀ
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.state() != QProcess.ProcessState.NotRunning

    @property
    def current_config(self) -> SimLaunchConfig | None:
        return self._config

    @property
    def output_history(self) -> list[str]:
        """Copia della storia output (fino a 2000 righe)."""
        return list(self._history)

    # ------------------------------------------------------------------
    # DISPONIBILITÀ
    # ------------------------------------------------------------------
    def is_simulator_available(self) -> bool:
        return (self._project_root / "simulator" / "run_sim.py").exists()

    @property
    def project_root(self) -> Path:
        return self._project_root

    # ------------------------------------------------------------------
    # LANCIO
    # ------------------------------------------------------------------
    def launch(self, config: SimLaunchConfig) -> bool:
        """
        Lancia il simulatore. Ritorna True se il lancio è stato initiato.

        Gli errori di avvio arrivano ASINCRONI via sim_error, non qui:
        non usiamo waitForStarted() per non bloccare l'event loop.
        """
        if self.is_running:
            self.sim_error.emit("Simulazione già in esecuzione.")
            return False

        if not self.is_simulator_available():
            self.sim_error.emit(
                f"Simulatore non trovato: "
                f"{self._project_root / 'simulator' / 'run_sim.py'}"
            )
            return False

        proc = QProcess(self)
        proc.setProgram(sys.executable)
        proc.setArguments(["-u", "-m", "simulator.run_sim"]
                          + self._build_arguments(config))
        proc.setWorkingDirectory(str(self._project_root))

        # --- Ambiente: no buffering, UTF-8 garantito ---
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        proc.setProcessEnvironment(env)

        # --- Canali uniti: ordine cronologico stdout/stderr ---
        proc.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels)

        # Reset stato
        self._line_buffer = ""
        self._stopping = False
        self._config = config
        self._process = proc

        # Collegamenti
        proc.started.connect(self._on_started)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        proc.readyReadStandardOutput.connect(self._drain_output)

        proc.start()
        return True

    def _build_arguments(self, config: SimLaunchConfig) -> list[str]:
        args = [
            f"--altitude={config.altitude}",
            f"--speed={config.speed}",
            f"--alpha={config.alpha}",
            f"--throttle={config.throttle}",
            f"--fc-mode={config.fc_mode}",
            "--endpoint=tcp://*:5555",
            "--frequency=50",
        ]
        if config.gain_schedule:
            args.append("--gain-schedule")
        return args

    # ------------------------------------------------------------------
    # STOP NON BLOCCANTE
    # ------------------------------------------------------------------
    def stop(self):
        """
        Ferma il processo SENZA bloccare l'event loop.

        terminate() → watchdog di 5 s → kill() se ancora vivo.
        Il segnale sim_stopped arriva quando il processo finisce davvero.
        """
        if self._process is None:
            return

        if self._process.state() == QProcess.ProcessState.NotRunning:
            return

        self._stopping = True
        self._process.terminate()
        self._kill_timer.start()

    def _force_kill(self):
        """Watchdog: forza la terminazione se terminate() non ha funzionato."""
        if self._process is None:
            return
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    def wait_for_stop(self, timeout_ms: int = 5000) -> bool:
        """
        Bloccante. USARE SOLO IN closeEvent, durante la shutdown.

        Nel funzionamento normale usare stop() + segnale sim_stopped.
        """
        if self._process is None:
            return True
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return True
        return self._process.waitForFinished(timeout_ms)

    # ------------------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------------------
    def _drain_output(self):
        """Legge stdout (che con MergedChannels contiene anche stderr)."""
        if self._process is None:
            return

        data = self._process.readAllStandardOutput()
        if data.isEmpty():
            return

        try:
            text = bytes(data).decode("utf-8", errors="replace")
        except Exception:
            text = data.data().decode("utf-8", errors="replace")

        self._line_buffer += text

        # Estrai solo le righe complete; tieni il frammento finale
        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            self._emit_line(line.rstrip("\r"))

    def _emit_line(self, line: str):
        if not line.strip():
            return
        self._history.append(line)
        self.sim_output.emit(line)

    # ------------------------------------------------------------------
    # SLOT QPROCESS
    # ------------------------------------------------------------------
    def _on_started(self):
        self.sim_started.emit()

    def _on_finished(self, exit_code: int, exit_status):
        self._kill_timer.stop()

        # Ultima lettura (potrebbe esserci dati residui nella pipe)
        if self._process is not None:
            self._drain_output()

        # Flush dell'eventuale frammento di riga senza newline
        if self._line_buffer.strip():
            self._emit_line(self._line_buffer.rstrip("\r"))
        self._line_buffer = ""

        was_stopping = self._stopping
        self._stopping = False
        self._config = None

        proc = self._process
        self._process = None
        if proc is not None:
            proc.deleteLater()

        self.sim_stopped.emit(exit_code)

        # Non segnalare come errore uno stop voluto dall'utente
        if exit_code != 0 and not was_stopping:
            self.sim_error.emit(
                f"Simulatore terminato con codice {exit_code}. "
                f"Controlla l'output nel pannello log."
            )

    def _on_error(self, error: QProcess.ProcessError):
        messages = {
            QProcess.ProcessError.FailedToStart:
                "Impossibile avviare il processo. "
                "Verifica Python e percorso del progetto.",
            QProcess.ProcessError.Crashed:
                "Il processo simulatore è crashato.",
            QProcess.ProcessError.Timedout:
                "Timeout del processo simulatore.",
            QProcess.ProcessError.WriteError:
                "Errore di scrittura verso il processo.",
            QProcess.ProcessError.ReadError:
                "Errore di lettura dal processo.",
        }
        msg = messages.get(error, f"Errore processo ({error})")

        detail = ""
        if self._process is not None:
            try:
                detail = self._process.errorString()
            except Exception:
                pass

        self.sim_error.emit(f"{msg} {detail}".strip())