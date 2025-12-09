"""
Interfaz gráfica moderna con PyQt para Scrappy (Moodle UCC)
"""
from pathlib import Path
from typing import Optional, List
import json

import keyring
from PyQt6 import QtCore, QtGui, QtWidgets

from scraper.navigator import MoodleScraper
from scraper.models import Materia
from utils.config import Config


class MateriaDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate que fuerza un tamaño de fuente válido para evitar warnings de Qt."""

    def initStyleOption(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        super().initStyleOption(option, index)
        font = option.font
        if font.pointSize() <= 0 and font.pixelSize() <= 0:
            font.setPointSize(11)
            option.font = font


class ScraperWorker(QtCore.QThread):
    """Ejecuta el scraper en un hilo separado para no bloquear la UI."""

    finished = QtCore.pyqtSignal(bool, str)
    progress = QtCore.pyqtSignal(str)

    def __init__(
        self,
        username: str,
        password: str,
        output_path: str,
        headless: bool,
        materias: Optional[List[Materia]] = None,
        materia_modes: Optional[dict] = None,
    ):
        super().__init__()
        self.username = username
        self.password = password
        self.output_path = output_path
        self.headless = headless
        self.materias = materias
        self.materia_modes = materia_modes or {}

    def run(self):
        try:
            scraper = MoodleScraper(headless=self.headless)
            scraper.progress_cb = lambda msg: self.progress.emit(msg)
            scraper.config.OUTPUT_DIR = self.output_path
            ok = scraper.ejecutar(
                username=self.username,
                password=self.password,
                exportar=True,
                materias=self.materias,
                materia_modes=self.materia_modes,
            )
            if ok:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, "Credenciales inválidas o sesión expirada.")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class FetchMateriasWorker(QtCore.QThread):
    """Obtiene materias tras login sin bloquear la UI."""

    finished = QtCore.pyqtSignal(bool, list, str)  # success, materias, message

    def __init__(self, username: str, password: str):
        super().__init__()
        self.username = username
        self.password = password

    def run(self):
        try:
            scraper = MoodleScraper(headless=True)
            materias = scraper.obtener_materias_con_credenciales(
                username=self.username,
                password=self.password
            )
            if not materias:
                self.finished.emit(False, [], "No se encontraron materias o las credenciales fallaron.")
                return
            self.finished.emit(True, materias, "")
        except Exception as exc:
            self.finished.emit(False, [], str(exc))


class MateriasListView(QtWidgets.QListView):
    """Lista de materias que consume el scroll para no propagarlo al resto de la UI."""

    def wheelEvent(self, event: QtGui.QWheelEvent):
        QtWidgets.QListView.wheelEvent(self, event)
        event.accept()


class ScrappyGUI(QtWidgets.QMainWindow):
    """Ventana principal con estilo moderno."""

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.headless = self.config.HEADLESS
        self.output_path = str(Path.home() / "Downloads")
        self._load_last_output_path()
        self.worker: Optional[ScraperWorker] = None
        self.fetch_worker: Optional[FetchMateriasWorker] = None
        self.materias_disponibles: List[Materia] = []
        self.animations = []
        self.pulse_animation: Optional[QtCore.QPropertyAnimation] = None
        self.username = ""
        self.password = ""
        self._updating_checks = False
        self.keyring_service = "scrappy_moodle_ucc"
        self.materia_modes = {}
        self.settings_path = Path("config/user_settings.json")

        self._setup_window()
        self._build_ui()
        self._apply_entry_animations()
        self._load_saved_credentials()

    def _setup_window(self):
        self.setWindowTitle("Scrappy · Moodle UCC")
        self.resize(960, 640)
        self.setMinimumSize(860, 560)
        self.setStyleSheet("""
            QWidget {
                background-color: #0b1120;
                color: #e5e7eb;
                font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', Arial, sans-serif;
                font-size: 14px;
            }
            QLabel {
                background: transparent;
            }
            QFrame#card {
                background-color: #0f172a;
                border: 1px solid #1f2937;
                border-radius: 18px;
            }
            QLabel#title {
                color: #c084fc;
                font-size: 28px;
                font-weight: 800;
            }
            QLabel#subtitle {
                color: #94a3b8;
                font-size: 15px;
            }
            QLabel#sectionTitle {
                color: #e0f2fe;
                font-size: 18px;
                font-weight: 700;
            }
            QLineEdit {
                background: #111827;
                border: 1px solid #1f2937;
                border-radius: 10px;
                padding: 12px;
                color: #e5e7eb;
            }
            QLineEdit:focus {
                border: 1px solid #7c3aed;
            }
            QPushButton {
                background-color: #7c3aed;
                color: #f8fafc;
                border: none;
                border-radius: 12px;
                padding: 12px 16px;
                font-weight: 700;
                letter-spacing: 0.2px;
            }
            QPushButton:hover {
                background-color: #8b5cf6;
            }
            QPushButton:pressed {
                background-color: #6d28d9;
            }
            QPushButton:disabled {
                background-color: #1f2937;
                color: #475569;
            }
            QPushButton#ghost {
                background: transparent;
                border: 1px solid #1f2937;
                color: #e5e7eb;
            }
            QPushButton#ghost:hover {
                border-color: #334155;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 6px;
                border: 1px solid #334155;
                background: #111827;
            }
            QCheckBox::indicator:checked {
                background: #22d3ee;
                border-color: #22d3ee;
            }
            QListView {
                background: #0d162b;
                border: 1px solid #1f2937;
                border-radius: 12px;
                padding: 10px 6px;
            }
            QListView::item {
                padding: 12px 10px;
                margin: 2px 0;
                color: #e5e7eb;
                border-radius: 10px;
            }
            QListView::item:hover {
                background: rgba(124, 58, 237, 0.12);
            }
            QListView::item:selected {
                background: rgba(34, 211, 238, 0.14);
                color: #e5e7eb;
            }
            QListView::indicator {
                width: 0px;
                height: 0px;
                margin: 0px;
                padding: 0px;
                border: none;
                background: transparent;
            }
            QProgressBar {
                border: 1px solid #1f2937;
                border-radius: 10px;
                background: #0b1120;
                padding: 3px;
                height: 18px;
                color: #e5e7eb;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #22d3ee;
                border-radius: 8px;
            }
            QScrollArea {
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 8px 0 8px 4px;
            }
            QScrollBar::handle:vertical {
                background: #22d3ee;
                min-height: 32px;
                border-radius: 6px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                width: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: rgba(255,255,255,0.04);
            }
        """)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(12)

        root_layout.addLayout(self._build_header())

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(16)
        body.setContentsMargins(0, 0, 0, 0)

        self.status_card = self._build_status_card()
        interaction_panel = self._build_interaction_panel()

        body.addWidget(self.status_card, stretch=1)
        body.addWidget(interaction_panel, stretch=3)

        root_layout.addLayout(body, stretch=1)

    def _build_header(self) -> QtWidgets.QHBoxLayout:
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(10)
        title = QtWidgets.QLabel("Scrappy · Moodle UCC")
        title.setObjectName("title")
        subtitle = QtWidgets.QLabel("Automatiza la descarga de recursos y evita errores al navegar manualmente.")
        subtitle.setObjectName("subtitle")

        header.addWidget(title, alignment=QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        header.addStretch()
        header.addWidget(subtitle, alignment=QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        return header

    def _build_interaction_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.stack = QtWidgets.QStackedWidget()
        self.credentials_card = self._build_credentials_card()
        self.options_card = self._build_options_card()
        self.stack.addWidget(self.credentials_card)
        self.stack.addWidget(self.options_card)

        layout.addWidget(self.stack)
        return panel

    def _build_credentials_card(self):
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        section = QtWidgets.QLabel("Acceso a Moodle")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)

        self.username_input = self._labeled_input(layout, "Usuario UCC")
        self.password_input = self._labeled_input(layout, "Contraseña", password=True)
        self.remember_checkbox = QtWidgets.QCheckBox("Recordar en este dispositivo")
        layout.addWidget(self.remember_checkbox)

        layout.addStretch()

        buttons = QtWidgets.QHBoxLayout()
        self.fetch_button = QtWidgets.QPushButton("Conectar y obtener materias")
        self.fetch_button.setMinimumHeight(46)
        self.fetch_button.clicked.connect(self._start_fetch_materias)
        close = QtWidgets.QPushButton("Cerrar")
        close.setObjectName("ghost")
        close.setMinimumHeight(46)
        close.clicked.connect(self.close)

        buttons.addWidget(self.fetch_button)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        return card

    def _build_options_card(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        section = QtWidgets.QLabel("Configurar extracción")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)

        layout.addWidget(QtWidgets.QLabel("Selecciona las materias a scrapear"))

        self.materias_view = MateriasListView()
        self.materias_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.materias_view.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.materias_view.setUniformItemSizes(True)
        self.materias_view.setMinimumHeight(240)
        self.materias_view.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.materias_view.setItemDelegate(MateriaDelegate(self.materias_view))
        self.materias_model = QtGui.QStandardItemModel(self.materias_view)
        self.materias_view.setModel(self.materias_model)
        self.materias_model.itemChanged.connect(self._on_materia_item_changed)
        self.materias_view.clicked.connect(self._on_materia_clicked)
        self.materias_view.viewport().installEventFilter(self)
        layout.addWidget(self.materias_view)

        self.select_all_btn = QtWidgets.QPushButton("Seleccionar todas")
        self.select_all_btn.setMinimumHeight(40)
        self.select_all_btn.setObjectName("ghost")
        self.select_all_btn.clicked.connect(self._toggle_all_items)
        layout.addWidget(self.select_all_btn)

        update_box = QtWidgets.QGroupBox("Encontrar nuevos contenidos")
        update_box.setStyleSheet("QGroupBox { border: 1px solid #1f2937; border-radius: 10px; margin-top: 6px; padding-top: 10px; }")
        update_layout = QtWidgets.QVBoxLayout(update_box)
        update_layout.setContentsMargins(12, 8, 12, 12)
        update_layout.setSpacing(8)

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("Actualizar (buscar cambios en módulos)", ("update", True))
        self.mode_combo.addItem("Solo módulos nuevos", ("update", False))
        self.mode_combo.addItem("Forzar descarga completa", ("full", True))

        apply_layout = QtWidgets.QHBoxLayout()
        self.apply_selected_btn = QtWidgets.QPushButton("Aplicar")
        self.apply_selected_btn.clicked.connect(self._apply_mode_selected)
        apply_layout.addWidget(self.mode_combo)
        apply_layout.addWidget(self.apply_selected_btn)

        self.mode_summary = QtWidgets.QLabel("Modo: Actualizar (buscar cambios)")
        self.mode_summary.setStyleSheet("color: #94a3b8;")

        update_layout.addLayout(apply_layout)
        update_layout.addWidget(self.mode_summary)
        layout.addWidget(update_box)

        layout.addSpacing(6)
        self._add_path_picker(layout)

        layout.addSpacing(12)
        self.headless_checkbox = QtWidgets.QCheckBox("Usar modo headless (oculta el navegador)")
        self.headless_checkbox.setChecked(self.headless)
        self.headless_checkbox.stateChanged.connect(self._sync_browser_from_headless)
        layout.addWidget(self.headless_checkbox)

        self.browser_checkbox = QtWidgets.QCheckBox("Mostrar navegador mientras trabaja")
        self.browser_checkbox.setChecked(not self.headless)
        self.browser_checkbox.stateChanged.connect(self._sync_headless)
        layout.addWidget(self.browser_checkbox)

        layout.addStretch()

        buttons_layout = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Comenzar scraping")
        self.start_button.clicked.connect(self._start_scraping)
        self.start_button.setMinimumHeight(46)

        self.close_button = QtWidgets.QPushButton("Cerrar")
        self.close_button.setObjectName("ghost")
        self.close_button.clicked.connect(self.close)
        self.close_button.setMinimumHeight(46)

        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.close_button)
        layout.addLayout(buttons_layout)
        scroll.setWidget(card)
        return scroll

    def _build_status_card(self) -> QtWidgets.QFrame:
        status_card = QtWidgets.QFrame()
        status_card.setObjectName("card")
        status_card.setMinimumWidth(260)
        layout = QtWidgets.QVBoxLayout(status_card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(10)
        self.pulse = QtWidgets.QFrame()
        self.pulse.setFixedSize(16, 16)
        self.pulse.setStyleSheet("background: #22d3ee; border-radius: 8px;")
        header_row.addWidget(self.pulse, alignment=QtCore.Qt.AlignmentFlag.AlignTop)

        text_container = QtWidgets.QVBoxLayout()
        self.status_label = QtWidgets.QLabel("Preparando navegador...")
        self.status_label.setStyleSheet("font-weight: 700; color: #e5e7eb;")
        self.status_label.setWordWrap(True)
        self.substatus_label = QtWidgets.QLabel("Inicia sesión para obtener las materias.")
        self.substatus_label.setStyleSheet("color: #94a3b8;")
        self.substatus_label.setWordWrap(True)

        text_container.addWidget(self.status_label)
        text_container.addWidget(self.substatus_label)

        header_row.addLayout(text_container, stretch=1)

        layout.addLayout(header_row)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFixedHeight(22)
        self.progress.setMinimumWidth(220)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #1f2937;
                border-radius: 11px;
                background: #0b1120;
                padding: 2px;
                color: #e5e7eb;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #22d3ee;
                border-radius: 9px;
            }
        """)
        layout.addWidget(self.progress)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(420)
        self.log_view.setFont(QtGui.QFont("Consolas", 11))
        self.log_view.setStyleSheet("background: #0d162b; border: 1px solid #1f2937; border-radius: 10px; color: #cbd5e1;")
        layout.addWidget(self.log_view, stretch=1)

        return status_card

    def _labeled_input(self, parent_layout: QtWidgets.QVBoxLayout, label: str, password: bool = False):
        wrapper = QtWidgets.QVBoxLayout()
        lbl = QtWidgets.QLabel(label)
        lbl.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        edit = QtWidgets.QLineEdit()
        if password:
            edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        wrapper.addWidget(lbl)
        wrapper.addWidget(edit)
        parent_layout.addLayout(wrapper)
        return edit

    def _add_path_picker(self, parent_layout: QtWidgets.QVBoxLayout):
        lbl = QtWidgets.QLabel("Carpeta de destino")
        lbl.setStyleSheet("color: #cbd5e1; font-weight: 600;")

        path_layout = QtWidgets.QHBoxLayout()
        self.path_display = QtWidgets.QLineEdit(self.output_path)
        self.path_display.setReadOnly(True)
        self.path_display.setCursorPosition(0)
        browse = QtWidgets.QPushButton("Elegir carpeta")
        browse.setObjectName("ghost")
        browse.clicked.connect(self._browse_path)

        path_layout.addWidget(self.path_display)
        path_layout.addWidget(browse)

        parent_layout.addWidget(lbl)
        parent_layout.addLayout(path_layout)

    def _apply_entry_animations(self):
        for widget in (self.credentials_card,):
            effect = QtWidgets.QGraphicsOpacityEffect()
            widget.setGraphicsEffect(effect)
            anim = QtCore.QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(700)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
            anim.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
            self.animations.append(anim)

    def _browse_path(self):
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta de destino",
            self.output_path
        )
        if selected:
            self.output_path = selected
            self.path_display.setText(selected)
            self._save_last_output_path()
        # Mantener foco en la lista tras cerrar el diálogo para seguir scroll interno
        self.materias_view.setFocus()

    def _sync_headless(self):
        # Mantener coherentes los toggles headless/mostrar navegador
        self.headless = not self.browser_checkbox.isChecked()
        self.headless_checkbox.setChecked(self.headless)

    def _sync_browser_from_headless(self):
        self.headless = self.headless_checkbox.isChecked()
        self.browser_checkbox.setChecked(not self.headless)

    def _start_fetch_materias(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        if not username or not password:
            QtWidgets.QMessageBox.warning(self, "Faltan datos", "Ingresa usuario y contraseña.")
            return

        self.username = username
        self.password = password
        self._set_credentials_enabled(False)
        self._show_status(True, "Conectando y obteniendo materias...", "Esto tomará solo unos segundos.")
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.pulse.setStyleSheet("background: #22d3ee; border-radius: 8px;")
        self._start_pulse_animation()

        self.fetch_worker = FetchMateriasWorker(username, password)
        self.fetch_worker.finished.connect(self._on_fetch_finished)
        self.fetch_worker.start()

    def _on_fetch_finished(self, success: bool, materias: list, message: str):
        self._set_credentials_enabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if success else 0)

        if success:
            if self.remember_checkbox.isChecked():
                self._save_credentials()
            else:
                self._clear_saved_credentials()
            self.materias_disponibles = materias
            self._populate_materias_list(materias)
            self.status_label.setText("Materias obtenidas")
            self.substatus_label.setText("Selecciona qué materias scrapear y continúa.")
            self.pulse.setStyleSheet("background: #22c55e; border-radius: 8px;")
            self.stack.setCurrentWidget(self.options_card)
        else:
            self.status_label.setText("No se pudo obtener materias")
            self.substatus_label.setText(message or "Revisa las credenciales y vuelve a intentar.")
            self.pulse.setStyleSheet("background: #ef4444; border-radius: 8px;")
            QtWidgets.QMessageBox.critical(self, "Error de conexión", message or "No se pudieron listar materias.")

    def _populate_materias_list(self, materias: List[Materia]):
        self._updating_checks = True
        try:
            self.materias_model.clear()
            self.materia_modes = {}
            for materia in materias:
                item = QtGui.QStandardItem(materia.nombre)
                item.setData(materia, QtCore.Qt.ItemDataRole.UserRole)
                item.setCheckable(True)
                item.setEditable(False)
                item.setCheckState(QtCore.Qt.CheckState.Checked)
                self._apply_item_style(item)
                self.materias_model.appendRow(item)
                self.materia_modes[materia.nombre] = {"mode": "update", "scan_existing": True}
            self.materias_view.viewport().update()
            self._sync_select_all_button()
            self._refresh_mode_summary()
            # Asegurar fonts válidos en la lista
            self.materias_view.setFont(QtGui.QFont("Segoe UI", 11))
        finally:
            self._updating_checks = False

    def _toggle_all_items(self):
        self._updating_checks = True
        try:
            all_checked = all(self.materias_model.item(i).checkState() == QtCore.Qt.CheckState.Checked for i in range(self.materias_model.rowCount()))
            target_state = QtCore.Qt.CheckState.Unchecked if all_checked else QtCore.Qt.CheckState.Checked
            for i in range(self.materias_model.rowCount()):
                item = self.materias_model.item(i)
                item.setCheckState(target_state)
                self._apply_item_style(item)
            self.materias_view.viewport().update()
            self._sync_select_all_button()
        finally:
            self._updating_checks = False

    def _current_mode_choice(self):
        data = self.mode_combo.currentData()
        if data:
            return {"mode": data[0], "scan_existing": data[1]}
        return {"mode": "update", "scan_existing": True}

    def _apply_mode_selected(self):
        choice = self._current_mode_choice()
        applied = False
        for i in range(self.materias_model.rowCount()):
            item = self.materias_model.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                materia = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if materia:
                    self.materia_modes[materia.nombre] = choice.copy()
                    applied = True
        # Si no había seleccionados, aplica a todos
        if not applied:
            for i in range(self.materias_model.rowCount()):
                item = self.materias_model.item(i)
                materia = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if materia:
                    self.materia_modes[materia.nombre] = choice.copy()
        self._refresh_mode_summary()

    def _refresh_mode_summary(self):
        modes = set()
        for i in range(self.materias_model.rowCount()):
            item = self.materias_model.item(i)
            materia = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if materia and materia.nombre in self.materia_modes:
                m = self.materia_modes[materia.nombre]
                modes.add((m["mode"], m.get("scan_existing", True)))
        if len(modes) == 1:
            mode, scan = next(iter(modes))
            if mode == "full":
                text = "Modo: Forzar descarga completa (todas las materias)"
            elif not scan:
                text = "Modo: Solo módulos nuevos"
            else:
                text = "Modo: Actualizar (buscar cambios)"
        else:
            text = "Modo: personalizado por materia"
        self.mode_summary.setText(text)

    def _get_selected_materias(self) -> List[Materia]:
        seleccionadas: List[Materia] = []
        for i in range(self.materias_model.rowCount()):
            item = self.materias_model.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                materia = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if materia:
                    seleccionadas.append(materia)
        return seleccionadas

    def _start_scraping(self):
        dest = self.path_display.text().strip()
        self.headless = self.headless_checkbox.isChecked() and not self.browser_checkbox.isChecked()

        if not self.username or not self.password:
            QtWidgets.QMessageBox.warning(self, "Faltan datos", "Primero ingresa credenciales y obtén las materias.")
            return

        if not dest:
            QtWidgets.QMessageBox.warning(self, "Destino inválido", "Selecciona una carpeta de destino.")
            return

        materias_seleccionadas = self._get_selected_materias()
        if not materias_seleccionadas:
            QtWidgets.QMessageBox.warning(self, "Selecciona materias", "Elige al menos una materia para scrapear.")
            return

        self._set_options_enabled(False)
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.pulse.setStyleSheet("background: #22d3ee; border-radius: 8px;")
        self._show_status(True, "Inicializando navegador...", "No cierres la ventana.")
        self.log_view.clear()
        self._append_log("Inicializando navegador...")
        self._start_pulse_animation()

        self.worker = ScraperWorker(
            self.username,
            self.password,
            dest,
            self.headless,
            materias=materias_seleccionadas,
            materia_modes=self.materia_modes,
        )
        self.worker.progress.connect(self._append_log)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_materia_item_changed(self, item: QtGui.QStandardItem):
        if self._updating_checks:
            return
        self._apply_item_style(item)
        self._sync_select_all_button()

    def _on_materia_clicked(self, index: QtCore.QModelIndex):
        if not index.isValid():
            return
        self._updating_checks = True
        try:
            item = self.materias_model.itemFromIndex(index)
            current = item.checkState()
            item.setCheckState(QtCore.Qt.CheckState.Unchecked if current == QtCore.Qt.CheckState.Checked else QtCore.Qt.CheckState.Checked)
            self._apply_item_style(item)
            self._sync_select_all_button()
            self.materias_view.viewport().update()
        finally:
            self._updating_checks = False

    def _sync_select_all_button(self):
        total = self.materias_model.rowCount()
        checked = sum(1 for i in range(total) if self.materias_model.item(i).checkState() == QtCore.Qt.CheckState.Checked)
        if checked == total and total > 0:
            self.select_all_btn.setText("Deseleccionar todas")
        else:
            self.select_all_btn.setText("Seleccionar todas")

    def _apply_item_style(self, item: QtGui.QStandardItem):
        font = item.font()
        if font.pointSize() <= 0 and font.pixelSize() <= 0:
            font.setPointSize(11)
        font.setStrikeOut(item.checkState() == QtCore.Qt.CheckState.Checked)
        item.setFont(font)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if watched == self.materias_view.viewport():
            if event.type() in (QtCore.QEvent.Type.Wheel, QtCore.QEvent.Type.MouseMove):
                # Forzar fuente válida en el viewport
                f = self.materias_view.font()
                if f.pointSize() <= 0 and f.pixelSize() <= 0:
                    f.setPointSize(11)
                    self.materias_view.setFont(f)
        return super().eventFilter(watched, event)

    def _set_credentials_enabled(self, enabled: bool):
        for widget in (
            self.username_input,
            self.password_input,
            self.remember_checkbox,
            self.fetch_button,
        ):
            widget.setEnabled(enabled)

    def _set_options_enabled(self, enabled: bool):
        for widget in (
            self.materias_view,
            self.select_all_btn,
            self.mode_combo,
            self.apply_selected_btn,
            self.path_display,
            self.headless_checkbox,
            self.browser_checkbox,
            self.start_button,
        ):
            widget.setEnabled(enabled)

    def _show_status(self, visible: bool, status: str = "", substatus: str = ""):
        self.status_card.setVisible(visible)
        if status:
            self.status_label.setText(status)
        if substatus:
            self.substatus_label.setText(substatus)

    def _start_pulse_animation(self):
        if self.pulse_animation:
            self.pulse_animation.stop()

        effect = QtWidgets.QGraphicsOpacityEffect()
        self.pulse.setGraphicsEffect(effect)
        anim = QtCore.QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(1200)
        anim.setStartValue(0.25)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QtCore.QEasingCurve.Type.InOutSine)
        anim.setLoopCount(-1)
        anim.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self.pulse_animation = anim

    def _load_saved_credentials(self):
        """Carga credenciales guardadas en keyring y arranca fetch automático si existen."""
        try:
            saved_username = keyring.get_password(self.keyring_service, "last_username")
            if not saved_username:
                return
            saved_password = keyring.get_password(self.keyring_service, saved_username)
            if not saved_password:
                return
            self.username = saved_username
            self.password = saved_password
            self.username_input.setText(saved_username)
            self.password_input.setText(saved_password)
            self.remember_checkbox.setChecked(True)
            # Arrancar fetch tras un breve delay para que la UI termine de cargar
            QtCore.QTimer.singleShot(200, self._start_fetch_materias)
        except Exception:
            pass

    def _save_credentials(self):
        """Guarda usuario/contraseña en el almacén seguro del sistema."""
        try:
            keyring.set_password(self.keyring_service, "last_username", self.username)
            keyring.set_password(self.keyring_service, self.username, self.password)
        except Exception:
            pass

    def _clear_saved_credentials(self):
        """Elimina credenciales guardadas."""
        try:
            keyring.delete_password(self.keyring_service, "last_username")
        except Exception:
            pass
        try:
            keyring.delete_password(self.keyring_service, self.username)
        except Exception:
            pass

    def _load_last_output_path(self):
        """Carga la última ruta de salida guardada."""
        try:
            if self.settings_path.exists():
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    last = data.get("last_output_path")
                    if last:
                        self.output_path = last
        except Exception:
            pass

    def _save_last_output_path(self):
        """Guarda la ruta de salida elegida por el usuario."""
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump({"last_output_path": self.output_path}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _append_log(self, text: str):
        if not text:
            return
        self.log_view.append(text)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
        self.status_label.setText(text)

    def _on_finished(self, success: bool, message: str):
        self._set_options_enabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if success else 0)
        if success:
            self.status_label.setText("Descarga completada")
            self.substatus_label.setText(f"Guardado en: {self.output_path}")
            self.pulse.setStyleSheet("background: #22c55e; border-radius: 8px;")
        else:
            self.status_label.setText("Ocurrió un error")
            self.substatus_label.setText(message or "Revisa las credenciales o la conexión.")
            self.pulse.setStyleSheet("background: #ef4444; border-radius: 8px;")
            QtWidgets.QMessageBox.critical(self, "Error durante el scraping", message or "Error desconocido.")
        self._append_log("Proceso finalizado.")


def main():
    app = QtWidgets.QApplication([])
    app.setFont(QtGui.QFont("Segoe UI", 11))
    window = ScrappyGUI()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
