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

    def test_password_is_sent_exactly_as_typed(self):
        from gui.panels.conexion import ConexionPanel
        panel, received = ConexionPanel(), []
        panel.login_requested.connect(lambda u, p: received.append((u, p)))
        panel.username_input.setText("  user ")
        panel.password_input.setText(" clave con espacios ")
        panel._on_connect_clicked()
        self.assertEqual(received, [("user", " clave con espacios ")])
        self.assertEqual(panel.get_credentials(), ("user", " clave con espacios "))

    def test_blank_password_does_not_emit(self):
        from gui.panels.conexion import ConexionPanel
        panel, received = ConexionPanel(), []
        panel.login_requested.connect(lambda u, p: received.append((u, p)))
        panel.username_input.setText("user")
        panel.password_input.setText("")
        panel._on_connect_clicked()
        self.assertEqual(received, [])

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

    def test_google_block_starts_disconnected_and_requests_login(self):
        from gui.panels.conexion import ConexionPanel
        panel, received = ConexionPanel(), []
        panel.google_connect_requested.connect(lambda: received.append("connect"))
        self.assertIn("No conectado", panel.google_status_label.text())
        self.assertEqual(panel.google_btn.text(), "Conectar con Google")
        panel.google_btn.click()
        self.assertEqual(received, ["connect"])

    def test_google_waiting_shows_consent_link_and_cancels(self):
        from gui.panels.conexion import ConexionPanel
        panel, received = ConexionPanel(), []
        panel.google_cancel_requested.connect(lambda: received.append("cancel"))
        panel.set_google_state("waiting")
        panel.set_google_consent_url("https://accounts.google.com/x?a=1&b=2")
        self.assertEqual(panel.google_btn.text(), "Cancelar")
        self.assertIn("https://accounts.google.com/x?a=1&amp;b=2", panel.google_link_label.text())
        self.assertFalse(panel.google_link_label.isHidden())
        panel.google_btn.click()
        self.assertEqual(received, ["cancel"])

    def test_google_connected_shows_email_and_disconnects(self):
        from gui.panels.conexion import ConexionPanel
        panel, received = ConexionPanel(), []
        panel.google_disconnect_requested.connect(lambda: received.append("disconnect"))
        panel.set_google_state("connected", "alumno@ucc.edu.ar")
        self.assertIn("alumno@ucc.edu.ar", panel.google_status_label.text())
        self.assertTrue(panel.google_link_label.isHidden())
        self.assertEqual(panel.google_btn.text(), "Desconectar")
        panel.google_btn.click()
        self.assertEqual(received, ["disconnect"])

    def test_google_expired_session_offers_reconnecting(self):
        from gui.panels.conexion import ConexionPanel
        panel, received = ConexionPanel(), []
        panel.google_connect_requested.connect(lambda: received.append("connect"))
        panel.set_google_state("expired")
        self.assertIn("vencida", panel.google_status_label.text())
        panel.google_btn.click()
        self.assertEqual(received, ["connect"])

    def test_google_error_shows_the_message(self):
        from gui.panels.conexion import ConexionPanel
        panel = ConexionPanel()
        panel.set_google_state("error", message="el administrador bloquea esta aplicación")
        self.assertIn("administrador", panel.google_status_label.text())
        self.assertEqual(panel.google_btn.text(), "Conectar con Google")

if __name__ == "__main__": unittest.main()
