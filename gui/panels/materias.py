from typing import List

from PyQt6 import QtCore, QtGui, QtWidgets

from gui.theme import BG_INPUT, BG_ITEM_ACTIVE, BG_ITEM_HOVER, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT
from scraper.models import Materia

CARD_MIN_WIDTH = 220
CARD_HEIGHT = 90
GRID_GAP = 16
GRID_RIGHT_MARGIN = 8


class MateriaCard(QtWidgets.QFrame):
    toggled = QtCore.pyqtSignal(object, bool)

    def __init__(self, materia: Materia, parent=None):
        super().__init__(parent)
        self.materia = materia
        self._selected = True
        self.setMinimumSize(CARD_MIN_WIDTH, CARD_HEIGHT)
        self.setFixedHeight(CARD_HEIGHT)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(0)

        self._check = QtWidgets.QLabel("✓", self)
        self._check.setFixedSize(22, 22)
        self._check.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._check.setStyleSheet(
            f"color: {ACCENT}; font-size: 16px; font-weight: 700; "
            "background: transparent; border: none;"
        )

        self._name = QtWidgets.QLabel(materia.nombre)
        self._name.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._name.setWordWrap(True)
        self._name.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;"
        )
        layout.addStretch()
        layout.addWidget(self._name, stretch=1)
        layout.addStretch()

        self._update_style()

    def mousePressEvent(self, a0):
        if a0 is None:
            return
        if a0.button() == QtCore.Qt.MouseButton.LeftButton:
            self.set_selected(not self._selected)
            a0.accept()
            return
        super().mousePressEvent(a0)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self._check.move(self.width() - self._check.width() - 12, 10)

    def set_selected(self, selected: bool):
        selected = bool(selected)
        if self._selected == selected:
            return
        self._selected = selected
        self._update_style()
        self.toggled.emit(self.materia, selected)

    def is_selected(self) -> bool:
        return self._selected

    def _update_style(self):
        font = self._name.font()
        font.setStrikeOut(not self._selected)
        self._name.setFont(font)

        if self._selected:
            self.setStyleSheet(
                f"QFrame {{ background: {BG_ITEM_ACTIVE}; border: 1px solid {ACCENT}; border-radius: 6px; }}"
                f"QFrame:hover {{ background: {BG_ITEM_HOVER}; }}"
            )
            self._check.setVisible(True)
            self._name.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;"
            )
            return

        self.setStyleSheet(
            f"QFrame {{ background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 6px; }}"
            f"QFrame:hover {{ background: {BG_ITEM_HOVER}; }}"
        )
        self._check.setVisible(False)
        self._name.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;"
        )


class MateriasGrid(QtWidgets.QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")

        self._container = QtWidgets.QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._grid = QtWidgets.QGridLayout(self._container)
        self._grid.setSpacing(GRID_GAP)
        self._grid.setContentsMargins(0, 0, GRID_RIGHT_MARGIN, 0)
        self._grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self.setWidget(self._container)
        self._cards: List[MateriaCard] = []

    def populate(self, materias: List[Materia]):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        self._cards.clear()
        for index, materia in enumerate(materias):
            card = MateriaCard(materia)
            self._cards.append(card)
            self._grid.addWidget(card, index // 2, index % 2)

        self._grid.setRowStretch((len(materias) // 2) + 1, 1)

    def get_selected(self) -> List[Materia]:
        return [card.materia for card in self._cards if card.is_selected()]

    def select_all(self):
        for card in self._cards:
            card.set_selected(True)

    def select_none(self):
        for card in self._cards:
            card.set_selected(False)

    def count(self) -> int:
        return len(self._cards)

    def selected_count(self) -> int:
        return sum(1 for card in self._cards if card.is_selected())


class MateriasPanel(QtWidgets.QWidget):
    start_requested = QtCore.pyqtSignal(list, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Materias")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY}; background: transparent;"
        )
        self._counter_label = QtWidgets.QLabel("")
        self._counter_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; background: transparent;"
        )
        header.addWidget(title)
        header.addWidget(self._counter_label)
        header.addStretch()

        all_link = self._make_link("Todas")
        all_link.linkActivated.connect(lambda _: self._select_all())
        none_link = self._make_link("Ninguna")
        none_link.linkActivated.connect(lambda _: self._select_none())
        sep = QtWidgets.QLabel("·")
        sep.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        header.addWidget(all_link)
        header.addWidget(sep)
        header.addWidget(none_link)
        layout.addLayout(header)

        self._grid = MateriasGrid()
        layout.addWidget(self._grid, stretch=1)

        mode_lbl = QtWidgets.QLabel("Modo de descarga")
        mode_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(mode_lbl)

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("Actualizar (buscar cambios en módulos)", ("update", True))
        self.mode_combo.addItem("Solo módulos nuevos", ("update", False))
        self.mode_combo.addItem("Forzar descarga completa", ("full", True))
        layout.addWidget(self.mode_combo)

        self._progress_label = QtWidgets.QLabel("")
        self._progress_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedHeight(6)
        self._progress_label.setVisible(False)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_label)
        layout.addWidget(self._progress_bar)

        self.start_btn = QtWidgets.QPushButton("Comenzar descarga")
        self.start_btn.setMinimumHeight(38)
        self.start_btn.clicked.connect(self._on_start_clicked)
        layout.addWidget(self.start_btn)

    def _make_link(self, text: str) -> QtWidgets.QLabel:
        link = QtWidgets.QLabel(f'<a href="{text}" style="color:{ACCENT};text-decoration:none;">{text}</a>')
        link.setOpenExternalLinks(False)
        link.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        return link

    def populate(self, materias: List[Materia]):
        self._grid.populate(materias)
        self._counter_label.setText(f"· {len(materias)} disponibles")

    def get_selected_materias(self) -> List[Materia]:
        return self._grid.get_selected()

    def get_mode(self) -> dict:
        data = self.mode_combo.currentData()
        if not data:
            return {"mode": "update", "scan_existing": True}
        return {"mode": data[0], "scan_existing": data[1]}

    def set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self._progress_label.setVisible(running)
        self._progress_bar.setVisible(running)

    def update_progress(self, text: str):
        self._progress_label.setText(text)

    def _on_start_clicked(self):
        materias = self.get_selected_materias()
        if not materias:
            return
        mode = self.get_mode()
        self.start_requested.emit(materias, {materia.nombre: mode for materia in materias})

    def _select_all(self):
        self._grid.select_all()

    def _select_none(self):
        self._grid.select_none()
