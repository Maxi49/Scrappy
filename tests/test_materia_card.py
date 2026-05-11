import unittest
from PyQt6 import QtCore, QtWidgets
from scraper.models import Materia


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class MateriaCardTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()
        self.m = Materia(nombre="Fisica I", url="http://x/1", id_curso="1")

    def test_card_starts_selected(self):
        from gui.panels.materias import MateriaCard
        self.assertTrue(MateriaCard(self.m).is_selected())

    def test_set_selected_false_deselects(self):
        from gui.panels.materias import MateriaCard
        card = MateriaCard(self.m)
        card.set_selected(False)
        self.assertFalse(card.is_selected())

    def test_toggled_signal_emits(self):
        from gui.panels.materias import MateriaCard
        card, received = MateriaCard(self.m), []
        card.toggled.connect(lambda m, s: received.append((m, s)))
        card.set_selected(False)
        self.assertEqual(received, [(self.m, False)])

    def test_name_is_centered(self):
        from gui.panels.materias import MateriaCard
        card = MateriaCard(self.m)
        alignment = card._name.alignment()
        self.assertTrue(alignment & QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.assertTrue(alignment & QtCore.Qt.AlignmentFlag.AlignVCenter)

    def test_check_toggle_does_not_move_name(self):
        from gui.panels.materias import MateriaCard
        card = MateriaCard(self.m)
        card.resize(420, 90)
        card.show()
        self.app.processEvents()
        before = card._name.geometry()
        card.set_selected(False)
        self.app.processEvents()
        self.assertEqual(card._name.geometry(), before)

    def test_grid_populate_creates_cards(self):
        from gui.panels.materias import MateriasGrid
        grid = MateriasGrid()
        grid.populate([Materia(nombre=f"M{i}", url=f"http://x/{i}", id_curso=str(i)) for i in range(4)])
        self.assertEqual(len(grid._cards), 4)

    def test_grid_get_selected_excludes_deselected(self):
        from gui.panels.materias import MateriasGrid
        grid = MateriasGrid()
        ms = [Materia(nombre=f"M{i}", url=f"http://x/{i}", id_curso=str(i)) for i in range(3)]
        grid.populate(ms)
        grid._cards[1].set_selected(False)
        self.assertEqual(len(grid.get_selected()), 2)
        self.assertNotIn(ms[1], grid.get_selected())

    def test_grid_cards_expand_to_use_available_width(self):
        from gui.panels.materias import MateriaCard, MateriasGrid
        grid = MateriasGrid()
        card = MateriaCard(self.m)
        self.assertGreater(grid._container.maximumWidth(), 1000)
        self.assertEqual(card.sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Policy.Expanding)
        self.assertGreater(card.maximumWidth(), 1000)


if __name__ == "__main__":
    unittest.main()
