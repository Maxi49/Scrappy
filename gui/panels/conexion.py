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

        h = QtWidgets.QHBoxLayout()
        h.addStretch(); h.addWidget(card); h.addStretch()
        layout.addStretch(); layout.addLayout(h); layout.addStretch()

    def _on_connect_clicked(self):
        u, p = self.username_input.text().strip(), self.password_input.text().strip()
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
        return self.username_input.text().strip(), self.password_input.text().strip()

    def should_remember(self):
        return self.remember_checkbox.isChecked()

    def set_remember(self, value):
        self.remember_checkbox.setChecked(value)
