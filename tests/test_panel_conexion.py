import unittest
from PyQt6 import QtWidgets

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class ConexionPanelTest(unittest.TestCase):
    def setUp(self): self.app = get_app()

    def test_login_requested_emits_credentials(self):
        from gui.panels.conexion import ConexionPanel
        panel, received = ConexionPanel(), []
        panel.login_requested.connect(lambda u, p: received.append((u, p)))
        panel.username_input.setText("user")
        panel.password_input.setText("pass")
        panel._on_connect_clicked()
        self.assertEqual(received, [("user", "pass")])

    def test_empty_credentials_do_not_emit(self):
        from gui.panels.conexion import ConexionPanel
        panel, received = ConexionPanel(), []
        panel.login_requested.connect(lambda u, p: received.append((u, p)))
        panel._on_connect_clicked()
        self.assertEqual(received, [])

    def test_set_loading_disables_button(self):
        from gui.panels.conexion import ConexionPanel
        panel = ConexionPanel()
        panel.set_loading(True)
        self.assertFalse(panel.connect_btn.isEnabled())
        panel.set_loading(False)
        self.assertTrue(panel.connect_btn.isEnabled())

    def test_set_status_updates_label(self):
        from gui.panels.conexion import ConexionPanel
        panel = ConexionPanel()
        panel.set_status("connected", "Conectado · API ✓")
        self.assertEqual(panel.status_label.text(), "Conectado · API ✓")

if __name__ == "__main__": unittest.main()
