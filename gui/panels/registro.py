from PyQt6 import QtCore, QtGui, QtWidgets

from gui.theme import BORDER, LOG_BG, LOG_FG, TEXT_SECONDARY


class RegistroPanel(QtWidgets.QWidget):
    cancel_requested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Registro de actividad")
        title.setStyleSheet(
            f"font-weight: 600; color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        clear_btn = QtWidgets.QPushButton("Limpiar")
        clear_btn.setObjectName("ghost")
        clear_btn.setFixedHeight(26)
        clear_btn.setStyleSheet(f"""
            QPushButton#ghost {{
                font-size: 11px; padding: 2px 10px;
                border: 1px solid {BORDER}; border-radius: 4px;
                background: transparent; color: {TEXT_SECONDARY};
            }}
            QPushButton#ghost:hover {{ color: #aaaaaa; border-color: #555555; }}
        """)
        clear_btn.clicked.connect(self.clear)
        self.cancel_btn = QtWidgets.QPushButton("Cancelar descarga")
        self.cancel_btn.setObjectName("ghost")
        self.cancel_btn.setFixedHeight(26)
        self.cancel_btn.setStyleSheet(clear_btn.styleSheet())
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        self.cancel_btn.hide()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.cancel_btn)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QtGui.QFont("Menlo", 11))
        self.log_view.setStyleSheet(f"""
            QTextEdit {{
                background: {LOG_BG};
                border: 1px solid {BORDER};
                border-radius: 6px;
                color: {LOG_FG};
                padding: 8px;
            }}
        """)
        layout.addWidget(self.log_view)

    def append(self, text: str):
        if not text:
            return
        self.log_view.append(text)
        scroll = self.log_view.verticalScrollBar()
        if scroll is None:
            return
        scroll.setValue(scroll.maximum())

    def set_running(self, running: bool):
        self.cancel_btn.setText("Cancelar descarga")
        self.cancel_btn.setEnabled(running)
        self.cancel_btn.setVisible(running)

    def set_cancelling(self):
        self.cancel_btn.setText("Cancelando...")
        self.cancel_btn.setEnabled(False)

    def clear(self):
        self.log_view.clear()
