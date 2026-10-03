import json
from pathlib import Path
from typing import Optional

import keyring
from PyQt6 import QtCore, QtGui, QtWidgets

from gui.panels.configuracion import ConfiguracionPanel
from gui.panels.conexion import ConexionPanel
from gui.panels.duplicados import DuplicadosPanel
from gui.panels.materias import MateriasPanel
from gui.panels.registro import RegistroPanel
from gui.sidebar import Sidebar
from gui.theme import BG_APP, GLOBAL_STYLESHEET
from gui.workers import (
    STATUS_CANCELLED,
    STATUS_OK,
    STATUS_PARTIAL,
    DuplicatesWorker,
    FetchMateriasWorker,
    ScraperWorker,
)
from utils.config import Config

PANEL_CONEXION = 0
PANEL_MATERIAS = 1
PANEL_CONFIGURACION = 2
PANEL_REGISTRO = 3
PANEL_DUPLICADOS = 4

# Seconds to let the Go core save its manifest after a cancel before closing.
CLOSE_WAIT_MS = 10_000

APP_NAME = "Scrappy"
# Older builds wrote settings relative to the working directory.
LEGACY_SETTINGS_PATH = Path("config/user_settings.json")


def user_settings_path() -> Path:
    """Per-user settings file in the OS config folder (independent of the cwd)."""
    if not QtCore.QCoreApplication.applicationName():
        QtCore.QCoreApplication.setApplicationName(APP_NAME)
    location = QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.StandardLocation.AppConfigLocation
    )
    base = Path(location) if location else Path.home() / ".scrappy"
    return base / "user_settings.json"


class ScrappyGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self._output_path = str(Path.home() / "Downloads")
        self._settings_path = user_settings_path()
        self._api_token = ""
        self._username = ""
        self._password = ""
        self._keyring_service = "scrappy_moodle_ucc"
        self.worker: Optional[ScraperWorker] = None
        self.fetch_worker: Optional[FetchMateriasWorker] = None
        self.duplicates_worker: Optional[DuplicatesWorker] = None

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
        self.config_panel = ConfiguracionPanel(self._output_path)
        self.config_panel.output_path_changed.connect(self._on_output_path_changed)
        self.registro_panel = RegistroPanel()
        self.registro_panel.cancel_requested.connect(self._cancel_scraping)
        self.duplicados_panel = DuplicadosPanel()
        self.duplicados_panel.set_folder(self._output_path)
        self.duplicados_panel.scan_requested.connect(self._start_duplicate_scan)
        self.duplicados_panel.remove_requested.connect(self._start_duplicate_removal)

        for panel in (
            self.conexion_panel,
            self.materias_panel,
            self.config_panel,
            self.registro_panel,
            self.duplicados_panel,
        ):
            self.stack.addWidget(panel)

        root.addWidget(self.stack, stretch=1)

    def _navigate_to(self, index: int):
        self.stack.setCurrentIndex(index)
        self.sidebar.set_active(index)

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    @staticmethod
    def _is_running(worker) -> bool:
        return worker is not None and worker.isRunning()

    def _start_fetch(self, username: str, password: str):
        # The saved-credentials auto login and a Conectar click can race.
        if self._is_running(self.fetch_worker):
            return
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
            status = "Conectado · Go API ✓"
            self.conexion_panel.set_status("connected", status)
            self._navigate_to(PANEL_MATERIAS)
            return

        error_message = message or "No se pudieron listar las materias."
        self.conexion_panel.set_status("error", error_message)
        QtWidgets.QMessageBox.critical(self, "Error de conexión", error_message)

    def _start_scraping(self, materias: list, materia_modes: dict):
        if self._is_running(self.worker) or self._is_running(self.duplicates_worker):
            return
        self.materias_panel.set_running(True)
        self.registro_panel.clear()
        self.registro_panel.set_running(True)
        self._navigate_to(PANEL_REGISTRO)
        self.worker = ScraperWorker(
            username=self._username,
            password=self._password,
            output_path=self.config_panel.get_output_path(),
            materias=materias,
            materia_modes=materia_modes,
            api_token=self._api_token,
        )
        self.worker.progress.connect(self.registro_panel.append)
        self.worker.finished.connect(self._on_scraping_finished)
        self.worker.start()

    def _cancel_scraping(self):
        if not self._is_running(self.worker):
            return
        self.registro_panel.set_cancelling()
        self.registro_panel.append("■ Cancelando... lo ya descargado queda guardado.")
        self.worker.cancel()

    def _on_scraping_finished(self, status: str, message: str):
        self.materias_panel.set_running(False)
        self.registro_panel.set_running(False)
        output_path = self.config_panel.get_output_path()
        if status == STATUS_OK:
            self.registro_panel.append("✓ Descarga completada.")
            self.registro_panel.append(f"  Guardado en: {output_path}")
            return
        if status == STATUS_CANCELLED:
            self.registro_panel.append("■ Descarga cancelada. Lo ya descargado quedó guardado.")
            return
        if status == STATUS_PARTIAL:
            self.registro_panel.append(f"⚠ Descarga completada con errores: {message}")
            self.registro_panel.append(f"  Guardado en: {output_path}")
            QtWidgets.QMessageBox.warning(
                self,
                "Descarga completada con errores",
                "Se descargó todo lo posible, pero algunas materias o archivos fallaron.\n\n"
                "El detalle está en el Registro y en .scrappy/sync-report.json.",
            )
            return

        error_message = message or "Error desconocido."
        self.registro_panel.append(f"✗ Error: {error_message}")
        QtWidgets.QMessageBox.critical(self, "Error durante la descarga", error_message)

    def _confirm_close_during_sync(self) -> bool:
        answer = QtWidgets.QMessageBox.question(
            self,
            "Descarga en curso",
            "Hay una descarga en curso. ¿Cancelarla y cerrar Scrappy?\n\n"
            "Lo ya descargado queda guardado.",
        )
        return answer == QtWidgets.QMessageBox.StandardButton.Yes

    def closeEvent(self, a0):
        if self._is_running(self.worker):
            if not self._confirm_close_during_sync():
                a0.ignore()
                return
        # Stop the Go core and wait for each thread: a QThread destroyed while
        # running crashes the app, and an orphaned core keeps downloading.
        for worker in (self.worker, self.fetch_worker, self.duplicates_worker):
            if not self._is_running(worker):
                continue
            try:
                worker.finished.disconnect()
            except TypeError:
                pass
            worker.cancel()
            worker.wait(CLOSE_WAIT_MS)
        a0.accept()

    def _run_duplicates_worker(self, paths: Optional[list], busy_text: str):
        if self._is_running(self.worker):
            self.duplicados_panel.show_error("Esperá a que termine la descarga en curso.")
            return
        if self._is_running(self.duplicates_worker):
            return
        output_path = self.config_panel.get_output_path()
        if paths is None:
            self.duplicates_worker = DuplicatesWorker(output_path)
            self.duplicates_worker.finished.connect(self._on_duplicate_scan_finished)
        else:
            self.duplicates_worker = DuplicatesWorker(output_path, paths)
            self.duplicates_worker.finished.connect(self._on_duplicate_removal_finished)
        self.duplicados_panel.set_busy(True, busy_text)
        self.duplicates_worker.start()

    def _start_duplicate_scan(self):
        self._run_duplicates_worker(None, "Buscando duplicados...")

    def _start_duplicate_removal(self, paths: list):
        self._run_duplicates_worker(paths, "Borrando duplicados...")

    def _on_duplicate_scan_finished(self, ok: bool, result: dict, error: str):
        if not ok:
            self.duplicados_panel.show_error(error or "No se pudo buscar duplicados.")
            return
        self.duplicados_panel.show_scan(result.get("duplicates") or [], int(result.get("bytes") or 0))

    def _on_duplicate_removal_finished(self, ok: bool, result: dict, error: str):
        if not ok:
            self.duplicados_panel.show_error(error or "No se pudieron borrar los duplicados.")
            return
        self.duplicados_panel.show_removal(
            result.get("removed") or [], result.get("skipped") or [], int(result.get("bytes") or 0)
        )

    def _on_output_path_changed(self, path: str):
        self._output_path = path
        self.duplicados_panel.set_folder(path)
        self._save_last_output_path()

    def _load_last_output_path(self):
        try:
            source = self._settings_path
            if not source.exists():
                source = LEGACY_SETTINGS_PATH
            if not source.exists():
                return
            with open(source, "r", encoding="utf-8") as file:
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
    app.setApplicationName(APP_NAME)
    app.setFont(QtGui.QFont("-apple-system", 13))
    window = ScrappyGUI()
    window.show()
    app.exec()
