import unittest
from PyQt6 import QtWidgets


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class ConfiguracionPanelTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    def test_get_output_path_returns_initial_value(self):
        from gui.panels.configuracion import ConfiguracionPanel
        self.assertEqual(ConfiguracionPanel("/tmp/test", True).get_output_path(), "/tmp/test")

    def test_get_headless_reflects_checkbox(self):
        from gui.panels.configuracion import ConfiguracionPanel
        panel = ConfiguracionPanel("/tmp", True)
        self.assertTrue(panel.get_headless())
        panel.headless_toggle.setChecked(False)
        self.assertFalse(panel.get_headless())

    def test_set_output_path_updates_display(self):
        from gui.panels.configuracion import ConfiguracionPanel
        panel = ConfiguracionPanel("/tmp", False)
        panel.set_output_path("/new/path")
        self.assertEqual(panel.get_output_path(), "/new/path")


if __name__ == "__main__":
    unittest.main()
