import unittest
from unittest.mock import patch

from PyQt6 import QtWidgets


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


DUPLICATES = [
    {"path": "Materia/U1/apunte_1.pdf", "original": "Materia/U1/apunte.pdf", "size": 2_000_000},
    {"path": "Materia/U1/guia_1.pdf", "original": "Materia/U1/guia.pdf", "size": 500_000},
]


class DuplicadosPanelTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()
        from gui.panels.duplicados import DuplicadosPanel

        self.panel = DuplicadosPanel()

    def test_scan_button_requests_a_scan(self):
        requested = []
        self.panel.scan_requested.connect(lambda: requested.append(True))
        self.panel.scan_btn.click()
        self.assertEqual(requested, [True])

    def test_results_are_listed_and_can_be_removed(self):
        self.panel.show_scan(DUPLICATES, 2_500_000)
        self.assertEqual(self.panel.result_list.count(), 2)
        self.assertTrue(self.panel.remove_btn.isEnabled())
        self.assertIn("2", self.panel.remove_btn.text())

        removed = []
        self.panel.remove_requested.connect(removed.append)
        with patch.object(self.panel, "_confirm_removal", return_value=True):
            self.panel.remove_btn.click()
        self.assertEqual(removed, [["Materia/U1/apunte_1.pdf", "Materia/U1/guia_1.pdf"]])

    def test_removal_needs_confirmation(self):
        self.panel.show_scan(DUPLICATES, 2_500_000)
        removed = []
        self.panel.remove_requested.connect(removed.append)
        with patch.object(self.panel, "_confirm_removal", return_value=False):
            self.panel.remove_btn.click()
        self.assertEqual(removed, [])

    def test_no_duplicates_disables_removal(self):
        self.panel.show_scan([], 0)
        self.assertEqual(self.panel.result_list.count(), 0)
        self.assertFalse(self.panel.remove_btn.isEnabled())
        self.assertIn("No hay", self.panel.status_label.text())

    def test_removal_result_is_summarised_and_list_cleared(self):
        self.panel.show_scan(DUPLICATES, 2_500_000)
        self.panel.show_removal(["Materia/U1/apunte_1.pdf"], [{"path": "x", "reason": "y"}], 2_000_000)
        self.assertEqual(self.panel.result_list.count(), 0)
        self.assertIn("1", self.panel.status_label.text())
        self.assertFalse(self.panel.remove_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()
