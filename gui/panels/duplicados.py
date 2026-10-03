from typing import List

from PyQt6 import QtCore, QtWidgets

from gui.theme import BG_CARD, BG_INPUT, BORDER, ERROR, SUCCESS, TEXT_PRIMARY, TEXT_SECONDARY


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


class DuplicadosPanel(QtWidgets.QWidget):
    """Busca y borra las copias apunte_1.pdf que dejaban las versiones 0.1.x.

    La detección y el borrado los hace el núcleo Go; este panel sólo muestra
    el resultado y pide confirmación.
    """

    scan_requested = QtCore.pyqtSignal()
    remove_requested = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duplicates: List[dict] = []
        self._bytes = 0
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        card = QtWidgets.QFrame()
        card.setMaximumWidth(620)
        card.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}"
        )
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(14)

        title = QtWidgets.QLabel("Archivos duplicados")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY}; background: transparent; border: none;"
        )
        card_layout.addWidget(title)

        intro = self._make_label(
            "¿Tenés copias repetidas como apunte_1.pdf o apunte_2.pdf? Las generaban las "
            "versiones anteriores de Scrappy. Las buscamos en tu carpeta de destino y "
            "sólo borramos las que son idénticas al original."
        )
        intro.setWordWrap(True)
        card_layout.addWidget(intro)

        self.folder_label = self._make_label("", size=11)
        self.folder_label.setWordWrap(True)
        card_layout.addWidget(self.folder_label)

        self.scan_btn = QtWidgets.QPushButton("Buscar duplicados")
        self.scan_btn.setMinimumHeight(34)
        self.scan_btn.clicked.connect(self.scan_requested.emit)
        card_layout.addWidget(self.scan_btn)

        self.status_label = self._make_label("")
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)

        self.result_list = QtWidgets.QListWidget()
        self.result_list.setMinimumHeight(160)
        self.result_list.setStyleSheet(
            f"QListWidget {{ background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 4px; "
            f"color: {TEXT_PRIMARY}; font-size: 12px; }}"
        )
        self.result_list.hide()
        card_layout.addWidget(self.result_list)

        self.remove_btn = QtWidgets.QPushButton("Borrar duplicados")
        self.remove_btn.setObjectName("ghost")
        self.remove_btn.setMinimumHeight(34)
        self.remove_btn.setEnabled(False)
        self.remove_btn.hide()
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        card_layout.addWidget(self.remove_btn)

        center = QtWidgets.QHBoxLayout()
        center.addStretch()
        center.addWidget(card, stretch=1)
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

    def _set_status(self, text: str, color: str = TEXT_SECONDARY):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 12px; background: transparent; border: none;"
        )

    def set_folder(self, path: str):
        self.folder_label.setText(f"Carpeta: {path}")
        self._show_list([])
        self._set_status("")

    def set_busy(self, busy: bool, text: str = ""):
        self.scan_btn.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy and bool(self._duplicates))
        if text:
            self._set_status(text)

    def show_scan(self, duplicates: List[dict], total_bytes: int):
        self.set_busy(False)
        self._bytes = total_bytes
        self._show_list(duplicates)
        if not duplicates:
            self._set_status("No hay duplicados. Tu carpeta está limpia.", SUCCESS)
            return
        self._set_status(
            f"Encontramos {len(duplicates)} copia(s) idéntica(s) que ocupan {format_bytes(total_bytes)}."
        )

    def show_removal(self, removed: List[str], skipped: List[dict], freed_bytes: int):
        self._show_list([])
        self.set_busy(False)
        text = f"Se borraron {len(removed)} archivo(s) y se liberaron {format_bytes(freed_bytes)}."
        if skipped:
            text += f" {len(skipped)} no se tocaron porque cambiaron desde la búsqueda."
        self._set_status(text, SUCCESS)

    def show_error(self, message: str):
        self.set_busy(False)
        self._set_status(message, ERROR)

    def _show_list(self, duplicates: List[dict]):
        self._duplicates = list(duplicates)
        self.result_list.clear()
        for duplicate in self._duplicates:
            item = QtWidgets.QListWidgetItem(duplicate["path"])
            item.setToolTip(f"Igual a {duplicate.get('original', '')}")
            self.result_list.addItem(item)
        has_results = bool(self._duplicates)
        self.result_list.setVisible(has_results)
        self.remove_btn.setVisible(has_results)
        self.remove_btn.setEnabled(has_results)
        self.remove_btn.setText(
            f"Borrar {len(self._duplicates)} duplicado(s) ({format_bytes(self._bytes)})"
            if has_results
            else "Borrar duplicados"
        )

    def _confirm_removal(self) -> bool:
        answer = QtWidgets.QMessageBox.question(
            self,
            "Borrar duplicados",
            f"¿Borrar {len(self._duplicates)} copia(s) idéntica(s)? "
            "Los originales no se tocan.",
        )
        return answer == QtWidgets.QMessageBox.StandardButton.Yes

    def _on_remove_clicked(self):
        if not self._duplicates or not self._confirm_removal():
            return
        self.remove_requested.emit([duplicate["path"] for duplicate in self._duplicates])
