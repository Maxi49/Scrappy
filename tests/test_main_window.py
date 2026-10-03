import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PyQt6 import QtGui, QtWidgets


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class MainWindowTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    @patch("keyring.get_password", return_value=None)
    def test_main_window_wires_four_panels(self, _get_password):
        from gui.main_window import ScrappyGUI

        window = ScrappyGUI()

        self.assertEqual(window.stack.count(), 5)
        self.assertEqual(len(window.sidebar._buttons), 5)
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
