"""
control_input/keyboard_input.py

Cattura input da tastiera e produce InputState.

Dalla versione K2, i tasti NON sono più hardcoded: vengono risolti
dinamicamente tramite il KeyBindingManager. Questo permette di
rimappare i controlli a runtime senza modificare questo file.

Tipi di azione gestiti:
- INCREMENTAL (throttle): tenere premuto cambia il valore nel tempo
- POSITIONAL (stick): tenere premuto imposta ±1, rilascio torna a 0
- MOMENTARY (pause/reset): pressione singola genera un evento
"""

from __future__ import annotations

from .input_state import InputState
from .bindings import KeyBindingManager
from .actions import get_action, ActionType


class KeyboardInput:
    """
    Gestisce lo stato dei tasti premuti e produce un InputState.

    I tasti vengono risolti dinamicamente tramite il KeyBindingManager.
    Questo permette di cambiare mappatura a runtime.

    Uso:
        mgr = KeyBindingManager()
        mgr.load_defaults()
        kb = KeyboardInput(binding_manager=mgr)
        kb.key_pressed(87)       # W
        kb.update(0.02)
        state = kb.get_state()
    """

    # Velocità di variazione del throttle (unità al secondo)
    THROTTLE_RATE = 0.5

    def __init__(self, binding_manager: KeyBindingManager = None,
                 initial_throttle: float = 0.0):
        """
        Args:
            binding_manager: KeyBindingManager per risolvere i tasti.
                             Se None, ne crea uno con i defaults.
            initial_throttle: valore iniziale del throttle [0, 1].
        """
        if binding_manager is None:
            binding_manager = KeyBindingManager()
            binding_manager.load_defaults()

        self._bindings = binding_manager
        self._pressed_keys: set = set()
        self._throttle: float = max(0.0, min(1.0, initial_throttle))
        self._momentary_queue: list[str] = []

    # ------------------------------------------------------------------
    # Eventi tastiera (chiamati dalla GUI)
    # ------------------------------------------------------------------
    def key_pressed(self, key: int):
        """Registra la pressione di un tasto."""
        is_repeat = key in self._pressed_keys
        self._pressed_keys.add(key)

        # Azioni momentanee: solo sulla prima pressione (no auto-repeat)
        if not is_repeat:
            action = self._bindings.get_action_by_key(key)
            if action:
                action_def = get_action(action)
                if action_def and action_def.action_type == ActionType.MOMENTARY:
                    self._momentary_queue.append(action)

    def key_released(self, key: int):
        """Registra il rilascio di un tasto."""
        self._pressed_keys.discard(key)

    def clear(self):
        """Rilascia tutti i tasti (es. quando la finestra perde il focus)."""
        self._pressed_keys.clear()

    # ------------------------------------------------------------------
    # Aggiornamento (chiamato ogni frame)
    # ------------------------------------------------------------------
    def update(self, dt: float):
        """
        Aggiorna i comandi incrementali (throttle).
        Deve essere chiamato ogni frame con il delta time.

        Args:
            dt: tempo trascorso dall'ultimo aggiornamento [s].
        """
        # Throttle up
        key_up = self._bindings.get_key("throttle_up")
        if key_up is not None and key_up in self._pressed_keys:
            self._throttle += self.THROTTLE_RATE * dt

        # Throttle down
        key_down = self._bindings.get_key("throttle_down")
        if key_down is not None and key_down in self._pressed_keys:
            self._throttle -= self.THROTTLE_RATE * dt

        # Clamp
        self._throttle = max(0.0, min(1.0, self._throttle))

    # ------------------------------------------------------------------
    # Stato corrente
    # ------------------------------------------------------------------
    def get_state(self) -> InputState:
        """Restituisce lo stato corrente dei comandi."""
        # Pitch (POSITIONAL)
        pitch = 0.0
        key = self._bindings.get_key("pitch_up")
        if key is not None and key in self._pressed_keys:
            pitch += 1.0
        key = self._bindings.get_key("pitch_down")
        if key is not None and key in self._pressed_keys:
            pitch -= 1.0

        # Roll (POSITIONAL)
        roll = 0.0
        key = self._bindings.get_key("roll_right")
        if key is not None and key in self._pressed_keys:
            roll += 1.0
        key = self._bindings.get_key("roll_left")
        if key is not None and key in self._pressed_keys:
            roll -= 1.0

        # Yaw (POSITIONAL)
        yaw = 0.0
        key = self._bindings.get_key("yaw_right")
        if key is not None and key in self._pressed_keys:
            yaw += 1.0
        key = self._bindings.get_key("yaw_left")
        if key is not None and key in self._pressed_keys:
            yaw -= 1.0

        return InputState(
            throttle=self._throttle,
            pitch_stick=pitch,
            roll_stick=roll,
            yaw_stick=yaw,
        )

    # ------------------------------------------------------------------
    # Eventi momentanei
    # ------------------------------------------------------------------
    def pop_momentary_events(self) -> list[str]:
        """
        Ritorna e svuota la coda di eventi momentanei.

        Returns:
            Lista di action_id (es. ["pause", "reset"]).
        """
        events = list(self._momentary_queue)
        self._momentary_queue.clear()
        return events

    def has_momentary_events(self) -> bool:
        """Verifica se ci sono eventi momentanei in coda."""
        return len(self._momentary_queue) > 0

    # ------------------------------------------------------------------
    # Proprietà
    # ------------------------------------------------------------------
    @property
    def throttle(self) -> float:
        return self._throttle

    @throttle.setter
    def throttle(self, value: float):
        self._throttle = max(0.0, min(1.0, value))

    @property
    def pressed_keys(self) -> set:
        """Insieme dei tasti attualmente premuti (per debug/UI)."""
        return self._pressed_keys.copy()

    @property
    def binding_manager(self) -> KeyBindingManager:
        """Accesso al KeyBindingManager (per K3/K4)."""
        return self._bindings