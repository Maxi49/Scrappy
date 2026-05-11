import unittest
from PyQt6 import QtWidgets
from scraper.models import Materia


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def make_materias(n=4):
    return [Materia(nombre=f"Materia {i}", url=f"http://x/{i}", id_curso=str(i)) for i in range(n)]


class MateriasPanelTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    def test_populate_updates_counter(self):
        from gui.panels.materias import MateriasPanel
        panel = MateriasPanel()
        panel.populate(make_materias(6))
        self.assertIn("6", panel._counter_label.text())

    def test_get_selected_materias_returns_all_by_default(self):
        from gui.panels.materias import MateriasPanel
        panel = MateriasPanel()
        panel.populate(make_materias(3))
        self.assertEqual(len(panel.get_selected_materias()), 3)

    def test_get_mode_returns_dict(self):
        from gui.panels.materias import MateriasPanel
        mode = MateriasPanel().get_mode()
        self.assertIn("mode", mode)
        self.assertIn("scan_existing", mode)

    def test_set_running_disables_button(self):
        from gui.panels.materias import MateriasPanel
        panel = MateriasPanel()
        panel.set_running(True)
        self.assertFalse(panel.start_btn.isEnabled())
        panel.set_running(False)
        self.assertTrue(panel.start_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()
