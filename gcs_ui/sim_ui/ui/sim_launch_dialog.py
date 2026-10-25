"""
gcs_ui/sim_ui/ui/sim_launch_dialog.py

Dialog di configurazione per il lancio della simulazione.

Permette all'utente di selezionare:
- Velivolo (da registry o profili salvati)
- Condizioni iniziali (quota, velocità, α)
- Modalità flight controller (stabilize/manual)
- Gain scheduling on/off

Il pulsante "Anteprima trim" risolve il trim prima del lancio e mostra
i valori di equilibrio, segnalando se il punto non è trimmabile.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox,
    QCheckBox, QMessageBox, QGroupBox,
)

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SIMULATOR_ROOT = _PROJECT_ROOT / "simulator"

for _p in (str(_PROJECT_ROOT), str(_SIMULATOR_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Stesse convenzioni di run_sim.py
try:
    from aircraft.c172 import make_c172_aircraft
    from flight_controller.trim_solver import TrimSolver
    FC_AVAILABLE = True
except ImportError as _e:
    FC_AVAILABLE = False
    _FC_IMPORT_ERROR = str(_e)


# ======================================================================
# CONFIGURAZIONE
# ======================================================================

class SimLaunchConfig:
    """Configurazione della simulazione selezionata dall'utente."""
    
    def __init__(self):
        self.aircraft: str = "C172"
        self.altitude: float = 500.0       # m
        self.speed: float = 45.0           # m/s
        self.alpha: float = 5.0            # deg
        self.fc_mode: str = "stabilize"    # "stabilize" | "manual"
        self.gain_schedule: bool = False
        self.throttle: float = 0.6         # throttle iniziale (default)


# ======================================================================
# DIALOG
# ======================================================================

class SimLaunchDialog(QDialog):
    """
    Dialog di configurazione per il lancio della simulazione.
    
    Uso:
        config = SimLaunchConfig()
        dlg = SimLaunchDialog(config, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # config è stato aggiornato dall'utente
            launch_simulation(config)
    """
    
    def __init__(self, config: SimLaunchConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione Simulazione")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        self._config = config
        self._build_ui()
        self._populate_from_config()
    
    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Gruppo: Velivolo ---
        aircraft_group = QGroupBox("Velivolo")
        aircraft_layout = QFormLayout()
        
        self._combo_aircraft = QComboBox()
        self._combo_aircraft.addItems(["C172"])  # In futuro: J3, Biplane, eVTOL
        aircraft_layout.addRow("Modello:", self._combo_aircraft)
        
        aircraft_group.setLayout(aircraft_layout)
        layout.addWidget(aircraft_group)
        
        # --- Gruppo: Condizioni iniziali ---
        conditions_group = QGroupBox("Condizioni Iniziali")
        conditions_layout = QFormLayout()
        
        self._spin_altitude = QDoubleSpinBox()
        self._spin_altitude.setRange(0.0, 10000.0)
        self._spin_altitude.setSingleStep(100.0)
        self._spin_altitude.setSuffix(" m")
        self._spin_altitude.setDecimals(0)
        conditions_layout.addRow("Quota:", self._spin_altitude)
        
        self._spin_speed = QDoubleSpinBox()
        self._spin_speed.setRange(0.0, 200.0)
        self._spin_speed.setSingleStep(5.0)
        self._spin_speed.setSuffix(" m/s")
        self._spin_speed.setDecimals(1)
        conditions_layout.addRow("Velocità:", self._spin_speed)
        
        self._spin_alpha = QDoubleSpinBox()
        self._spin_alpha.setRange(-20.0, 30.0)
        self._spin_alpha.setSingleStep(1.0)
        self._spin_alpha.setSuffix("°")
        self._spin_alpha.setDecimals(1)
        conditions_layout.addRow("Angolo α:", self._spin_alpha)
        
        self._spin_throttle = QDoubleSpinBox()
        self._spin_throttle.setRange(0.0, 1.0)
        self._spin_throttle.setSingleStep(0.05)
        self._spin_throttle.setDecimals(2)
        conditions_layout.addRow("Throttle iniziale:", self._spin_throttle)
        
        conditions_group.setLayout(conditions_layout)
        layout.addWidget(conditions_group)
        
        # --- Gruppo: Flight Controller ---
        fc_group = QGroupBox("Flight Controller")
        fc_layout = QFormLayout()
        
        self._combo_fc_mode = QComboBox()
        self._combo_fc_mode.addItems(["stabilize", "manual"])
        fc_layout.addRow("Modalità:", self._combo_fc_mode)
        
        self._check_gain_schedule = QCheckBox("Abilita gain scheduling (avvio più lento)")
        fc_layout.addRow("", self._check_gain_schedule)
        
        fc_group.setLayout(fc_layout)
        layout.addWidget(fc_group)
        
        # --- Pulsante Anteprima Trim ---
        if FC_AVAILABLE:
            trim_layout = QHBoxLayout()
            self._btn_trim = QPushButton("Anteprima Trim")
            self._btn_trim.setToolTip(
                "Risolve il trim per verificare che il punto sia trimmabile.\n"
                "Mostra α, δe, throttle di equilibrio."
            )
            self._btn_trim.clicked.connect(self._on_trim_preview)
            trim_layout.addWidget(self._btn_trim)
            
            self._lbl_trim_result = QLabel("")
            self._lbl_trim_result.setStyleSheet("color: #555; font-style: italic;")
            trim_layout.addWidget(self._lbl_trim_result, stretch=1)
            
            layout.addLayout(trim_layout)
        else:
            layout.addWidget(QLabel(
                "⚠ Flight controller non disponibile (import fallito)"))
        
        # --- Pulsanti finali ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._btn_cancel = QPushButton("Annulla")
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)
        
        self._btn_launch = QPushButton("Avvia Simulazione")
        self._btn_launch.setDefault(True)
        self._btn_launch.clicked.connect(self.accept)
        btn_layout.addWidget(self._btn_launch)
        
        layout.addLayout(btn_layout)
    
    def _populate_from_config(self):
        """Riempie i campi dal config."""
        cfg = self._config
        
        # Aircraft
        idx = self._combo_aircraft.findText(cfg.aircraft)
        if idx >= 0:
            self._combo_aircraft.setCurrentIndex(idx)
        
        # Condizioni
        self._spin_altitude.setValue(cfg.altitude)
        self._spin_speed.setValue(cfg.speed)
        self._spin_alpha.setValue(cfg.alpha)
        self._spin_throttle.setValue(cfg.throttle)
        
        # FC
        idx = self._combo_fc_mode.findText(cfg.fc_mode)
        if idx >= 0:
            self._combo_fc_mode.setCurrentIndex(idx)
        self._check_gain_schedule.setChecked(cfg.gain_schedule)
    
    def _update_config(self):
        """Aggiorna il config dai campi del dialog."""
        cfg = self._config
        cfg.aircraft = self._combo_aircraft.currentText()
        cfg.altitude = self._spin_altitude.value()
        cfg.speed = self._spin_speed.value()
        cfg.alpha = self._spin_alpha.value()
        cfg.throttle = self._spin_throttle.value()
        cfg.fc_mode = self._combo_fc_mode.currentText()
        cfg.gain_schedule = self._check_gain_schedule.isChecked()
    
    # ------------------------------------------------------------------
    # ANTEPRIMA TRIM
    # ------------------------------------------------------------------
    def _on_trim_preview(self):
        """Risolve il trim e mostra il risultato."""
        if not FC_AVAILABLE:
            QMessageBox.warning(
                self, "Errore",
                "Flight controller non disponibile.")
            return
        
        self._update_config()
        cfg = self._config
        
        try:
            # Carica il velivolo
            if cfg.aircraft == "C172":
                aircraft = make_c172_aircraft()
            else:
                self._lbl_trim_result.setText("Velivolo non supportato")
                return
            
            # Risolve il trim
            solver = TrimSolver(aircraft)
            trim = solver.solve(V=cfg.speed, altitude=cfg.altitude)
            
            if trim.converged:
                import math
                alpha_deg = math.degrees(trim.alpha)
                de_deg = math.degrees(trim.delta_e)
                self._lbl_trim_result.setText(
                    f"✓ Trim OK: α={alpha_deg:+.1f}°, "
                    f"δe={de_deg:+.1f}°, thr={trim.throttle:.2f}"
                )
                self._lbl_trim_result.setStyleSheet(
                    "color: green; font-style: italic;")
            else:
                self._lbl_trim_result.setText(
                    f"✗ Trim fallito: {trim.reason}"
                )
                self._lbl_trim_result.setStyleSheet(
                    "color: red; font-style: italic;")
        
        except Exception as e:
            self._lbl_trim_result.setText(f"Errore: {e}")
            self._lbl_trim_result.setStyleSheet(
                "color: red; font-style: italic;")
    
    # ------------------------------------------------------------------
    # OVERRIDE accept
    # ------------------------------------------------------------------
    def accept(self):
        """Aggiorna il config e chiude il dialog."""
        self._update_config()
        super().accept()