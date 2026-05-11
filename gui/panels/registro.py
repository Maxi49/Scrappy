from PyQt6 import QtGui, QtWidgets

from gui.theme import BORDER, LOG_BG, LOG_FG, TEXT_SECONDARY


class RegistroPanel(QtWidgets.QWidget):
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
        header.addWidget(title)
        header.addStretch()
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
        scroll.setValue(scroll.maximum())

    def clear(self):
        self.log_view.clear()
