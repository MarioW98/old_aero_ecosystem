"""
gcs_ui/sim_ui/ui/window.py

Finestra principale della GCS.
Sistema di telemetria UNIFICATO: Mock / External / ZeroMQ / Test / Pause.
"""

import json
import uuid
import shiboken6
from PySide6.QtCore import Qt, QPointF, QPoint, QMimeData, QTimer, QSettings
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QPainter, QShortcut, QTransform
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QTextEdit,
    QApplication, QDockWidget, QFileDialog, QGraphicsItem, QMenuBar,
    QMainWindow, QMenu, QMessageBox, QToolBar, QGraphicsView,
    QLabel, QInputDialog, QStatusBar,
)
from ..core.constants import LAYOUT_SCHEMA_VERSION, DEFAULT_GRID_SIZE
from ..core.prototype import InstrumentRegistry, build_default_registry
from ..core.telemetry import (
    TelemetryData, TelemetryAdapter,
    MockTelemetryAdapter, ExternalTelemetryAdapter,
)
from .hangar_instr import HangarDockWidget
from .scene import InstrumentScene
from .view import InstrumentGraphicsView, FPSCounter, OPENGL_AVAILABLE
from ..instruments.base import BaseInstrument
from ..instruments.factory import InstrumentFactory
from ..core.theme import InstrumentTheme, ThemeRegistry, build_default_themes
from ..core.presets import PresetManager
from ..core.zmq_adapter import ZMQTelemetryAdapter
from ipc_bus.trajectory import create_trajectory
from ipc_bus.trajectory_adapter import TrajectoryTelemetryAdapter
from ipc_bus import ControlPublisher, ZMQConfig
from control_input.bindings import KeyBindingManager
from control_input.qt_keyboard_adapter import KeyboardControlManager
from .key_binding_dialog import KeyBindingDialog
from .sim_launch_dialog import SimLaunchDialog, SimLaunchConfig
from ..sim_manager import SimManager
from pathlib import Path
from ipc_bus import ControlPublisher, ZMQConfig
from control_input.qt_keyboard_adapter import KeyboardControlManager
from .preset_dialog import PresetDialog


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flight Simulator UI — Fase 8")
        self.resize(1400, 900)

        self._spawn_index = 0
        self._instrument_cache: list = []
        self._instrument_cache_dirty = True
        self._preview_mode = False
        self._snap_enabled = False
        self._grid_size = DEFAULT_GRID_SIZE

        self._registry = build_default_registry()
        self._theme_registry = build_default_themes()

        # Preset di pannello
        self._preset_manager = PresetManager()
        self._current_theme = self._theme_registry.default()

        # Stato OpenGL
        self._opengl_enabled = False
        self._target_fps = 20
        self._fps_actions: dict[int, QAction] = {}

        # Scena
        self._scene = InstrumentScene(self)
        self._scene.setSceneRect(-800, -450, 1600, 900)
        self._scene.set_grid_size(self._grid_size)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        # View
        self._view = InstrumentGraphicsView(self._scene)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._view.instrument_dropped.connect(self.add_instrument_at)
        self._view.context_menu_requested.connect(self._show_context_menu)
        self._view.cursor_moved.connect(self._on_cursor_moved)
        self.setCentralWidget(self._view)

        # Hangar
        self._hangar = HangarDockWidget(self._registry, self)
        self._hangar.instrument_requested.connect(self.add_instrument_by_type)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._hangar)

        # =============================================================
        # SIMULATORE — MANAGER (deve esistere prima di _create_menu)
        # =============================================================
        self._sim_manager = SimManager(self)
        self._sim_manager.sim_started.connect(self._on_sim_started)
        self._sim_manager.sim_stopped.connect(self._on_sim_stopped)
        self._sim_manager.sim_error.connect(self._on_sim_error)
        self._sim_manager.sim_output.connect(self._on_sim_output)
        self._settings = QSettings("AeroControlQwen", "GCS_SimUI")
        # Menu, toolbar, shortcuts
        self._create_menu()
        # Preferenze persistenti (usate anche da _create_menu)
        self._create_toolbar()
        self._create_shortcuts()

        # ====================================================================
        # SETUP TELEMETRIA — SISTEMA UNIFICATO
        # ====================================================================
        self._telemetry_adapter: TelemetryAdapter | None = None
        adapter = MockTelemetryAdapter(self)
        adapter.set_interval(int(1000 / self._target_fps))
        self._set_telemetry_adapter(adapter)

        # Adapter ZeroMQ (creato ma non avviato)
        self._zmq_adapter = ZMQTelemetryAdapter(
            parent=self,
            endpoint="tcp://127.0.0.1:5555",
            auto_start=False,
        )
        # Collega ZMQ → stesso handler telemetria esistente
        self._zmq_adapter.set_external_callback(self._on_telemetry)

        # Info permanenti sempre visibili a destra
        self._status_label = QLabel()
        self.statusBar().addPermanentWidget(self._status_label)
        self._update_status_bar()
        self._update_toolbar_state()
        self._apply_theme(self._current_theme.theme_id)

        # FPS tracking
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps_display)


        # =============================================================
        # INPUT TASTIERA → COMANDI ZMQ
        # =============================================================
        # Carica la mappatura tasti da file (o default se assente)
        self._bindings_file = ( Path(__file__).resolve().parent.parent.parent.parent
            / "control_input" / "bindings.json")
        self._binding_manager = KeyBindingManager()
        self._binding_manager.load_or_defaults(self._bindings_file)

        self._control_publisher = ControlPublisher(ZMQConfig())
        self._control_publisher.start()
        self._keyboard_mgr = KeyboardControlManager(
            self, self._control_publisher,
            binding_manager=self._binding_manager)
        # Collega le azioni momentanee (pause, reset)
        self._keyboard_mgr.momentary_action.connect(self._on_momentary_action)
        self._keyboard_mgr.enable()


        # =============================================================
        # SIMULATORE — PANNELLO CONTROLLI (angolo destro della menu bar)
        # =============================================================
        # Contenitore orizzontale per i controlli del simulatore
        self._sim_toolbar = QWidget(self)
        self._sim_toolbar.setObjectName("sim_toolbar")
        sim_layout = QHBoxLayout(self._sim_toolbar)
        sim_layout.setContentsMargins(4, 2, 8, 2)
        sim_layout.setSpacing(4)

        # Dropdown velivolo
        self._combo_aircraft = QComboBox()
        self._combo_aircraft.addItems(["C172"])
        self._combo_aircraft.setToolTip("Seleziona il velivolo per la simulazione")
        sim_layout.addWidget(self._combo_aircraft)

        # Pulsante Play
        self._btn_sim_play = QPushButton("▶")
        self._btn_sim_play.setToolTip("Avvia simulazione")
        self._btn_sim_play.setFixedWidth(36)
        self._btn_sim_play.clicked.connect(self._on_sim_play)
        sim_layout.addWidget(self._btn_sim_play)

        # Pulsante Stop
        self._btn_sim_stop = QPushButton("■")
        self._btn_sim_stop.setToolTip("Ferma simulazione")
        self._btn_sim_stop.setFixedWidth(36)
        self._btn_sim_stop.setEnabled(False)
        self._btn_sim_stop.clicked.connect(self._on_sim_stop)
        sim_layout.addWidget(self._btn_sim_stop)

        # Label stato simulatore
        self._lbl_sim_status = QLabel("Sim: inattivo")
        sim_layout.addWidget(self._lbl_sim_status)

        # Toggle log simulatore
        self._btn_sim_log = QPushButton("Log")
        self._btn_sim_log.setToolTip("Mostra/nascondi il log del simulatore")
        self._btn_sim_log.setCheckable(True)
        self._btn_sim_log.setFixedWidth(44)
        self._btn_sim_log.clicked.connect(self._toggle_sim_log)
        sim_layout.addWidget(self._btn_sim_log)

        # Posiziona il pannello nell'angolo destro della menu bar
        self.menuBar().setCornerWidget(
            self._sim_toolbar, Qt.Corner.TopRightCorner)

        # Dock log simulatore
        self._sim_log_dock = QDockWidget("Log Simulatore", self)
        self._sim_log_dock.setObjectName("sim_log_dock")
        self._sim_log_text = QTextEdit()
        self._sim_log_text.setReadOnly(True)
        self._sim_log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._sim_log_text.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 10px;")
        self._sim_log_dock.setWidget(self._sim_log_text)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                            self._sim_log_dock)
        # Preferenza persistente: il log deve essere visibile all'avvio?

        show_log_at_startup = self._settings.value(
            "sim_log_visible", False, type=bool)
        self._sim_log_dock.setVisible(show_log_at_startup)
        self._btn_sim_log.setChecked(show_log_at_startup)

        # Abilita/disabilita in base alla disponibilità del simulatore
        sim_available = self._sim_manager.is_simulator_available()
        self._sim_toolbar.setVisible(sim_available)
        self._btn_sim_play.setEnabled(sim_available)   



    # ========================================================================
    # SHOW / CLOSE
    # ========================================================================
    def showEvent(self, e):
        super().showEvent(e)
        self._view.setFocus()

    def closeEvent(self, e):
        """Ferma TUTTO: simulatore + input tastiera + publisher + adapter."""
        # --- Cleanup simulatore (bloccante, solo in shutdown) ---
        if hasattr(self, '_sim_manager') and self._sim_manager.is_running:
            reply = QMessageBox.question(
                self, "Chiudi GCS",
                "Il simulatore è ancora in esecuzione. Fermarlo e uscire?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self._sim_manager.stop()
            self._sim_manager.wait_for_stop(5000)

        # --- Cleanup input tastiera e publisher comandi ---
        if hasattr(self, '_keyboard_mgr'):
            self._keyboard_mgr.disable()
        if hasattr(self, '_control_publisher'):
            self._control_publisher.stop()
        # --- Cleanup telemetria ---
        if self._telemetry_adapter:
            self._telemetry_adapter.stop()
        if hasattr(self, '_zmq_adapter') and self._zmq_adapter:
            self._zmq_adapter.stop()
        super().closeEvent(e)


    # =============================================================
    # EVENTI TASTIERA per input di volo
    # =============================================================
    def keyPressEvent(self, event):
        """Cattura la pressione dei tasti per i comandi di volo."""
        if hasattr(self, '_keyboard_mgr'):
            self._keyboard_mgr.handle_key_press(event.key())
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Cattura il rilascio dei tasti per i comandi di volo."""
        if hasattr(self, '_keyboard_mgr'):
            self._keyboard_mgr.handle_key_release(event.key())
        super().keyReleaseEvent(event)



    # ========================================================================
    # TELEMETRIA — SISTEMA UNIFICATO
    # ========================================================================
    def _set_telemetry_adapter(self, adapter):
        if self._telemetry_adapter:
            self._telemetry_adapter.stop()
            try:
                self._telemetry_adapter.telemetry_updated.disconnect(
                    self._on_telemetry)
            except RuntimeError:
                pass
        self._telemetry_adapter = adapter
        adapter.telemetry_updated.connect(self._on_telemetry)
        adapter.start()

    def _on_telemetry(self, data):
        self._view.tick_fps()
        visible_rect = self._view.mapToScene(
            self._view.viewport().rect()
        ).boundingRect()
        margin = 100
        visible_rect = visible_rect.adjusted(-margin, -margin, margin, margin)
        for it in self._all_instruments():
            # Salta oggetti C++ già eliminati (deleteLater in sospeso)
            if not shiboken6.isValid(it):
                continue
            if it.sceneBoundingRect().intersects(visible_rect):
                it.update_data(data)

    def get_external_adapter(self):
        adapter = ExternalTelemetryAdapter(self)
        self._set_telemetry_adapter(adapter)
        return adapter

    def _switch_telemetry(self, mode):
        """Cambia la sorgente di telemetria (mock/external/zmq/test/pause)."""
        # Se usciamo da ZMQ, fermiamo il subscriber
        if mode != "zmq" and hasattr(self, '_zmq_adapter'):
            self._zmq_adapter.stop()

        if mode == "mock":
            adapter = MockTelemetryAdapter(self)
            adapter.set_interval(int(1000 / self._target_fps))
            self._set_telemetry_adapter(adapter)

        elif mode == "external":
            self._set_telemetry_adapter(ExternalTelemetryAdapter(self))

        elif mode == "zmq":
            # Ferma adapter corrente
            if self._telemetry_adapter:
                self._telemetry_adapter.stop()
                try:
                    self._telemetry_adapter.telemetry_updated.disconnect(
                        self._on_telemetry)
                except RuntimeError:
                    pass
                self._telemetry_adapter = None
            # Avvia subscriber ZMQ
            self._zmq_adapter.start()
            self.statusBar().showMessage(
                "Telemetria: ZeroMQ (Simulatore)", 3000)

        elif mode.startswith("test-"):
            # Traiettoria di test coerente (factory riusabile in ipc_bus)
            traj_key = mode.removeprefix("test-")
            trajectory = create_trajectory(traj_key)
            adapter = TrajectoryTelemetryAdapter(trajectory, self)
            adapter.set_interval(int(1000 / self._target_fps))
            self._set_telemetry_adapter(adapter)
            self.statusBar().showMessage(
                f"Telemetria: Test — {traj_key}", 3000)

        elif mode == "pause":
            if self._telemetry_adapter:
                self._telemetry_adapter.stop()

    # ========================================================================
    # MENU (unico)
    # ========================================================================
    def _create_menu(self):
        mb = self.menuBar()
        # =====================================================================
        # FILE
        # =====================================================================
        fm = mb.addMenu("&File")
        act_save = fm.addAction("Salva layout...")
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._save_layout)
        act_load = fm.addAction("Carica layout...")
        act_load.setShortcut("Ctrl+O")
        act_load.triggered.connect(self._load_layout)
        fm.addSeparator()
        # --- Sottomenu Preset ---
        self._preset_menu = fm.addMenu("Preset")
        self._preset_menu.aboutToShow.connect(self._rebuild_preset_menu)
        fm.addSeparator()
        fm.addAction("Pulisci layout").triggered.connect(self._clear_all)
        fm.addSeparator()
        fm.addAction("Esci").triggered.connect(self.close)
        # =====================================================================
        # VISTA
        # =====================================================================
        vm = mb.addMenu("&Vista")
        act_zoom_in = vm.addAction("Zoom In")
        act_zoom_in.setShortcut("Ctrl+=")
        act_zoom_in.triggered.connect(self._view.zoom_in)
        act_zoom_out = vm.addAction("Zoom Out")
        act_zoom_out.setShortcut("Ctrl+-")
        act_zoom_out.triggered.connect(self._view.zoom_out)
        act_zoom_reset = vm.addAction("Reset Zoom")
        act_zoom_reset.setShortcut("Ctrl+0")
        act_zoom_reset.triggered.connect(self._view.zoom_reset)
        vm.addSeparator()
        act_fit = vm.addAction("Adatta tutto")
        act_fit.setShortcut("Ctrl+F")
        act_fit.triggered.connect(self._view.fit_all)
        vm.addSeparator()
        act_fullscreen = vm.addAction("Fullscreen")
        act_fullscreen.setShortcut("F11")
        act_fullscreen.triggered.connect(self._toggle_fullscreen)
        vm.addSeparator()
        self._act_preview = vm.addAction("Cockpit Preview")
        self._act_preview.setShortcut("F5")
        self._act_preview.setCheckable(True)
        self._act_preview.triggered.connect(self._toggle_preview)
        vm.addSeparator()
        # OpenGL toggle
        self._act_opengl = vm.addAction("OpenGL")
        self._act_opengl.setCheckable(True)
        self._act_opengl.setChecked(self._opengl_enabled)
        self._act_opengl.setEnabled(OPENGL_AVAILABLE)
        self._act_opengl.triggered.connect(self._toggle_opengl)
        # =====================================================================
        # TEMA
        # =====================================================================
        theme_menu = mb.addMenu("&Tema")
        self._theme_actions: dict[str, QAction] = {}
        for th in self._theme_registry.themes():
            act = theme_menu.addAction(th.display_name)
            act.setCheckable(True)
            act.setChecked(th.theme_id == self._current_theme.theme_id)
            act.triggered.connect(
                lambda checked=False, tid=th.theme_id: self._apply_theme(tid)
            )
            self._theme_actions[th.theme_id] = act
        # =====================================================================
        # TELEMETRIA (unico, con ZeroMQ e Test)
        # =====================================================================
        tm = mb.addMenu("&Telemetria")
        tm.addAction("Mock (sinusoidale)").triggered.connect(
            lambda: self._switch_telemetry("mock"))
        tm.addAction("Esterna (backend)").triggered.connect(
            lambda: self._switch_telemetry("external"))
        tm.addAction("ZeroMQ (Simulatore)").triggered.connect(
            lambda: self._switch_telemetry("zmq"))

        # --- Sottomenu Test: traiettorie coerenti ---
        test_menu = tm.addMenu("Test")
        test_menu.addAction("Rettilinea").triggered.connect(
            lambda: self._switch_telemetry("test-straight"))
        test_menu.addAction("Orbita").triggered.connect(
            lambda: self._switch_telemetry("test-orbit"))
        test_menu.addAction("Salita / Discesa").triggered.connect(
            lambda: self._switch_telemetry("test-climb"))

        tm.addSeparator()
        tm.addAction("Pausa").triggered.connect(
            lambda: self._switch_telemetry("pause"))
        # =====================================================================
        # PRESTAZIONI
        # =====================================================================
        pm = mb.addMenu("&Prestazioni")
        # Sottomenu FPS Target
        fps_menu = pm.addMenu("FPS Target")
        fps_values = [60, 40, 30, 20, 15, 10]
        self._fps_actions = {}
        for fps in fps_values:
            act = fps_menu.addAction(f"{fps} FPS")
            act.setCheckable(True)
            act.setChecked(fps == self._target_fps)
            act.triggered.connect(
                lambda checked=False, f=fps: self._set_target_fps(f)
            )
            self._fps_actions[fps] = act
        pm.addSeparator()
        pm.addAction("Stress test: +10 strumenti").triggered.connect(
            lambda: self._stress_test(10))
        pm.addAction("Stress test: +50 strumenti").triggered.connect(
            lambda: self._stress_test(50))
        pm.addAction("Stress test: +100 strumenti").triggered.connect(
            lambda: self._stress_test(100))
        pm.addSeparator()
        pm.addAction("Pulisci tutto").triggered.connect(self._clear_stress_test)

        # =====================================================================
        # CONTROLLI
        # =====================================================================
        cm = mb.addMenu("&Controlli")
        cm.addAction("Configurazione tasti...").triggered.connect(
            self._open_key_binding_dialog)
        cm.addSeparator()
        cm.addAction("Ripristina default").triggered.connect(
            self._restore_default_bindings)
        # =====================================================================
        # SIMULATOR
        # =====================================================================
        sm = mb.addMenu("&Simulator")

        # Checkmark: mostra/nascondi pannello simulatore
        self._action_show_sim = sm.addAction("Pannello Simulatore")
        self._action_show_sim.setCheckable(True)
        self._action_show_sim.setChecked(
            self._sim_manager.is_simulator_available())
        self._action_show_sim.toggled.connect(self._toggle_sim_panel)

        # Checkmark log simulatore
        self._action_show_log = sm.addAction("Log Simulatore")
        self._action_show_log.setCheckable(True)
        self._action_show_log.setChecked(
            self._settings.value("sim_log_visible", False, type=bool))
        self._action_show_log.toggled.connect(self._toggle_sim_log)

        sm.addSeparator()

        sm.addAction("Avvia Simulazione...").triggered.connect(
            self._on_sim_play)
        sm.addAction("Ferma Simulazione").triggered.connect(
            self._on_sim_stop)

    # ========================================================================
    # TEMA
    # ========================================================================
    def _apply_theme(self, theme_id: str):
        theme = self._theme_registry.get(theme_id)
        if theme is None:
            return
        self._current_theme = theme
        # Applica il tema a tutti gli strumenti
        for item in self._all_instruments():
            item.set_theme(theme)
        # Applica il tema alla scena (sfondo + griglia)
        self._scene.setBackgroundBrush(QBrush(theme.scene_background))
        self._scene.set_grid_color(theme.grid_color)
        # Aggiorna checkmark nel menu
        for tid, act in self._theme_actions.items():
            act.setChecked(tid == theme_id)
        # Forza ridisegno
        self._scene.invalidate()
        self._view.viewport().update()
        self.statusBar().showMessage(f"Tema: {theme.display_name}", 3000)

    # ========================================================================
    # PRESTAZIONI
    # ========================================================================
    def _update_fps_display(self):
        self._update_status_bar()

    def _toggle_opengl(self):
        """Attiva/disattiva viewport OpenGL (stato reale = tipo del viewport)."""
        current = self._view.is_opengl()
        new_state = not current
        if new_state and not OPENGL_AVAILABLE:
            QMessageBox.warning(
                self, "OpenGL non disponibile",
                "PySide6.QtOpenGLWidgets non è installato.\n"
                "Installa con: pip install PySide6"
            )
            if hasattr(self, '_act_opengl'):
                self._act_opengl.blockSignals(True)
                self._act_opengl.setChecked(current)
                self._act_opengl.blockSignals(False)
            return
        self._view.set_opengl(new_state)
        self._opengl_enabled = self._view.is_opengl()   # riverifica dopo il cambio
        # Invalida la cache di rendering di ogni strumento
        for item in self._all_instruments():
            if hasattr(item, "_bg_cache"):
                item._bg_cache = None
            item.update()
        self._scene.invalidate()
        self._view.viewport().update()
        state = "ON" if self._opengl_enabled else "OFF"
        self.statusBar().showMessage(f"OpenGL: {state}", 3000)
        if hasattr(self, '_act_opengl'):
            self._act_opengl.blockSignals(True)
            self._act_opengl.setChecked(self._opengl_enabled)
            self._act_opengl.blockSignals(False)

    def _set_target_fps(self, fps: int):
        """Imposta la frequenza target per la telemetria mock."""
        self._target_fps = fps
        interval_ms = max(1, int(1000 / fps))
        # Applica all'adapter attuale se è Mock
        if isinstance(self._telemetry_adapter, MockTelemetryAdapter):
            self._telemetry_adapter.set_interval(interval_ms)
        # Aggiorna i checkmark nel menu
        for f, act in self._fps_actions.items():
            act.setChecked(f == fps)
        self.statusBar().showMessage(f"FPS Target: {fps}", 3000)

    def _stress_test(self, count: int = 50):
        """Genera N strumenti casuali per test prestazionali."""
        import random
        prototypes = [
            self._registry.get("flight-airspeed"),
            self._registry.get("flight-altimeter"),
            self._registry.get("flight-attitude"),
            self._registry.get("engine-rpm"),
            self._registry.get("engine-oil-temp"),
            self._registry.get("nav-heading"),
        ]
        prototypes = [p for p in prototypes if p is not None]
        if not prototypes:
            return
        scene_rect = self._scene.sceneRect()
        for i in range(count):
            proto = random.choice(prototypes)
            item = InstrumentFactory.create_item(proto)
            item.set_snap_enabled(False)
            x = random.uniform(scene_rect.left() + 20,
                               scene_rect.right() - proto.width - 20)
            y = random.uniform(scene_rect.top() + 20,
                               scene_rect.bottom() - proto.height - 20)
            item.setPos(x, y)
            item.setZValue(random.uniform(0, 10))
            self._scene.addItem(item)
            if self._current_theme:
                item.set_theme(self._current_theme)
        self._invalidate_instrument_cache()
        self._scene.clearSelection()
        self._update_status_bar()
        self.statusBar().showMessage(
            f"Stress test: +{count} strumenti (totale: {len(self._all_instruments())})",
            4000
        )

    def _clear_stress_test(self):
        """Rimuove tutti gli strumenti (utile dopo stress test)."""
        self._clear_all()

    def _update_toolbar_state(self):
        has = len(self._selected_instruments()) > 0
        for a in [
            self._act_duplicate,
            self._act_delete,
            self._act_front,
            self._act_back,
            self._act_rot_cw,
            self._act_rot_ccw,
            self._act_scale_up,
            self._act_scale_down,
            self._act_reset,
        ]:
            a.setEnabled(has)

    # ========================================================================
    # SHORTCUTS
    # ========================================================================
    def _create_shortcuts(self):
        # Elimina selezionati
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self).activated.connect(
            self.delete_selected
        )
        # Duplica
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(
            self._duplicate
        )
        # Seleziona tutto
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(
            self._select_all
        )
        # Toggle snap/griglia
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(
            lambda: self.set_snap(not self._snap_enabled)
        )
        # Toggle Cockpit Preview
        # IMPORTANTE: Ctrl+=, Ctrl+-, Ctrl+0, Ctrl+F, F11
        # NON vanno qui perché sono già nel menu Vista.

    def _select_all(self):
        for it in self._all_instruments():
            it.setSelected(True)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ========================================================================
    # CURSOR TRACKING
    # ========================================================================
    def _on_cursor_moved(self, pos: QPointF):
        self._cursor_pos = pos
        self._update_status_bar()

    # ========================================================================
    # COCKPIT PREVIEW
    # ========================================================================
    def _toggle_preview(self):
        """Alterna tra modalità editing e modalità preview."""
        if self._preview_mode:
            self._exit_preview()
        else:
            self._enter_preview()

    def _enter_preview(self):
        self._preview_mode = True
        self._scene.clearSelection()
        self._scene.set_snap_enabled(False)
        self._hangar.hide()
        self._edit_toolbar.hide()
        for item in self._all_instruments():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        if hasattr(self, "_act_preview"):
            self._act_preview.setChecked(True)
        self._update_status_bar()
        self.statusBar().showMessage("Cockpit Preview — F5 per uscire", 4000)

    def _exit_preview(self):
        self._preview_mode = False
        if self._snap_enabled:
            self._scene.set_snap_enabled(True)
        self._hangar.show()
        self._edit_toolbar.show()
        for item in self._all_instruments():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        if hasattr(self, "_act_preview"):
            self._act_preview.setChecked(False)
        self._update_status_bar()
        self.statusBar().showMessage("Modalità editing", 3000)

    # ========================================================================
    # TOOLBAR
    # ========================================================================
    def _create_toolbar(self):
        tb = QToolBar("Editing", self); tb.setObjectName("EditTB"); tb.setMovable(False)
        self._edit_toolbar = tb
        self.addToolBar(tb)
        self._act_duplicate = QAction("Duplica", self); self._act_duplicate.triggered.connect(self._duplicate); tb.addAction(self._act_duplicate)
        self._act_delete = QAction("Elimina", self); self._act_delete.triggered.connect(self.delete_selected); tb.addAction(self._act_delete)
        tb.addSeparator()
        self._act_front = QAction("Davanti", self); self._act_front.triggered.connect(self._z_front); tb.addAction(self._act_front)
        self._act_back = QAction("Dietro", self); self._act_back.triggered.connect(self._z_back); tb.addAction(self._act_back)
        tb.addSeparator()
        self._act_rot_cw = QAction("Rot+15°", self); self._act_rot_cw.triggered.connect(lambda: self._rotate(15)); tb.addAction(self._act_rot_cw)
        self._act_rot_ccw = QAction("Rot-15°", self); self._act_rot_ccw.triggered.connect(lambda: self._rotate(-15)); tb.addAction(self._act_rot_ccw)
        tb.addSeparator()
        self._act_scale_up = QAction("Scala+", self); self._act_scale_up.triggered.connect(lambda: self._scale(1.1)); tb.addAction(self._act_scale_up)
        self._act_scale_down = QAction("Scala-", self); self._act_scale_down.triggered.connect(lambda: self._scale(0.9)); tb.addAction(self._act_scale_down)
        tb.addSeparator()
        self._act_reset = QAction("Reset", self); self._act_reset.triggered.connect(self._reset_transform); tb.addAction(self._act_reset)
        tb.addSeparator()
        self._act_snap = QAction("Snap", self); self._act_snap.setCheckable(True); self._act_snap.setChecked(self._snap_enabled); self._act_snap.toggled.connect(self.set_snap); tb.addAction(self._act_snap)
        self._update_toolbar_state()

    def _update_status_bar(self):
        instruments = self._all_instruments()
        selected = self._selected_instruments()
        snap = "ON" if self._snap_enabled else "OFF"
        zoom = self._view.transform().m11()
        try:
            fps = self._view.get_fps()
        except AttributeError:
            fps = 0.0
        try:
            gl_state = "GL" if self._opengl_enabled else "SW"
        except AttributeError:
            gl_state = "SW"
        parts = [
            f"Strum: {len(instruments)}",
            f"FPS: {fps:.0f}",
            f"Snap: {snap}",
            f"Zoom: {zoom:.0%}",
            gl_state,
        ]
        if hasattr(self, '_cursor_pos'):
            parts.append(f"XY: {self._cursor_pos.x():.0f},{self._cursor_pos.y():.0f}")
        if len(selected) == 1:
            parts.append(f"Sel: {selected[0].prototype.display_name}")
        elif len(selected) > 1:
            parts.append(f"Sel: {len(selected)}")
        # Aggiorna il label permanente (destra)
        self._status_label.setText(" | ".join(parts))

    # ========================================================================
    # SELEZIONE / STATUS
    # ========================================================================
    def _on_selection_changed(self):
        self._update_status_bar(); self._update_toolbar_state()

    def _all_instruments(self):
        if self._instrument_cache_dirty:
            self._instrument_cache = [
                i for i in self._scene.items()
                if isinstance(i, BaseInstrument) and shiboken6.isValid(i)
            ]
            self._instrument_cache_dirty = False
        return self._instrument_cache

    def _invalidate_instrument_cache(self):
        """Marca la cache come dirty (chiamare dopo aggiunte/rimozioni)."""
        self._instrument_cache_dirty = True

    def _selected_instruments(self):
        return [i for i in self._scene.selectedItems() if isinstance(i, BaseInstrument)]

    # ========================================================================
    # AGGIUNTA
    # ========================================================================
    def add_instrument_by_type(self, tid):
        if self._preview_mode:
            return
        proto = self._registry.get(tid)
        if not proto: return
        item = InstrumentFactory.create_item(proto)
        center = self._view.mapToScene(self._view.viewport().rect().center())
        off = self._spawn_index * 32.0
        self._insert(item, QPointF(center.x()-proto.width/2+off, center.y()-proto.height/2+off))
        self._spawn_index = (self._spawn_index+1)%6

    def add_instrument_at(self, tid, scene_pos):
        if self._preview_mode:
            return
        proto = self._registry.get(tid)
        if not proto: return
        item = InstrumentFactory.create_item(proto)
        self._insert(item, QPointF(scene_pos.x()-proto.width/2, scene_pos.y()-proto.height/2))

    def _insert(self, item, desired):
        item.set_snap_enabled(self._snap_enabled)
        item.set_grid_size(self._grid_size)
        item.setPos(self._clamp(desired, item.prototype, item.scale()))
        self._scene.addItem(item)
        # Porta davanti l'ultimo strumento aggiunto
        max_z = max((i.zValue() for i in self._scene.items()
                     if isinstance(i, BaseInstrument)), default=0)
        item.setZValue(max_z + 1)
        self._invalidate_instrument_cache()
        if self._preview_mode:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        if self._current_theme:
            item.set_theme(self._current_theme)
        self._scene.clearSelection()
        item.setSelected(True)
        self._view.setFocus()
        self._update_status_bar()

    def _clamp(self, pos, proto, scale=1.0):
        sr = self._scene.sceneRect()
        w, h = proto.width*max(0.1,scale), proto.height*max(0.1,scale)
        x = max(sr.left()+8, min(pos.x(), sr.right()-w-8))
        y = max(sr.top()+8, min(pos.y(), sr.bottom()-h-8))
        return QPointF(x, y)

    # ========================================================================
    # CONTEXT MENU
    # ========================================================================
    def _show_context_menu(self, vp):
        if self._preview_mode:
            return
        sp = self._view.mapToScene(vp)
        item = self._scene.itemAt(sp, QTransform())
        if item is not None and hasattr(item, 'show_custom_context_menu'):
            global_pos = self._view.viewport().mapToGlobal(vp)
            if item.show_custom_context_menu(global_pos):
                return
        menu = QMenu(self)
        if isinstance(item, BaseInstrument):
            if not item.isSelected():
                self._scene.clearSelection(); item.setSelected(True)
            menu.addAction("Duplica", lambda: self._duplicate())
            menu.addSeparator()
            menu.addAction("Porta davanti", lambda: self._z_front())
            menu.addAction("Porta dietro", lambda: self._z_back())
            menu.addSeparator()
            menu.addAction("Ruota +15°", lambda: self._rotate(15))
            menu.addAction("Ruota -15°", lambda: self._rotate(-15))
            menu.addSeparator()
            menu.addAction("Scala +", lambda: self._scale(1.1))
            menu.addAction("Scala -", lambda: self._scale(0.9))
            if hasattr(item, 'get_map_scale_menu'):
                scale_menu = item.get_map_scale_menu()
                if scale_menu is not None:
                    menu.addSeparator()
                    menu.addMenu(scale_menu)
            menu.addSeparator()
            menu.addAction("Reset", lambda: self._reset_transform())
            menu.addSeparator()
            menu.addAction("Elimina", lambda: self.delete_selected())
        else:
            sa = menu.addAction("Snap"); sa.setCheckable(True); sa.setChecked(self._snap_enabled); sa.triggered.connect(self.set_snap)
            menu.addSeparator()
            menu.addAction("Seleziona tutto", lambda: self._select_all())
            menu.addAction("Deseleziona", lambda: self._scene.clearSelection())
            if self._selected_instruments():
                menu.addAction("Elimina selezionati", lambda: self.delete_selected())
        menu.exec(self._view.viewport().mapToGlobal(vp))

    # ========================================================================
    # EDITING
    # ========================================================================
    def set_snap(self, e):
        self._snap_enabled = bool(e)
        self._scene.set_snap_enabled(self._snap_enabled)
        for it in self._all_instruments(): it.set_snap_enabled(self._snap_enabled); it.set_grid_size(self._grid_size)
        if hasattr(self, '_act_snap'):
            self._act_snap.blockSignals(True); self._act_snap.setChecked(self._snap_enabled); self._act_snap.blockSignals(False)
        self._update_status_bar()

    def _duplicate(self):
        if self._preview_mode:
            return
        sel = self._selected_instruments()
        if not sel: return
        new_items = []
        for it in sel:
            ni = InstrumentFactory.create_item(it.prototype)
            ni.setRotation(it.rotation()); ni.setScale(it.scale()); ni.setZValue(it.zValue())
            ni.set_snap_enabled(self._snap_enabled); ni.set_grid_size(self._grid_size)
            ni.setPos(self._clamp(QPointF(it.pos().x()+24, it.pos().y()+24), ni.prototype, ni.scale()))
            self._scene.addItem(ni)
            if self._current_theme:
                ni.set_theme(self._current_theme)
            new_items.append(ni)
        self._invalidate_instrument_cache()
        self._scene.clearSelection()
        for ni in new_items: ni.setSelected(True)
        self._update_status_bar()

    def _z_front(self):
        sel = self._selected_instruments()
        if not sel: return
        mz = max((i.zValue() for i in self._all_instruments()), default=0)
        for idx, it in enumerate(sel): it.setZValue(mz+1+idx)
        self._scene.update()

    def _z_back(self):
        sel = self._selected_instruments()
        if not sel: return
        mz = min((i.zValue() for i in self._all_instruments()), default=0)
        for idx, it in enumerate(sel): it.setZValue(mz-1-idx)
        self._scene.update()

    def _rotate(self, d):
        for it in self._selected_instruments(): it.setRotation((it.rotation()+d)%360)
        self._scene.update(); self._update_status_bar()

    def _scale(self, f):
        for it in self._selected_instruments(): it.setScale(max(0.3, min(it.scale()*f, 3.0)))
        self._scene.update(); self._update_status_bar()

    def _reset_transform(self):
        for it in self._selected_instruments(): it.setRotation(0); it.setScale(1.0)
        self._scene.update(); self._update_status_bar()

    def delete_selected(self):
        if self._preview_mode:
            return
        for it in self._selected_instruments():
            it.setSelected(False)
            self._scene.removeItem(it)
            it.deleteLater()
        self._invalidate_instrument_cache()
        self._update_status_bar()

    def _clear_all(self):
        for it in self._all_instruments():
            self._scene.removeItem(it)
            it.deleteLater()
        self._scene.clearSelection()
        self._spawn_index = 0
        self._invalidate_instrument_cache()
        self._update_status_bar()

    # ========================================================================
    # PERSISTENZA
    # ========================================================================
    def _serialize(self):
        instruments = []
        for it in self._all_instruments():
            entry = {
                "instance_id": it.instance_id,
                "type_id": it.prototype.type_id,
                "x": it.pos().x(),
                "y": it.pos().y(),
                "rotation": it.rotation(),
                "scale": it.scale(),
                "z": it.zValue(),
            }
            if hasattr(it, "save_state"):
                state = it.save_state()
                if state:
                    entry["state"] = state
            instruments.append(entry)
        return {
            "schema_version": LAYOUT_SCHEMA_VERSION,
            "snap_enabled": self._snap_enabled,
            "grid_size": self._grid_size,
            "theme_id": self._current_theme.theme_id if self._current_theme else "base",
            "instruments": instruments,
        }

    def _deserialize(self, data):
        try:
            version = int(data.get("schema_version", 0))
        except (ValueError, TypeError):
            return False
        if version > LAYOUT_SCHEMA_VERSION: return False
        self._clear_all(); self._snap_enabled = False
        theme_id = data.get("theme_id")
        if theme_id:
            theme = self._theme_registry.get(theme_id)
            if theme:
                self._current_theme = theme
        # Fase 1: crea e aggiungi tutti gli strumenti SENZA zValue
        items_list = []
        for inst in data.get("instruments", []):
            proto = self._registry.get(inst.get("type_id"))
            if not proto: continue
            item = InstrumentFactory.create_item(proto)
            item.set_instance_id(inst.get("instance_id", str(uuid.uuid4())))
            item.set_snap_enabled(False)
            item.setPos(inst.get("x",0), inst.get("y",0))
            item.setRotation(inst.get("rotation",0))
            item.setScale(inst.get("scale",1.0))
            item.set_grid_size(self._grid_size)
            state = inst.get("state")
            if state and hasattr(item, "restore_state"):
                item.restore_state(state)
            self._scene.addItem(item)
            if self._current_theme:
                item.set_theme(self._current_theme)
            # Salva item e zValue per la fase 2
            items_list.append((item, inst.get("z", 0)))
        # Fase 2: imposta TUTTI i zValue DOPO aver aggiunto tutti gli item
        # Questo garantisce che Qt non modifichi i valori durante addItem
        for item, z_val in items_list:
            item.setZValue(z_val)
        self._invalidate_instrument_cache()
        self._snap_enabled = data.get("snap_enabled", False)
        self._grid_size = data.get("grid_size", DEFAULT_GRID_SIZE)
        self._scene.set_grid_size(self._grid_size)
        self.set_snap(self._snap_enabled)
        if theme_id:
            self._apply_theme(theme_id)
        self._update_status_bar()
        return True

    def _save_layout(self):
        fp, _ = QFileDialog.getSaveFileName(self, "Salva layout", "", "JSON (*.json)")
        if not fp: return
        try:
            with open(fp, "w", encoding="utf-8") as f: json.dump(self._serialize(), f, indent=2, ensure_ascii=False)
            self.statusBar().showMessage(f"Salvato: {fp}", 4000)
        except Exception as e: QMessageBox.critical(self, "Errore", str(e))

    def _load_layout(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Carica layout", "", "JSON (*.json)")
        if not fp: return
        try:
            with open(fp, "r", encoding="utf-8") as f: data = json.load(f)
        except Exception as e: QMessageBox.critical(self, "Errore", str(e)); return
        if self._deserialize(data): self.statusBar().showMessage(f"Caricato: {fp}", 4000)
        else: QMessageBox.warning(self, "Versione", "Schema non supportato.")

    # ========================================================================
    # PRESET DI PANNELLO
    # ========================================================================
    def _rebuild_preset_menu(self):
        """Ricostruisce il sottomenu Preset con la lista attuale."""
        self._preset_menu.clear()
        presets = self._preset_manager.list_presets()
        if presets:
            for name in presets:
                act = self._preset_menu.addAction(name)
                act.triggered.connect(
                    lambda checked=False, n=name: self._load_preset(n)
                )
            self._preset_menu.addSeparator()
        act_save = self._preset_menu.addAction("Salva come preset...")
        act_save.triggered.connect(self._save_as_preset)
        act_manage = self._preset_menu.addAction("Gestisci preset...")
        act_manage.triggered.connect(self._manage_presets)

    def _save_as_preset(self):
        """Chiede un nome e salva il layout corrente come preset."""
        name, ok = QInputDialog.getText(self, "Salva preset", "Nome del preset:")
        if not ok or not name.strip():
            return
        name = name.strip()
        # Conferma sovrascrittura
        if self._preset_manager.preset_exists(name):
            reply = QMessageBox.question(
                self, "Preset esistente",
                f"Il preset '{name}' esiste già. Sovrascrivere?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if self._preset_manager.save_preset(name, self._serialize()):
            self.statusBar().showMessage(f"Preset salvato: {name}", 4000)
        else:
            QMessageBox.warning(self, "Errore", "Impossibile salvare il preset.")

    def _load_preset(self, name: str):
        """Carica un preset per nome."""
        data = self._preset_manager.load_preset(name)
        if data is None:
            QMessageBox.warning(self, "Errore",
                                f"Impossibile caricare il preset '{name}'.")
            return
        if self._deserialize(data):
            self.statusBar().showMessage(f"Preset caricato: {name}", 4000)
        else:
            QMessageBox.warning(self, "Versione",
                                "Schema del preset non supportato.")

    def _manage_presets(self):
        """Apre il dialog di gestione preset."""
        dlg = PresetDialog(self._preset_manager, self)
        dlg.exec()

    # ========================================================================
    # CONTROLLI / KEY BINDING
    # ========================================================================
    def _open_key_binding_dialog(self):
        """Apre il dialog di configurazione dei tasti di volo."""
        dlg = KeyBindingDialog(self._binding_manager, self)
        if dlg.exec() == KeyBindingDialog.DialogCode.Accepted:
            # L'utente ha confermato: salva i binding su file
            if self._binding_manager.save(self._bindings_file):
                self.statusBar().showMessage("Mappatura tasti salvata.", 3000)
            else:
                QMessageBox.warning(
                    self, "Errore",
                    "Impossibile salvare la mappatura dei tasti.")
        else:
            self.statusBar().showMessage("Mappatura tasti annullata.", 3000)

    def _restore_default_bindings(self):
        """Ripristina la mappatura di default e salva su file."""
        reply = QMessageBox.question(
            self, "Ripristina default",
            "Vuoi ripristinare la mappatura di default dei tasti?\n"
            "La configurazione corrente verrà sovrascritta.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._binding_manager.load_defaults()
        self._binding_manager.save(self._bindings_file)
        self.statusBar().showMessage(
            "Mappatura tasti ripristinata ai default.", 3000)

    def _on_momentary_action(self, action: str):
        """
        Gestisce le azioni momentanee da tastiera.
        - pause: sospende/riprende la pubblicazione dei comandi.
                In pausa il simulatore riceve timeout e usa i default.
        - reset: azzera il throttle e rilascia tutti i tasti.
        """
        if action == "pause":
            if self._keyboard_mgr.enabled:
                self._keyboard_mgr.disable()
                self.statusBar().showMessage(
                    "COMANDI IN PAUSA — il simulatore usa i default", 3000)
            else:
                self._keyboard_mgr.enable()
                self.statusBar().showMessage("COMANDI ATTIVI", 2000)
        elif action == "reset":
            self._keyboard_mgr.clear()
            self._keyboard_mgr.keyboard.throttle = 0.0
            self.statusBar().showMessage(
                "Comandi resettati (throttle = 0)", 2000)
            
        # ========================================================================
        # SIMULATORE — GESTIONE PROCESSO
        # ========================================================================
    def _toggle_sim_panel(self, checked: bool):
        """Mostra/nasconde la toolbar e il dock del simulatore."""
        self._sim_toolbar.setVisible(checked)
        if not checked:
            self._sim_log_dock.hide()

    def _toggle_sim_log(self, checked: bool):
        """Mostra/nasconde il dock del log simulatore e salva la preferenza."""
        self._sim_log_dock.setVisible(checked)
        self._settings.setValue("sim_log_visible", checked)
        # Sincronizza i due controlli (pulsante e voce di menu)
        if hasattr(self, '_btn_sim_log'):
            self._btn_sim_log.setChecked(checked)
        if hasattr(self, '_action_show_log'):
            self._action_show_log.setChecked(checked)

    def _on_sim_play(self):
        """Apre il dialog di configurazione e avvia la simulazione."""
        if self._sim_manager.is_running:
            QMessageBox.information(
                self, "Simulatore",
                "La simulazione è già in esecuzione.")
            return

        config = SimLaunchConfig()
        config.aircraft = self._combo_aircraft.currentText()

        dlg = SimLaunchDialog(config, self)
        if dlg.exec() == SimLaunchDialog.DialogCode.Accepted:
            self._sim_log_text.clear()
            self._sim_log_dock.show()
            ok = self._sim_manager.launch(config)
            if ok:
                self.statusBar().showMessage(
                    "Avvio simulazione in corso...", 3000)
            else:
                self.statusBar().showMessage(
                    "Errore nell'avvio della simulazione.", 5000)

    def _on_sim_stop(self):
        """Ferma la simulazione."""
        if not self._sim_manager.is_running:
            return
        self._sim_manager.stop()
        self.statusBar().showMessage("Arresto simulazione...", 3000)

    def _on_sim_started(self):
        """Il processo simulatore è avviato."""
        self._btn_sim_play.setEnabled(False)
        self._btn_sim_stop.setEnabled(True)
        self._lbl_sim_status.setText(" Simulatore: ATTIVO")
        self._lbl_sim_status.setStyleSheet("color: green; font-weight: bold;")
        self.statusBar().showMessage("Simulatore avviato.", 3000)

    def _on_sim_stopped(self, exit_code: int):
        """Il processo simulatore è terminato."""
        self._btn_sim_play.setEnabled(True)
        self._btn_sim_stop.setEnabled(False)
        self._lbl_sim_status.setText(
            f" Simulatore: fermo (exit {exit_code})")
        self._lbl_sim_status.setStyleSheet("color: #a00;")
        self.statusBar().showMessage(
            f"Simulatore terminato (codice {exit_code}).", 5000)

    def _on_sim_error(self, msg: str):
        """Errore dal SimManager."""
        self._lbl_sim_status.setText(" Simulatore: ERRORE")
        self._lbl_sim_status.setStyleSheet("color: red; font-weight: bold;")
        self.statusBar().showMessage(f"Errore simulatore: {msg}", 8000)

    def _on_sim_output(self, line: str):
        """Una riga di output dal simulatore."""
        self._sim_log_text.append(line)
        # Autoscroll: vai in fondo
        scrollbar = self._sim_log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())