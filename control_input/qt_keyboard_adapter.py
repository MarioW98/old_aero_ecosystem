"""
control_input/qt_keyboard_adapter.py

Adattatore Qt per l'input da tastiera nella GCS.

Dalla versione K2:
- Usa KeyBindingManager per la risoluzione dinamica dei tasti
- Emette segnali Qt per le azioni momentanee (pause, reset)
- Espone il binding_manager per la futura UI di configurazione (K3)
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from .keyboard_input import KeyboardInput
from .input_state import InputState
from .bindings import KeyBindingManager

try:
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from ipc_bus import ControlPublisher, ControlCommand
    IPC_AVAILABLE = True
except ImportError:
    IPC_AVAILABLE = False


class KeyboardControlManager(QObject):
    """
    Gestisce l'input da tastiera e pubblica comandi su ZMQ.

    Dalla versione K2, eredita da QObject per emettere segnali Qt
    per le azioni momentanee (pause, reset).

    Segnali:
        momentary_action(str): emesso quando un'azione momentanea
                               viene attivata (es. "pause", "reset").

    Uso in MainWindow:
        self._keyboard_mgr = KeyboardControlManager(self, publisher)
        self._keyboard_mgr.momentary_action.connect(self._on_momentary)
        self._keyboard_mgr.enable()
    """

    # Segnale per azioni momentanee (pause, reset, ecc.)
    momentary_action = Signal(str)

    UPDATE_INTERVAL_MS = 20  # 50 Hz

    def __init__(self, parent_widget, publisher=None,
                 binding_manager: KeyBindingManager = None):
        """
        Args:
            parent_widget: widget Qt padre (per il QTimer e QObject).
            publisher: ControlPublisher già avviato. Se None, non pubblica.
            binding_manager: KeyBindingManager. Se None, crea con defaults.
        """
        super().__init__(parent_widget)

        # Setup binding manager
        if binding_manager is None:
            binding_manager = KeyBindingManager()
            binding_manager.load_defaults()
        self._binding_manager = binding_manager

        # Setup keyboard input
        self._keyboard = KeyboardInput(binding_manager=self._binding_manager)
        self._publisher = publisher
        self._enabled = False
        self._last_state = InputState()

        # Timer per aggiornamento e pubblicazione
        self._timer = QTimer(self)
        self._timer.setInterval(self.UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Attivazione / disattivazione
    # ------------------------------------------------------------------
    def enable(self):
        """Attiva la cattura input e la pubblicazione."""
        self._enabled = True
        self._timer.start()

    def disable(self):
        """Disattiva la cattura input e rilascia i tasti."""
        self._enabled = False
        self._timer.stop()
        self._keyboard.clear()

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Eventi tastiera (chiamati dalla finestra Qt)
    # ------------------------------------------------------------------
    def handle_key_press(self, key: int):
        """Registra la pressione di un tasto."""
        if self._enabled:
            self._keyboard.key_pressed(key)

    def handle_key_release(self, key: int):
        """Registra il rilascio di un tasto."""
        if self._enabled:
            self._keyboard.key_released(key)

    def clear(self):
        """Rilascia tutti i tasti (es. perdita di focus)."""
        self._keyboard.clear()

    # ------------------------------------------------------------------
    # Loop di aggiornamento
    # ------------------------------------------------------------------
    def _tick(self):
        """Chiamato dal timer: aggiorna input, gestisce eventi, pubblica."""
        dt = self.UPDATE_INTERVAL_MS / 1000.0
        self._keyboard.update(dt)

        # Gestisci eventi momentanei (pause, reset, ecc.)
        for action in self._keyboard.pop_momentary_events():
            self.momentary_action.emit(action)

        # Pubblica stato su ZMQ
        state = self._keyboard.get_state()
        self._last_state = state

        if self._publisher is not None:
            cmd = ControlCommand(
                throttle=state.throttle,
                roll_stick=state.roll_stick,
                pitch_stick=state.pitch_stick,
                yaw_stick=state.yaw_stick,
            )
            self._publisher.publish(cmd)

    # ------------------------------------------------------------------
    # Accesso a binding manager (per K3/K4)
    # ------------------------------------------------------------------
    @property
    def binding_manager(self) -> KeyBindingManager:
        """Accesso al KeyBindingManager per la UI di configurazione."""
        return self._binding_manager

    # ------------------------------------------------------------------
    # Accesso allo stato (per debug/UI)
    # ------------------------------------------------------------------
    @property
    def current_state(self) -> InputState:
        return self._last_state

    @property
    def keyboard(self) -> KeyboardInput:
        return self._keyboard