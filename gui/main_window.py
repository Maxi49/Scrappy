import json
from pathlib import Path
from typing import Optional

import keyring
from PyQt6 import QtCore, QtGui, QtWidgets

from gui.panels.configuracion import ConfiguracionPanel
from gui.panels.conexion import ConexionPanel
from gui.panels.materias import MateriasPanel
from gui.panels.registro import RegistroPanel
from gui.sidebar import Sidebar
from gui.theme import BG_APP, GLOBAL_STYLESHEET
from gui.workers import FetchMateriasWorker, ScraperWorker
from utils.config import Config

PANEL_CONEXION = 0
PANEL_MATERIAS = 1
PANEL_CONFIGURACION = 2
PANEL_REGISTRO = 3


class ScrappyGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self._output_path = str(Path.home() / "Downloads")
        self._settings_path = Path("config/user_settings.json")
        self._api_token = ""
        self._username = ""
        self._password = ""
        self._keyring_service = "scrappy_moodle_ucc"
        self.worker: Optional[ScraperWorker] = None
        self.fetch_worker: Optional[FetchMateriasWorker] = None

        self._load_last_output_path()
        self._setup_window()
        self._build_ui()
        self._load_saved_credentials()

    def _setup_window(self):
        self.setWindowTitle("Scrappy · Moodle UCC")
        self.resize(960, 640)
        self.setMinimumSize(860, 560)
        self.setStyleSheet(GLOBAL_STYLESHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.nav_changed.connect(self._on_nav_changed)
        root.addWidget(self.sidebar)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.setStyleSheet(f"background: {BG_APP};")

        self.conexion_panel = ConexionPanel()
        self.conexion_panel.login_requested.connect(self._start_fetch)
        self.materias_panel = MateriasPanel()
        self.materias_panel.start_requested.connect(self._start_scraping)
        self.config_panel = ConfiguracionPanel(self._output_path, self.config.HEADLESS)
        self.config_panel.output_path_changed.connect(self._on_output_path_changed)
        self.registro_panel = RegistroPanel()

        for panel in (
            self.conexion_panel,
            self.materias_panel,
            self.config_panel,
            self.registro_panel,
        ):
            self.stack.addWidget(panel)

        root.addWidget(self.stack, stretch=1)

    def _navigate_to(self, index: int):
        self.stack.setCurrentIndex(index)
        self.sidebar.set_active(index)

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _start_fetch(self, username: str, password: str):
        self._username = username
        self._password = password
        self.conexion_panel.set_loading(True)
        self.fetch_worker = FetchMateriasWorker(username, password, self.config.BASE_URL)
        self.fetch_worker.finished.connect(self._on_fetch_finished)
        self.fetch_worker.start()

    def _on_fetch_finished(self, success: bool, materias: list, message: str, token: str):
        self.conexion_panel.set_loading(False)
        self._api_token = token
        if success:
            if self.conexion_panel.should_remember():
                self._save_credentials()
            else:
                self._clear_saved_credentials()
            self.materias_panel.populate(materias)
            status = "Conectado · API ✓" if token else "Conectado"
            self.conexion_panel.set_status("connected", status)
            self._navigate_to(PANEL_MATERIAS)
            return

        error_message = message or "No se pudieron listar las materias."
        self.conexion_panel.set_status("error", error_message)
        QtWidgets.QMessageBox.critical(self, "Error de conexión", error_message)

    def _start_scraping(self, materias: list, materia_modes: dict):
        self.materias_panel.set_running(True)
        self.registro_panel.clear()
        self._navigate_to(PANEL_REGISTRO)
        self.worker = ScraperWorker(
            username=self._username,
            password=self._password,
            output_path=self.config_panel.get_output_path(),
            headless=self.config_panel.get_headless(),
            materias=materias,
            materia_modes=materia_modes,
            api_token=self._api_token,
        )
        self.worker.progress.connect(self.registro_panel.append)
        self.worker.finished.connect(self._on_scraping_finished)
        self.worker.start()

    def _on_scraping_finished(self, success: bool, message: str):
        self.materias_panel.set_running(False)
        if success:
            self.registro_panel.append("✓ Descarga completada.")
            self.registro_panel.append(f"  Guardado en: {self.config_panel.get_output_path()}")
            return

        error_message = message or "Error desconocido."
        self.registro_panel.append(f"✗ Error: {error_message}")
        QtWidgets.QMessageBox.critical(self, "Error durante el scraping", error_message)

    def _on_output_path_changed(self, path: str):
        self._output_path = path
        self._save_last_output_path()

    def _load_last_output_path(self):
        try:
            if not self._settings_path.exists():
                return
            with open(self._settings_path, "r", encoding="utf-8") as file:
                last = json.load(file).get("last_output_path")
            if last:
                self._output_path = last
        except Exception:
            pass

    def _save_last_output_path(self):
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._settings_path, "w", encoding="utf-8") as file:
                json.dump({"last_output_path": self._output_path}, file, ensure_ascii=False)
        except Exception:
            pass

    def _load_saved_credentials(self):
        try:
            username = keyring.get_password(self._keyring_service, "last_username")
            if not username:
                return
            password = keyring.get_password(self._keyring_service, username)
            if not password:
                return
            self.conexion_panel.set_credentials(username, password)
            self.conexion_panel.set_remember(True)
            QtCore.QTimer.singleShot(200, lambda: self._start_fetch(username, password))
        except Exception:
            pass

    def _save_credentials(self):
        # Si el usuario recordado cambia, borrar la contraseña del usuario anterior
        # para no dejarla huérfana en el keychain del sistema indefinidamente.
        try:
            usuario_anterior = keyring.get_password(self._keyring_service, "last_username")
            if usuario_anterior and usuario_anterior != self._username:
                keyring.delete_password(self._keyring_service, usuario_anterior)
        except Exception:
            pass
        try:
            keyring.set_password(self._keyring_service, "last_username", self._username)
            keyring.set_password(self._keyring_service, self._username, self._password)
        except Exception:
            pass

    def _clear_saved_credentials(self):
        for key in ("last_username", self._username):
            try:
                keyring.delete_password(self._keyring_service, key)
            except Exception:
                pass


def main():
    app = QtWidgets.QApplication([])
    app.setFont(QtGui.QFont("-apple-system", 13))
    window = ScrappyGUI()
    window.show()
    app.exec()
