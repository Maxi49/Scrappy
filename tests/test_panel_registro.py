import unittest
from PyQt6 import QtWidgets


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class RegistroPanelTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    def test_append_adds_text(self):
        from gui.panels.registro import RegistroPanel
        panel = RegistroPanel()
        panel.append("hola mundo")
        self.assertIn("hola mundo", panel.log_view.toPlainText())

    def test_clear_empties_log(self):
        from gui.panels.registro import RegistroPanel
        panel = RegistroPanel()
        panel.append("linea 1")
        panel.clear()
        self.assertEqual(panel.log_view.toPlainText().strip(), "")

    def test_empty_text_not_appended(self):
        from gui.panels.registro import RegistroPanel
        panel = RegistroPanel()
        panel.append("")
        self.assertEqual(panel.log_view.toPlainText().strip(), "")


if __name__ == "__main__":
    unittest.main()
