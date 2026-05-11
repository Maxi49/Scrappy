from PyQt6 import QtCore, QtWidgets

from gui.theme import BG_CARD, BORDER, TEXT_PRIMARY, TEXT_SECONDARY


class ConfiguracionPanel(QtWidgets.QWidget):
    output_path_changed = QtCore.pyqtSignal(str)

    def __init__(self, output_path: str, headless: bool, parent=None):
        super().__init__(parent)
        self._output_path = output_path
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        card = QtWidgets.QFrame()
        card.setMaximumWidth(480)
        card.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}"
        )
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(20)

        title = QtWidgets.QLabel("Configuración")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(title)

        card_layout.addWidget(self._make_label("Carpeta de destino"))
        path_row = QtWidgets.QHBoxLayout()
        self._path_display = QtWidgets.QLineEdit(output_path)
        self._path_display.setReadOnly(True)
        self._path_display.setCursorPosition(0)
        browse_btn = QtWidgets.QPushButton("Elegir")
        browse_btn.setObjectName("ghost")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self._path_display)
        path_row.addWidget(browse_btn)
        card_layout.addLayout(path_row)
        card_layout.addWidget(self._make_label("Se guarda automáticamente al cambiar.", size=11))

        self.headless_toggle = QtWidgets.QCheckBox("Ocultar navegador mientras trabaja")
        self.headless_toggle.setChecked(headless)
        card_layout.addWidget(self.headless_toggle)
        card_layout.addWidget(
            self._make_label("Con API activa el navegador no se usa de todas formas.", size=11)
        )
        card_layout.addStretch()

        center = QtWidgets.QHBoxLayout()
        center.addStretch()
        center.addWidget(card)
        center.addStretch()
        layout.addStretch()
        layout.addLayout(center)
        layout.addStretch()

    def _make_label(self, text: str, size: int = 12) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {size}px; background: transparent; border: none;"
        )
        return label

    def _browse(self):
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta", self._output_path
        )
        if selected:
            self.set_output_path(selected)
            self.output_path_changed.emit(selected)

    def get_output_path(self) -> str:
        return self._output_path

    def set_output_path(self, path: str):
        self._output_path = path
        self._path_display.setText(path)
        self._path_display.setCursorPosition(0)

    def get_headless(self) -> bool:
        return self.headless_toggle.isChecked()
