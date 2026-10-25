"""
gcs_ui/sim_ui/ui/key_binding_dialog.py
Dialog di configurazione dei tasti di volo.
Permette all'utente di rimappare i tasti associati alle azioni di volo.
Lavora su una COPIA dei binding: le modifiche vengono applicate solo
se l'utente clicca "Salva".

NOTA DI RENDERING (Windows):
Il QTreeWidget con tema di sistema disegna l'highlight di selezione
SOPRA qualunque background personalizzato. Per eliminare il problema
alla radice:
- NoSelection + FocusPolicy.NoFocus  → nessun blu di selezione/focus
- setIndentation(0) + no decoration  → albero piatto, le celle coprono
  tutta la larghezza della riga, quindi setBackground() funziona.

STATI VISIVI DELLE RIGHE AZIONE (priorità decrescente):
- CAPTURE  (doppio-click) → giallo scuro, "in attesa di tasto"
- SELECTED (click)        → giallo medio, "riga attiva"
- HOVER    (mouse sopra)  → giallo chiaro, "riga cliccabile"
La gerarchia è gestita centralmente da _refresh_row_colors().
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeySequence, QColor, QBrush
from PySide6.QtWidgets import (
    QDialog, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyle,
)
import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from control_input.bindings import KeyBindingManager
from control_input.actions import ACTIONS, ActionType, get_actions_by_category


class _NoHighlightDelegate(QStyledItemDelegate):
    """Ignora selezione, focus e hover dell'item: il background impostato
    con setBackground() non viene più coperto dallo stile di sistema."""
    def paint(self, painter, option, index):
        option.state &= ~QStyle.StateFlag.State_Selected
        option.state &= ~QStyle.StateFlag.State_HasFocus
        option.state &= ~QStyle.StateFlag.State_MouseOver   # ← NEW
        super().paint(painter, option, index)


# ======================================================================
# COSTANTI
# ======================================================================
ACTION_TYPE_NAMES = {
    ActionType.INCREMENTAL: "Continuo",
    ActionType.POSITIONAL: "Posizionale",
    ActionType.MOMENTARY: "Singolo",
}

# Scala di colori per gli stati visivi (dal più chiaro al più scuro)
HOVER_BG = QColor(255, 248, 220)     # giallo chiarissimo — mouse sopra
SELECTED_BG = QColor(255, 235, 170)  # giallo medio — cliccato
CAPTURE_BG = QColor(255, 220, 130)   # giallo scuro — in attesa di tasto
CAPTURE_FG = QColor(0, 0, 0)         # testo nero su tutti gli stati


# ======================================================================
# HELPER
# ======================================================================
def _key_display_name(key: int | None) -> str:
    """Ritorna il nome leggibile di un tasto Qt."""
    if key is None or key == 0:
        return "—"
    return QKeySequence(key).toString()


def _copy_manager(source: KeyBindingManager) -> KeyBindingManager:
    """Crea una copia profonda di un KeyBindingManager."""
    copy = KeyBindingManager()
    for action, binding in source.get_all_bindings().items():
        copy.bind(
            action=binding.action,
            source_id=binding.source_id,
            source_type=binding.source_type,
            force=True,
        )
    return copy


# ======================================================================
# DIALOG
# ======================================================================
class KeyBindingDialog(QDialog):
    """
    Dialog per la configurazione dei tasti di volo.

    Mostra le azioni raggruppate per categoria. Click singolo per
    selezionare una riga (giallo medio), doppio-click per entrare in
    modalità "cattura tasto" (giallo scuro). Il passaggio del mouse
    evidenzia in giallo chiaro.
    """

    def __init__(self, binding_manager: KeyBindingManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione Tasti di Volo")
        self.setMinimumSize(560, 480)
        self.setModal(True)

        # Manager originale (da modificare solo su Salva)
        self._original_manager = binding_manager
        # Copia di lavoro (le modifiche avvengono qui)
        self._working_manager = _copy_manager(binding_manager)

        # Stato della modalità cattura
        self._capture_action: str | None = None

        # Stati visivi delle righe
        self._hover_item: QTreeWidgetItem | None = None
        self._selected_item: QTreeWidgetItem | None = None

        # Riferimenti agli item della tabella per aggiornamento rapido
        self._action_items: dict[str, QTreeWidgetItem] = {}

        self._build_ui()
        self._populate_tree()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Istruzioni
        instructions = QLabel(
            "Passa il mouse su un'azione per evidenziarla.\n"
            "Click per selezionare, doppio-click per riassegnare il tasto.\n"
            "Premi Esc durante la cattura per annullare."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Tabella azioni
        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Azione", "Tipo", "Tasto"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)

        # --- ELIMINA LE CAUSE DEL BLU ---
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tree.setRootIsDecorated(False)
        self._tree.setIndentation(0)

        # Delegate anti-highlight di sistema
        self._tree.setItemDelegate(_NoHighlightDelegate(self._tree))

        # --- HOVER: mouse tracking + event filter ---
        self._tree.setMouseTracking(True)
        self._tree.installEventFilter(self)

        # --- SELEZIONE: click singolo ---
        self._tree.itemClicked.connect(self._on_item_clicked)

        # --- CATTURA: doppio-click ---
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._tree.setStyleSheet(
            "QTreeView::item:selected, QTreeView::item:focus {"
            "  background: transparent; color: black; }"
        )

        # Dimensionamento colonne
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._tree, stretch=1)

        # Label di stato
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #555; font-style: italic;")
        layout.addWidget(self._status_label)

        # Pulsanti
        btn_layout = QHBoxLayout()

        self._btn_defaults = QPushButton("Ripristina Default")
        self._btn_defaults.clicked.connect(self._restore_defaults)
        btn_layout.addWidget(self._btn_defaults)

        btn_layout.addStretch()

        self._btn_cancel = QPushButton("Annulla")
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        self._btn_save = QPushButton("Salva")
        self._btn_save.setDefault(True)
        self._btn_save.clicked.connect(self._save)
        btn_layout.addWidget(self._btn_save)

        layout.addLayout(btn_layout)

    def _populate_tree(self):
        """Popola la tabella con le azioni raggruppate per categoria."""
        self._tree.clear()
        self._action_items.clear()
        self._hover_item = None
        self._selected_item = None

        categories = get_actions_by_category()

        for category, actions in categories.items():
            # Nodo categoria (riga in grassetto, non evidenziabile)
            cat_item = QTreeWidgetItem([category, "", ""])
            font = cat_item.font(0)
            font.setBold(True)
            cat_item.setFont(0, font)
            cat_item.setFlags(
                cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._tree.addTopLevelItem(cat_item)

            # Azioni della categoria
            for action_def in actions:
                key = self._working_manager.get_key(action_def.action_id)
                key_name = _key_display_name(key)
                type_name = ACTION_TYPE_NAMES.get(
                    action_def.action_type, "?")

                item = QTreeWidgetItem([
                    action_def.display_name,
                    type_name,
                    key_name,
                ])
                item.setData(0, Qt.ItemDataRole.UserRole,
                             action_def.action_id)
                cat_item.addChild(item)

                self._action_items[action_def.action_id] = item

            cat_item.setExpanded(True)

    # ------------------------------------------------------------------
    # GESTIONE COLORI CENTRALIZZATA
    # ------------------------------------------------------------------
    def _refresh_row_colors(self):
        """
        Applica i colori a tutte le righe azione secondo la priorità:
        capture > selected > hover > normale.

        Con ~10 righe il costo è trascurabile e il codice resta
        semplice e privo di bug di stato.
        """
        for action_id, item in self._action_items.items():
            if action_id == self._capture_action:
                bg = CAPTURE_BG
            elif item is self._selected_item:
                bg = SELECTED_BG
            elif item is self._hover_item:
                bg = HOVER_BG
            else:
                bg = None

            for col in range(self._tree.columnCount()):
                if bg is None:
                    item.setData(col, Qt.ItemDataRole.BackgroundRole, None)
                    item.setData(col, Qt.ItemDataRole.ForegroundRole, None)
                else:
                    item.setBackground(col, QBrush(bg))
                    item.setForeground(col, QBrush(CAPTURE_FG))

    # ------------------------------------------------------------------
    # EVENT FILTER — hover e leave
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        """Intercetta i movimenti del mouse sul tree per l'hover."""
        if obj is self._tree:
            if event.type() == QEvent.Type.MouseMove:
                item = self._tree.itemAt(event.pos())
                # Solo righe azione (hanno UserRole impostato)
                if item is not None and \
                        item.data(0, Qt.ItemDataRole.UserRole) is not None:
                    new_hover = item
                else:
                    new_hover = None
                if new_hover is not self._hover_item:
                    self._hover_item = new_hover
                    self._refresh_row_colors()
                return False

            if event.type() == QEvent.Type.Leave:
                # Il mouse è uscito dal tree: rimuovi hover
                if self._hover_item is not None:
                    self._hover_item = None
                    self._refresh_row_colors()
                return False

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # SELEZIONE (click singolo)
    # ------------------------------------------------------------------
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Gestisce il click singolo: seleziona la riga."""
        action_id = item.data(0, Qt.ItemDataRole.UserRole)
        if action_id is None:
            return  # categoria, ignora
        self._selected_item = item
        self._refresh_row_colors()

    # ------------------------------------------------------------------
    # CATTURA TASTO (doppio-click)
    # ------------------------------------------------------------------
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Gestisce il doppio-click su un'azione."""
        action_id = item.data(0, Qt.ItemDataRole.UserRole)
        if action_id is None:
            return  # Click su una categoria, ignora
        self._start_capture(action_id)

    def _start_capture(self, action_id: str):
        """Entra in modalità cattura per un'azione."""
        self._capture_action = action_id
        # Il doppio-click seleziona anche la riga (coerenza visiva)
        self._selected_item = self._action_items.get(action_id)

        action_def = ACTIONS[action_id]
        self._status_label.setText(
            f"Premi un tasto per «{action_def.display_name}»... "
            f"(Esc per annullare)")

        self._refresh_row_colors()

        # Il focus va al dialog (non al tree) per intercettare i tasti
        self.setFocus()

    def _cancel_capture(self):
        """Annulla la modalità cattura."""
        self._capture_action = None
        self._status_label.setText("")
        self._refresh_row_colors()

    def keyPressEvent(self, event):
        """Intercetta i tasti durante la modalità cattura."""
        if self._capture_action is not None:
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_capture()
                return
            self._assign_key(self._capture_action, event.key())
            return
        # Comportamento default (Esc chiude il dialog)
        super().keyPressEvent(event)

    def _assign_key(self, action_id: str, key: int):
        """Assegna un tasto a un'azione, gestendo i conflitti."""
        action_def = ACTIONS[action_id]

        # Verifica conflitto
        existing_action = self._working_manager.get_action_by_key(key)
        if existing_action is not None and existing_action != action_id:
            existing_def = ACTIONS[existing_action]
            reply = QMessageBox.question(
                self,
                "Conflitto di assegnazione",
                f"Il tasto «{_key_display_name(key)}» è già assegnato a "
                f"«{existing_def.display_name}».\n\n"
                f"Vuoi riassegnarlo a «{action_def.display_name}»?\n"
                f"«{existing_def.display_name}» rimarrà senza tasto.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._cancel_capture()
                return

        # Applica il binding
        success = self._working_manager.bind(
            action=action_id,
            source_id=key,
            source_type="keyboard",
            force=True,
        )

        if not success:
            QMessageBox.warning(
                self, "Errore",
                f"Impossibile assegnare il tasto a "
                f"«{action_def.display_name}».")
            self._cancel_capture()
            return

        # Aggiorna la tabella
        self._refresh_all_key_display()

        # Esci dalla modalità cattura (la riga resta selezionata)
        self._cancel_capture()
        self._status_label.setText(
            f"«{action_def.display_name}» → "
            f"{_key_display_name(key)}",
        )

    def _refresh_all_key_display(self):
        """Aggiorna la colonna 'Tasto' per tutte le azioni."""
        for action_id, item in self._action_items.items():
            key = self._working_manager.get_key(action_id)
            item.setText(2, _key_display_name(key))

    # ------------------------------------------------------------------
    # PULSANTI
    # ------------------------------------------------------------------
    def _restore_defaults(self):
        """Ripristina la mappatura di default nella copia di lavoro."""
        reply = QMessageBox.question(
            self,
            "Ripristina default",
            "Vuoi ripristinare la mappatura di default?\n"
            "Le modifiche non salvate verranno perse.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._cancel_capture()
        self._working_manager.load_defaults()
        self._refresh_all_key_display()
        self._refresh_row_colors()
        self._status_label.setText("Mappatura di default ripristinata.")

    def _save(self):
        """Applica le modifiche al manager originale e chiude."""
        self._cancel_capture()

        if self._working_manager.has_conflicts():
            QMessageBox.warning(
                self, "Conflitti",
                "Ci sono conflitti nella mappatura. "
                "Risolvili prima di salvare.")
            return

        self._original_manager.clear()
        for action, binding in \
                self._working_manager.get_all_bindings().items():
            self._original_manager.bind(
                action=binding.action,
                source_id=binding.source_id,
                source_type=binding.source_type,
                force=True,
            )

        self.accept()