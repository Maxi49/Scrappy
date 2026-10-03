import html

from PyQt6 import QtCore, QtWidgets
from gui.theme import BG_CARD, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT, SUCCESS, ERROR

_DOT_COLORS = {"disconnected": TEXT_SECONDARY, "connecting": ACCENT, "connected": SUCCESS, "error": ERROR}


class StatusDot(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self.set_state("disconnected")

    def set_state(self, state):
        color = _DOT_COLORS.get(state, TEXT_SECONDARY)
        self.setStyleSheet(f"background: {color}; border-radius: 5px; border: none;")


class ConexionPanel(QtWidgets.QWidget):
    login_requested = QtCore.pyqtSignal(str, str)
    google_connect_requested = QtCore.pyqtSignal()
    google_cancel_requested = QtCore.pyqtSignal()
    google_disconnect_requested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.username_input = QtWidgets.QLineEdit()
        self.password_input = QtWidgets.QLineEdit()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        card = QtWidgets.QFrame()
        card.setStyleSheet(f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}")
        card.setMaximumWidth(400)
        cl = QtWidgets.QVBoxLayout(card)
        cl.setContentsMargins(32, 32, 32, 32)
        cl.setSpacing(16)

        title = QtWidgets.QLabel("Conexión a Moodle UCC")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY}; background: transparent; border: none;")
        cl.addWidget(title)

        for lbl_text, inp, pw in [
            ("Usuario UCC", self.username_input, False),
            ("Contraseña", self.password_input, True),
        ]:
            lbl = QtWidgets.QLabel(lbl_text)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
            if pw:
                inp.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            cl.addWidget(lbl)
            cl.addWidget(inp)

        self.remember_checkbox = QtWidgets.QCheckBox("Recordar en este dispositivo")
        cl.addWidget(self.remember_checkbox)
        cl.addSpacing(8)

        self.connect_btn = QtWidgets.QPushButton("Conectar")
        self.connect_btn.setMinimumHeight(38)
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        cl.addWidget(self.connect_btn)

        row = QtWidgets.QHBoxLayout()
        self._dot = StatusDot()
        self.status_label = QtWidgets.QLabel("Desconectado")
        self.status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
        row.addWidget(self._dot, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.status_label, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        row.addStretch()
        cl.addLayout(row)

        google_card = self._build_google_card()

        h = QtWidgets.QHBoxLayout()
        h.addStretch(); h.addWidget(card); h.addStretch()
        g = QtWidgets.QHBoxLayout()
        g.addStretch(); g.addWidget(google_card); g.addStretch()
        layout.addStretch(); layout.addLayout(h); layout.addSpacing(16); layout.addLayout(g); layout.addStretch()
        self.set_google_state("disconnected")

    def _build_google_card(self):
        card = QtWidgets.QFrame()
        card.setStyleSheet(f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}")
        card.setMaximumWidth(400)
        cl = QtWidgets.QVBoxLayout(card)
        cl.setContentsMargins(32, 20, 32, 20)
        cl.setSpacing(10)

        title = QtWidgets.QLabel("Google Drive")
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {TEXT_PRIMARY}; background: transparent; border: none;")
        cl.addWidget(title)

        row = QtWidgets.QHBoxLayout()
        self._google_dot = StatusDot()
        self.google_status_label = QtWidgets.QLabel()
        self.google_status_label.setWordWrap(True)
        self.google_status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
        row.addWidget(self._google_dot, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.google_status_label, stretch=1)
        cl.addLayout(row)

        self.google_link_label = QtWidgets.QLabel()
        self.google_link_label.setWordWrap(True)
        self.google_link_label.setOpenExternalLinks(True)
        self.google_link_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        self.google_link_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")
        self.google_link_label.hide()
        cl.addWidget(self.google_link_label)

        self.google_btn = QtWidgets.QPushButton()
        self.google_btn.setMinimumHeight(32)
        self.google_btn.clicked.connect(self._on_google_clicked)
        cl.addWidget(self.google_btn)
        return card

    def _on_google_clicked(self):
        if self._google_state == "waiting":
            self.google_cancel_requested.emit()
        elif self._google_state == "connected":
            self.google_disconnect_requested.emit()
        else:
            self.google_connect_requested.emit()

    def set_google_state(self, state, email="", message=""):
        """state: disconnected, waiting, connected, expired o error."""
        self._google_state = state
        text, dot, button = {
            "disconnected": ("No conectado. Hace falta solo para carpetas privadas de la UCC.", "disconnected", "Conectar con Google"),
            "waiting": ("Esperando la autorización en el navegador...", "connecting", "Cancelar"),
            "connected": (f"Conectado como {email}" if email else "Conectado", "connected", "Desconectar"),
            "expired": ("Sesión vencida. Volvé a conectar Google.", "error", "Conectar con Google"),
            "error": (message or "No se pudo conectar Google.", "error", "Conectar con Google"),
        }[state]
        self.google_status_label.setText(text)
        self._google_dot.set_state(dot)
        self.google_btn.setText(button)
        if state != "waiting":
            self.google_link_label.hide()

    def set_google_consent_url(self, url):
        safe = html.escape(url, quote=True)
        self.google_link_label.setText(
            f'Si no se abrió el navegador, <a href="{safe}" style="color:{ACCENT};">abrí este link</a>.<br>{safe}'
        )
        self.google_link_label.show()

    def _on_connect_clicked(self):
        u, p = self.username_input.text().strip(), self.password_input.text()
        if u and p:
            self.login_requested.emit(u, p)

    def set_loading(self, loading):
        for w in (self.connect_btn, self.username_input, self.password_input, self.remember_checkbox):
            w.setEnabled(not loading)
        self._dot.set_state("connecting" if loading else "disconnected")
        self.status_label.setText("Conectando..." if loading else "Desconectado")

    def set_status(self, state, text):
        self._dot.set_state(state)
        self.status_label.setText(text)

    def set_credentials(self, username, password):
        self.username_input.setText(username)
        self.password_input.setText(password)

    def get_credentials(self):
        return self.username_input.text().strip(), self.password_input.text()

    def should_remember(self):
        return self.remember_checkbox.isChecked()

    def set_remember(self, value):
        self.remember_checkbox.setChecked(value)
