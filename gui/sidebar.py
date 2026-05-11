from PyQt6 import QtCore, QtGui, QtWidgets
from gui.theme import BG_SIDEBAR, BG_ITEM_ACTIVE, BG_ITEM_HOVER, ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, BORDER

_NAV_ITEMS = [("⚡", "Conexión"), ("⊞", "Materias"), ("⚙", "Configuración"), ("≡", "Registro")]


class SidebarButton(QtWidgets.QPushButton):
    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self.setText(f"  {icon}   {label}")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(44)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                border-left: 2px solid transparent; border-radius: 0;
                color: {TEXT_SECONDARY}; font-size: 13px;
                text-align: left; padding-left: 12px;
            }}
            QPushButton:hover {{ background: {BG_ITEM_HOVER}; color: {TEXT_PRIMARY}; }}
            QPushButton:checked {{
                background: {BG_ITEM_ACTIVE};
                border-left: 2px solid {ACCENT};
                color: {TEXT_PRIMARY}; font-weight: 600;
            }}
        """)


class Sidebar(QtWidgets.QFrame):
    nav_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self.setStyleSheet(f"QFrame {{ background: {BG_SIDEBAR}; border-right: 1px solid {BORDER}; }}")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QtWidgets.QLabel("  ◈  Scrappy")
        header.setStyleSheet(f"""
            color: {TEXT_PRIMARY}; font-size: 15px; font-weight: 700;
            padding: 20px 12px 16px 12px;
            border-bottom: 1px solid {BORDER}; background: transparent;
        """)
        layout.addWidget(header)

        self._buttons: list[SidebarButton] = []
        for i, (icon, label) in enumerate(_NAV_ITEMS):
            btn = SidebarButton(icon, label)
            btn.clicked.connect(lambda checked, idx=i: self._on_click(idx))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()
        self.set_active(0)

    def _on_click(self, index):
        self.set_active(index)
        self.nav_changed.emit(index)

    def navigate_to(self, index):
        self.set_active(index)
        self.nav_changed.emit(index)

    def set_active(self, index):
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
