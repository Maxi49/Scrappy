import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtGui, QtWidgets


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class MainWindowTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    @patch("keyring.get_password", return_value=None)
    def test_main_window_wires_six_panels(self, _get_password):
        from gui.main_window import ScrappyGUI

        window = ScrappyGUI()

        self.assertEqual(window.stack.count(), 6)
        self.assertEqual(len(window.sidebar._buttons), 6)
        self.assertEqual(window.stack.currentIndex(), 0)



@patch("keyring.get_password", return_value=None)
class MainWindowWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    def _window(self):
        from gui.main_window import ScrappyGUI

        return ScrappyGUI()

    def test_partial_failure_warns_instead_of_reporting_an_error(self, _get_password):
        window = self._window()
        with patch.object(QtWidgets.QMessageBox, "warning") as warning, \
                patch.object(QtWidgets.QMessageBox, "critical") as critical:
            window._on_scraping_finished("partial", "2 materia(s) o recurso(s) fallaron")
        warning.assert_called_once()
        critical.assert_not_called()

    def test_total_failure_is_still_an_error(self, _get_password):
        window = self._window()
        with patch.object(QtWidgets.QMessageBox, "critical") as critical:
            window._on_scraping_finished("error", "credenciales rechazadas")
        critical.assert_called_once()

    def test_cancelled_sync_shows_no_popup(self, _get_password):
        window = self._window()
        with patch.object(QtWidgets.QMessageBox, "warning") as warning, \
                patch.object(QtWidgets.QMessageBox, "critical") as critical:
            window._on_scraping_finished("cancelled", "Operación cancelada.")
        warning.assert_not_called()
        critical.assert_not_called()
        self.assertTrue(window.registro_panel.cancel_btn.isHidden())

    def test_cancel_button_cancels_the_running_sync(self, _get_password):
        window = self._window()
        with patch("gui.main_window.ScraperWorker") as Worker:
            window._start_scraping([], {})
            window.registro_panel.cancel_btn.click()
        Worker.return_value.cancel.assert_called_once()
        self.assertFalse(window.registro_panel.cancel_btn.isEnabled())

    def test_login_is_not_started_twice_while_one_is_running(self, _get_password):
        window = self._window()
        with patch("gui.main_window.FetchMateriasWorker") as Worker:
            Worker.return_value.isRunning.return_value = True
            window._start_fetch("u", "p")
            window._start_fetch("u", "p")
        self.assertEqual(Worker.call_count, 1)

    def test_duplicate_scan_uses_the_output_folder(self, _get_password):
        window = self._window()
        window.config_panel.set_output_path("/tmp/destino")
        with patch("gui.main_window.DuplicatesWorker") as Worker:
            Worker.return_value.isRunning.return_value = False
            window.duplicados_panel.scan_btn.click()
        Worker.assert_called_once_with("/tmp/destino")
        Worker.return_value.start.assert_called_once()

    def test_duplicates_are_not_touched_while_syncing(self, _get_password):
        window = self._window()
        window.worker = MagicMock()
        window.worker.isRunning.return_value = True
        with patch("gui.main_window.DuplicatesWorker") as Worker:
            window.duplicados_panel.scan_btn.click()
        Worker.assert_not_called()
        self.assertIn("descarga", window.duplicados_panel.status_label.text())

    def test_closing_during_a_sync_cancels_and_waits(self, _get_password):
        window = self._window()
        worker = MagicMock()
        worker.isRunning.return_value = True
        window.worker = worker
        event = QtGui.QCloseEvent()
        with patch.object(window, "_confirm_close_during_sync", return_value=True):
            window.closeEvent(event)
        worker.cancel.assert_called_once()
        worker.wait.assert_called_once()
        self.assertTrue(event.isAccepted())

    def test_closing_can_be_aborted_while_syncing(self, _get_password):
        window = self._window()
        worker = MagicMock()
        worker.isRunning.return_value = True
        window.worker = worker
        event = QtGui.QCloseEvent()
        with patch.object(window, "_confirm_close_during_sync", return_value=False):
            window.closeEvent(event)
        worker.cancel.assert_not_called()
        self.assertFalse(event.isAccepted())



@patch("keyring.get_password", return_value=None)
class UserSettingsLocationTest(unittest.TestCase):
    def setUp(self):
        from PyQt6 import QtCore

        self.app = get_app()
        QtCore.QStandardPaths.setTestModeEnabled(True)
        self.addCleanup(QtCore.QStandardPaths.setTestModeEnabled, False)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self.cwd)
        from gui.main_window import user_settings_path

        self.settings = user_settings_path()
        self.settings.unlink(missing_ok=True)
        self.addCleanup(self.settings.unlink, missing_ok=True)

    def test_settings_live_in_the_os_config_folder_not_the_cwd(self, _get_password):
        from gui.main_window import ScrappyGUI

        window = ScrappyGUI()
        window._on_output_path_changed("/tmp/elegida")

        self.assertTrue(self.settings.is_file())
        self.assertFalse(Path(self.tmp.name, "config", "user_settings.json").exists())
        self.assertNotEqual(self.settings.parent.resolve(), Path(self.tmp.name).resolve())
        self.assertEqual(ScrappyGUI()._output_path, "/tmp/elegida")

    def test_legacy_settings_from_the_cwd_are_still_read(self, _get_password):
        from gui.main_window import ScrappyGUI

        legacy = Path(self.tmp.name, "config", "user_settings.json")
        legacy.parent.mkdir()
        legacy.write_text(json.dumps({"last_output_path": "/tmp/vieja"}), encoding="utf-8")

        self.assertEqual(ScrappyGUI()._output_path, "/tmp/vieja")


if __name__ == "__main__":
    unittest.main()


class GoogleSessionTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    def _window(self, stored=None):
        from gui.main_window import ScrappyGUI

        stored = stored or {}
        with patch("keyring.get_password", side_effect=lambda service, key: stored.get((service, key))):
            return ScrappyGUI()

    def test_stored_google_session_is_shown_on_startup(self):
        window = self._window({
            ("scrappy_google", "refresh_token"): "RT",
            ("scrappy_google", "email"): "alumno@ucc.edu.ar",
        })
        self.assertEqual(window._google_refresh_token, "RT")
        self.assertIn("alumno@ucc.edu.ar", window.conexion_panel.google_status_label.text())

    def test_connecting_google_opens_the_consent_page_and_stores_the_session(self):
        window = self._window()
        with patch("gui.main_window.GoogleLoginWorker") as Worker:
            window.conexion_panel.google_btn.click()
        Worker.return_value.start.assert_called_once()
        self.assertEqual(window.conexion_panel.google_btn.text(), "Cancelar")

        with patch.object(QtGui.QDesktopServices, "openUrl") as open_url:
            window._on_google_consent_url("https://accounts.google.com/x")
        open_url.assert_called_once()
        self.assertIn("https://accounts.google.com/x", window.conexion_panel.google_link_label.text())

        with patch("keyring.set_password") as set_password:
            window._on_google_login_finished(True, {"refresh_token": "RT", "email": "a@ucc.edu.ar"}, "")
        set_password.assert_any_call("scrappy_google", "refresh_token", "RT")
        set_password.assert_any_call("scrappy_google", "email", "a@ucc.edu.ar")
        self.assertEqual(window._google_refresh_token, "RT")
        self.assertIn("a@ucc.edu.ar", window.conexion_panel.google_status_label.text())

    def test_failed_google_login_shows_the_error(self):
        window = self._window()
        window._on_google_login_finished(False, {}, "Google rechazó el acceso (access_denied)")
        self.assertIn("rechazó", window.conexion_panel.google_status_label.text())
        self.assertEqual(window._google_refresh_token, "")

    def test_cancelling_google_login_stops_the_worker(self):
        window = self._window()
        with patch("gui.main_window.GoogleLoginWorker") as Worker:
            Worker.return_value.isRunning.return_value = True
            window.conexion_panel.google_btn.click()
            window.conexion_panel.google_btn.click()
        Worker.return_value.cancel.assert_called_once()

    def test_disconnecting_google_forgets_the_session(self):
        window = self._window({
            ("scrappy_google", "refresh_token"): "RT",
            ("scrappy_google", "email"): "alumno@ucc.edu.ar",
        })
        with patch("keyring.delete_password") as delete_password:
            window.conexion_panel.google_btn.click()
        delete_password.assert_any_call("scrappy_google", "refresh_token")
        self.assertEqual(window._google_refresh_token, "")
        self.assertIn("No conectado", window.conexion_panel.google_status_label.text())

    def test_expired_google_session_is_forgotten(self):
        window = self._window({("scrappy_google", "refresh_token"): "RT"})
        with patch("keyring.delete_password"):
            window._on_google_session_expired()
        self.assertEqual(window._google_refresh_token, "")
        self.assertIn("vencida", window.conexion_panel.google_status_label.text())


@patch("keyring.get_password", return_value=None)
class DrivePanelWiringTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    def _window(self):
        from gui.main_window import ScrappyGUI

        window = ScrappyGUI()
        window.config_panel.set_output_path("/tmp/destino")
        return window

    def test_drive_panel_sits_below_materias(self, _get_password):
        from gui.main_window import PANEL_DRIVE, PANEL_MATERIAS

        window = self._window()
        self.assertEqual(PANEL_DRIVE, PANEL_MATERIAS + 1)
        self.assertIs(window.stack.widget(PANEL_DRIVE), window.drive_panel)
        self.assertIn("Drive", window.sidebar._buttons[PANEL_DRIVE].text())

    def test_opening_the_drive_panel_loads_the_saved_state(self, _get_password):
        from gui.main_window import PANEL_DRIVE

        window = self._window()
        with patch("gui.main_window.DriveWorker") as Worker:
            Worker.return_value.isRunning.return_value = False
            window.sidebar.navigate_to(PANEL_DRIVE)
        Worker.assert_called_once_with("state", output_path="/tmp/destino")
        Worker.return_value.start.assert_called_once()

    def test_scanning_needs_a_moodle_connection(self, _get_password):
        window = self._window()
        with patch("gui.main_window.DriveWorker") as Worker:
            window.drive_panel.scan_btn.click()
        Worker.assert_not_called()
        self.assertIn("Conectate", window.drive_panel.status_label.text())

    def test_scanning_uses_the_selected_courses_and_google_session(self, _get_password):
        from gui.models import Materia

        window = self._window()
        materias = [Materia("Sistemas", "https://m/1", "1"), Materia("Álgebra", "https://m/2", "2")]
        window._on_fetch_finished(True, materias, "", "TOKEN")
        window._google_refresh_token = "RT"
        with patch.object(window.materias_panel, "get_selected_materias", return_value=[materias[0]]), \
                patch("gui.main_window.DriveWorker") as Worker:
            Worker.return_value.isRunning.return_value = False
            window.drive_panel.scan_btn.click()
        kwargs = Worker.call_args.kwargs
        self.assertEqual(Worker.call_args.args, ("scan",))
        self.assertEqual(kwargs["materias"], [materias[0]])
        self.assertEqual(kwargs["token"], "TOKEN")
        self.assertEqual(kwargs["google_refresh_token"], "RT")

    def test_scanning_without_a_course_selection_uses_every_course(self, _get_password):
        from gui.models import Materia

        window = self._window()
        materias = [Materia("Sistemas", "https://m/1", "1")]
        window._on_fetch_finished(True, materias, "", "TOKEN")
        with patch.object(window.materias_panel, "get_selected_materias", return_value=[]), \
                patch("gui.main_window.DriveWorker") as Worker:
            Worker.return_value.isRunning.return_value = False
            window.drive_panel.scan_btn.click()
        self.assertEqual(Worker.call_args.kwargs["materias"], materias)

    def test_saving_sends_the_rules_and_marks_the_panel_clean(self, _get_password):
        window = self._window()
        with patch("gui.main_window.DriveWorker") as Worker:
            Worker.return_value.isRunning.return_value = False
            window.drive_panel.save_requested.emit({"R": "include"})
        Worker.assert_called_once_with("save", output_path="/tmp/destino", rules={"R": "include"})
        with patch.object(window.drive_panel, "mark_saved") as mark_saved:
            window._on_drive_saved(True, {"ok": True}, "")
        mark_saved.assert_called_once()

    def test_leaving_the_drive_panel_with_unsaved_changes_asks_first(self, _get_password):
        from gui.main_window import PANEL_DRIVE, PANEL_REGISTRO

        window = self._window()
        with patch("gui.main_window.DriveWorker"):
            window.sidebar.navigate_to(PANEL_DRIVE)
        with patch.object(window.drive_panel, "is_dirty", return_value=True), \
                patch.object(window, "_confirm_leave_drive", return_value=False):
            window.sidebar.navigate_to(PANEL_REGISTRO)
        self.assertEqual(window.stack.currentIndex(), PANEL_DRIVE)
        with patch.object(window.drive_panel, "is_dirty", return_value=True), \
                patch.object(window, "_confirm_leave_drive", return_value=True):
            window.sidebar.navigate_to(PANEL_REGISTRO)
        self.assertEqual(window.stack.currentIndex(), PANEL_REGISTRO)

    def test_sync_passes_the_google_session_and_handles_expiry(self, _get_password):
        window = self._window()
        window._google_refresh_token = "RT"
        with patch("gui.main_window.ScraperWorker") as Worker:
            window._start_scraping([], {})
        self.assertEqual(Worker.call_args.kwargs["google_refresh_token"], "RT")
        Worker.return_value.google_session_expired.connect.assert_called_once_with(window._on_google_session_expired)


class ErrorHookTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    def test_unhandled_errors_are_logged_and_shown_instead_of_aborting(self):
        from gui.main_window import report_unhandled_error

        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "scrappy-error.log"
            try:
                raise ValueError("algo raro")
            except ValueError as exc:
                error = (type(exc), exc, exc.__traceback__)
            with patch.object(QtWidgets.QMessageBox, "critical") as critical:
                report_unhandled_error(log, *error)
            content = log.read_text(encoding="utf-8")
            self.assertIn("ValueError: algo raro", content)
            self.assertIn("Traceback", content)
            critical.assert_called_once()
            self.assertIn(str(log), critical.call_args.args[2])


class RememberCredentialsTest(unittest.TestCase):
    SERVICE = "scrappy_moodle_ucc"

    def setUp(self):
        from PyQt6 import QtCore

        self.app = get_app()
        QtCore.QStandardPaths.setTestModeEnabled(True)
        self.addCleanup(QtCore.QStandardPaths.setTestModeEnabled, False)
        from gui.main_window import user_settings_path

        self.settings = user_settings_path()
        self.settings.unlink(missing_ok=True)
        self.addCleanup(self.settings.unlink, missing_ok=True)

    def _window(self, stored=None):
        from gui.main_window import ScrappyGUI

        stored = stored or {}
        with patch("keyring.get_password", side_effect=lambda service, key: stored.get((service, key))), \
                patch.object(QtCore.QTimer, "singleShot"):
            return ScrappyGUI()

    def _connect(self, window, remember=True):
        from gui.models import Materia

        window._username, window._password = "2502564", "clave"
        window.conexion_panel.set_remember(remember)
        window._on_fetch_finished(True, [Materia("S", "u", "1")], "", "TOKEN")

    def _settings(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def test_remembering_keeps_the_username_in_settings_and_only_the_password_in_the_keyring(self):
        window = self._window()
        with patch("keyring.set_password") as set_password:
            self._connect(window)
        set_password.assert_called_once_with(self.SERVICE, "2502564", "clave")
        self.assertEqual(self._settings()["last_username"], "2502564")

    def test_remembered_user_logs_in_on_start(self):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps({"last_username": "2502564"}), encoding="utf-8")
        window = self._window({(self.SERVICE, "2502564"): "clave"})
        self.assertEqual(window.conexion_panel.get_credentials(), ("2502564", "clave"))
        self.assertTrue(window.conexion_panel.should_remember())

    def test_username_remembered_by_older_versions_in_the_keyring_still_works(self):
        window = self._window({(self.SERVICE, "last_username"): "2502564", (self.SERVICE, "2502564"): "clave"})
        self.assertEqual(window.conexion_panel.get_credentials(), ("2502564", "clave"))

    def test_keyring_failure_is_reported_instead_of_silently_forgetting(self):
        window = self._window()
        with patch("keyring.set_password", side_effect=RuntimeError("acceso denegado")):
            self._connect(window)
        self.assertIn("llavero", window.conexion_panel.status_label.text())

    def test_not_remembering_forgets_both(self):
        window = self._window()
        with patch("keyring.set_password"):
            self._connect(window)
        with patch("keyring.delete_password") as delete_password:
            self._connect(window, remember=False)
        delete_password.assert_any_call(self.SERVICE, "2502564")
        self.assertNotIn("last_username", self._settings())

    def test_changing_the_output_folder_keeps_the_remembered_user(self):
        window = self._window()
        with patch("keyring.set_password"):
            self._connect(window)
        window._on_output_path_changed("/tmp/otra")
        self.assertEqual(self._settings(), {"last_output_path": "/tmp/otra", "last_username": "2502564"})


def test_tests_never_reach_the_real_keychain_or_preferences():
    import keyring
    from conftest import MemoryKeyring
    from PyQt6 import QtCore

    assert isinstance(keyring.get_keyring(), MemoryKeyring)
    location = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppConfigLocation)
    assert "qttest" in location.lower()


def test_forgetting_nothing_does_not_rewrite_settings(tmp_path, monkeypatch):
    app = get_app()  # keep a reference: a collected QApplication aborts Qt
    from gui.main_window import ScrappyGUI, user_settings_path

    monkeypatch.chdir(tmp_path)  # no legacy config/ to migrate
    path = user_settings_path()
    path.unlink(missing_ok=True)
    with patch("keyring.get_password", return_value=None):
        window = ScrappyGUI()
    window._clear_saved_credentials()
    assert not path.exists()
