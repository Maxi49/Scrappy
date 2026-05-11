import unittest
from PyQt6 import QtWidgets

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class SidebarTest(unittest.TestCase):
    def setUp(self): self.app = get_app()

    def test_nav_changed_emits_correct_index(self):
        from gui.sidebar import Sidebar
        s = Sidebar()
        received = []
        s.nav_changed.connect(received.append)
        s.navigate_to(2)
        self.assertEqual(received, [2])

    def test_set_active_checks_correct_button(self):
        from gui.sidebar import Sidebar
        s = Sidebar()
        s.set_active(1)
        self.assertTrue(s._buttons[1].isChecked())
        self.assertFalse(s._buttons[0].isChecked())

    def test_sidebar_has_four_buttons(self):
        from gui.sidebar import Sidebar
        self.assertEqual(len(Sidebar()._buttons), 4)

if __name__ == "__main__": unittest.main()
