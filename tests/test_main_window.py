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

        self.assertEqual(window.stack.count(), 4)
        self.assertEqual(len(window.sidebar._buttons), 4)
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


if __name__ == "__main__":
    unittest.main()
