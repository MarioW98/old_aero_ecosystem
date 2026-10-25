"""
control_input/bindings.py

KeyBindingManager: gestisce la mappatura azione → sorgente di input.

Il modello dati è progettato per supportare sorgenti multiple:
- Tastiera (source_type="keyboard", source_id=Qt.Key)
- Joystick axis (source_type="joystick_axis", source_id=indice asse)
- Joystick button (source_type="joystick_button", source_id=indice pulsante)

Per ora è implementata solo la tastiera, ma il modello è già pronto
per il joystick (Fase futura).

Persistenza: JSON con versionamento per forward/backward compatibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from .actions import ACTIONS


# ======================================================================
# MODELLO DATI
# ======================================================================

@dataclass
class InputBinding:
    """
    Un singolo binding: associa un'azione a una sorgente di input.

    Attributes:
        action: ID dell'azione (es. "throttle_up").
        source_type: Tipo di sorgente ("keyboard", "joystick_axis",
                     "joystick_button").
        source_id: Identificatore della sorgente.
                   Per tastiera: valore Qt.Key (es. 87 per W).
                   Per joystick: indice asse/pulsante.
        axis_direction: Per assi joystick: -1 o +1 per la direzione.
                        0 per tastiera e pulsanti.
    """
    action: str
    source_type: str
    source_id: int
    axis_direction: int = 0


# ======================================================================
# KEY BINDING MANAGER
# ======================================================================

class KeyBindingManager:
    """
    Gestisce la mappatura azione → sorgente di input.

    Fornisce:
    - bind/unbind con rilevamento conflitti
    - Query bidirezionali (azione→tasto, tasto→azione)
    - Persistenza JSON (save/load)
    - Caricamento defaults

    Uso:
        mgr = KeyBindingManager()
        mgr.load_defaults()
        mgr.bind("throttle_up", Qt.Key_W)
        key = mgr.get_key("throttle_up")       # → Qt.Key_W
        action = mgr.get_action_by_key(87)      # → "throttle_up"
        mgr.save("bindings.json")
    """

    SCHEMA_VERSION = 1

    def __init__(self):
        # action_id → InputBinding
        self._bindings: dict[str, InputBinding] = {}
        # (source_type, source_id) → action_id  (lookup inverso)
        self._reverse: dict[tuple[str, int], str] = {}

    # ------------------------------------------------------------------
    # BIND / UNBIND
    # ------------------------------------------------------------------
    def bind(self, action: str, source_id: int,
             source_type: str = "keyboard",
             force: bool = False) -> bool:
        """
        Associa una sorgente a un'azione.

        Args:
            action: ID dell'azione (deve esistere in ACTIONS).
            source_id: Qt.Key per tastiera, indice per joystick.
            source_type: "keyboard", "joystick_axis", "joystick_button".
            force: Se True, sovrascrive anche in caso di conflitto.
                   Se False, ritorna False se la sorgente è già usata.

        Returns:
            True se il binding è stato creato, False altrimenti.
        """
        if action not in ACTIONS:
            return False

        # Verifica conflitto: la sorgente è già usata da un'altra azione?
        existing_action = self.get_action_by_source(source_id, source_type)
        if existing_action is not None and existing_action != action:
            if not force:
                return False
            # Rimuovi il binding precedente per quella sorgente
            self.unbind(existing_action)

        # Rimuovi il binding precedente per questa azione (se esiste)
        if action in self._bindings:
            old = self._bindings[action]
            old_key = (old.source_type, old.source_id)
            if old_key in self._reverse:
                del self._reverse[old_key]

        # Crea il nuovo binding
        binding = InputBinding(
            action=action,
            source_type=source_type,
            source_id=source_id,
        )
        self._bindings[action] = binding
        self._reverse[(source_type, source_id)] = action
        return True

    def unbind(self, action: str) -> bool:
        """Rimuove il binding per un'azione. Ritorna True se esisteva."""
        if action not in self._bindings:
            return False
        binding = self._bindings.pop(action)
        rev_key = (binding.source_type, binding.source_id)
        if rev_key in self._reverse:
            del self._reverse[rev_key]
        return True

    def unbind_source(self, source_id: int, source_type: str = "keyboard") -> bool:
        """Rimuove il binding per una sorgente specifica."""
        action = self.get_action_by_source(source_id, source_type)
        if action is not None:
            return self.unbind(action)
        return False

    # ------------------------------------------------------------------
    # QUERY
    # ------------------------------------------------------------------
    def get_binding(self, action: str) -> Optional[InputBinding]:
        """Ritorna il binding completo per un'azione."""
        return self._bindings.get(action)

    def get_key(self, action: str) -> Optional[int]:
        """
        Ritorna il tasto Qt.Key associato a un'azione (solo tastiera).
        Ritorna None se l'azione non ha binding o non è tastiera.
        """
        binding = self._bindings.get(action)
        if binding and binding.source_type == "keyboard":
            return binding.source_id
        return None

    def get_action_by_source(self, source_id: int,
                             source_type: str = "keyboard") -> Optional[str]:
        """Ritorna l'azione associata a una sorgente di input."""
        return self._reverse.get((source_type, source_id))

    def get_action_by_key(self, key: int) -> Optional[str]:
        """Shortcut per tastiera: ritorna l'azione per un Qt.Key."""
        return self.get_action_by_source(key, "keyboard")

    def get_all_bindings(self) -> dict[str, InputBinding]:
        """Ritorna una copia di tutti i binding."""
        return dict(self._bindings)

    def get_bound_actions(self) -> list[str]:
        """Ritorna la lista delle azioni che hanno un binding."""
        return list(self._bindings.keys())

    def get_unbound_actions(self) -> list[str]:
        """Ritorna la lista delle azioni senza binding."""
        return [a for a in ACTIONS if a not in self._bindings]

    def has_conflicts(self) -> bool:
        """Verifica se ci sono conflitti (dovrebbe essere sempre False)."""
        seen_sources: set[tuple[str, int]] = set()
        for binding in self._bindings.values():
            key = (binding.source_type, binding.source_id)
            if key in seen_sources:
                return True
            seen_sources.add(key)
        return False

    # ------------------------------------------------------------------
    # DEFAULTS
    # ------------------------------------------------------------------
    def load_defaults(self):
        """
        Carica la mappatura di default.
        Usa i valori Qt.Key direttamente (import pigro per non
        richiedere Qt al momento dell'import del modulo).
        """
        from PySide6.QtCore import Qt

        defaults = {
            "throttle_up": Qt.Key_W,
            "throttle_down": Qt.Key_S,
            "pitch_up": Qt.Key_Up,
            "pitch_down": Qt.Key_Down,
            "roll_left": Qt.Key_Left,
            "roll_right": Qt.Key_Right,
            "yaw_left": Qt.Key_A,
            "yaw_right": Qt.Key_D,
            "pause": Qt.Key_P,
            "reset": Qt.Key_R,
        }

        self._bindings.clear()
        self._reverse.clear()

        for action, key in defaults.items():
            binding = InputBinding(
                action=action,
                source_type="keyboard",
                source_id=int(key),
            )
            self._bindings[action] = binding
            self._reverse[("keyboard", int(key))] = action

    # ------------------------------------------------------------------
    # PERSISTENZA JSON
    # ------------------------------------------------------------------
    def save(self, path: str | Path) -> bool:
        """
        Salva i binding su file JSON.

        Args:
            path: Percorso del file.

        Returns:
            True se salvato con successo.
        """
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": self.SCHEMA_VERSION,
                "bindings": {
                    action: asdict(binding)
                    for action, binding in self._bindings.items()
                },
            }

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def load(self, path: str | Path) -> bool:
        """
        Carica i binding da file JSON.

        Args:
            path: Percorso del file.

        Returns:
            True se caricato con successo, False altrimenti.
            Se False, lo stato del manager non viene modificato.
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, OSError):
            return False

        if not isinstance(data, dict):
            return False
        if data.get("version") != self.SCHEMA_VERSION:
            return False

        # Costruisci il nuovo stato in strutture temporanee
        new_bindings: dict[str, InputBinding] = {}
        new_reverse: dict[tuple[str, int], str] = {}

        for action, bdata in data.get("bindings", {}).items():
            # Ignora azioni non nel catalogo (forward compatibility)
            if action not in ACTIONS:
                continue
            try:
                binding = InputBinding(
                    action=bdata["action"],
                    source_type=bdata.get("source_type", "keyboard"),
                    source_id=int(bdata["source_id"]),
                    axis_direction=int(bdata.get("axis_direction", 0)),
                )
            except (KeyError, ValueError, TypeError):
                continue

            new_bindings[action] = binding
            new_reverse[(binding.source_type, binding.source_id)] = action

        # Applica il nuovo stato solo se tutto è valido
        self._bindings = new_bindings
        self._reverse = new_reverse
        return True

    def load_or_defaults(self, path: str | Path) -> bool:
        """
        Prova a caricare da file. Se fallisce, carica i defaults.

        Returns:
            True se caricato da file, False se sono stati usati i defaults.
        """
        if self.load(path):
            return True
        self.load_defaults()
        return False

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------
    def clear(self):
        """Rimuove tutti i binding."""
        self._bindings.clear()
        self._reverse.clear()

    def __len__(self) -> int:
        return len(self._bindings)

    def __repr__(self) -> str:
        return f"KeyBindingManager({len(self._bindings)} bindings)"