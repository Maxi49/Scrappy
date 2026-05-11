import unittest
from unittest.mock import patch

from PyQt6 import QtWidgets


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


if __name__ == "__main__":
    unittest.main()
