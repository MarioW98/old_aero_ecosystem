from __future__ import annotations

import json
import re
from pathlib import Path


class PresetManager:
    """
    Gestisce una libreria di preset di pannello.
    Ogni preset è un file JSON nella cartella 'presets/'.
    """

    def __init__(self, presets_dir=None):
        if presets_dir is None:
            # Cartella presets accanto al pacchetto sim_ui
            presets_dir = Path(__file__).resolve().parent.parent / "presets"
        self._dir = Path(presets_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._dir

    # =========================================================================
    # ELENCO
    # =========================================================================

    def list_presets(self) -> list[str]:
        """Restituisce i nomi dei preset ordinati alfabeticamente."""
        return sorted(f.stem for f in self._dir.glob("*.json"))

    def preset_exists(self, name: str) -> bool:
        return (self._dir / f"{self._sanitize(name)}.json").exists()

    # =========================================================================
    # SALVATAGGIO / CARICAMENTO
    # =========================================================================

    def save_preset(self, name: str, layout_dict: dict) -> bool:
        """Salva un layout come preset. Ritorna True se riuscito."""
        safe = self._sanitize(name)
        if not safe:
            return False
        path = self._dir / f"{safe}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(layout_dict, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def load_preset(self, name: str) -> dict | None:
        """Carica un preset. Ritorna il dict del layout o None."""
        path = self._dir / f"{self._sanitize(name)}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # =========================================================================
    # ELIMINAZIONE / RINOMINA
    # =========================================================================

    def delete_preset(self, name: str) -> bool:
        path = self._dir / f"{self._sanitize(name)}.json"
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception:
                return False
        return False

    def rename_preset(self, old_name: str, new_name: str) -> bool:
        data = self.load_preset(old_name)
        if data is None:
            return False
        if self.save_preset(new_name, data):
            return self.delete_preset(old_name)
        return False

    # =========================================================================
    # UTILITY
    # =========================================================================

    @staticmethod
    def _sanitize(name: str) -> str:
        """Rimuove caratteri non validi per un nome di file."""
        cleaned = re.sub(r"[^\w\s\-]", "", name).strip()
        return cleaned