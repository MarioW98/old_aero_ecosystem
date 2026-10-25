from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QInputDialog, QMessageBox,
)

from ..core.presets import PresetManager


class PresetDialog(QDialog):
    """Dialog per rinominare ed eliminare i preset."""

    def __init__(self, manager: PresetManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self.setWindowTitle("Gestisci Preset")
        self.resize(360, 320)

        layout = QVBoxLayout(self)

        # Lista preset
        self._list = QListWidget()
        layout.addWidget(self._list)

        # Pulsanti
        btn_row = QHBoxLayout()

        self._btn_rename = QPushButton("Rinomina")
        self._btn_rename.clicked.connect(self._rename)
        btn_row.addWidget(self._btn_rename)

        self._btn_delete = QPushButton("Elimina")
        self._btn_delete.clicked.connect(self._delete)
        btn_row.addWidget(self._btn_delete)

        btn_row.addStretch()

        self._btn_close = QPushButton("Chiudi")
        self._btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self._btn_close)

        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        self._list.clear()
        for name in self._manager.list_presets():
            self._list.addItem(name)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _selected_name(self) -> str | None:
        item = self._list.currentItem()
        return item.text() if item else None

    def _rename(self):
        name = self._selected_name()
        if not name:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rinomina preset", "Nuovo nome:", text=name
        )
        if not ok or not new_name.strip() or new_name.strip() == name:
            return
        if self._manager.rename_preset(name, new_name.strip()):
            self._refresh()
        else:
            QMessageBox.warning(self, "Errore", "Rinomina non riuscita.")

    def _delete(self):
        name = self._selected_name()
        if not name:
            return
        reply = QMessageBox.question(
            self, "Elimina preset",
            f"Eliminare il preset '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.delete_preset(name)
            self._refresh()