from datetime import datetime
from typing import Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from gui.panels.duplicados import format_bytes
from gui.theme import BG_CARD, BORDER, ERROR, TEXT_PRIMARY, TEXT_SECONDARY

INCLUDE = "include"
EXCLUDE = "exclude"

ROLE_ID = QtCore.Qt.ItemDataRole.UserRole
ROLE_BASE = QtCore.Qt.ItemDataRole.UserRole + 1  # included before any edit
ROLE_SIZE = QtCore.Qt.ItemDataRole.UserRole + 2
ROLE_ROOT = QtCore.Qt.ItemDataRole.UserRole + 3

Checked = QtCore.Qt.CheckState.Checked
Unchecked = QtCore.Qt.CheckState.Unchecked


def nearest_rule(rules: Dict[str, str], chain) -> bool:
    for drive_id in reversed(chain):
        if drive_id in rules:
            return rules[drive_id] == INCLUDE
    return False


class DrivePanel(QtWidgets.QWidget):
    """Árbol de lo que hay detrás de cada link de Drive, para elegir qué bajar.

    El core lista Drive y guarda las reglas; este panel sólo las muestra como
    checkboxes y arma las reglas mínimas al guardar.
    """

    scan_requested = QtCore.pyqtSignal()
    save_requested = QtCore.pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: Dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._dirty = False
        self._loading = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 24)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("Google Drive")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Nombre", "Tamaño"])
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px; }}"
        )
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, stretch=1)

        footer = QtWidgets.QHBoxLayout()
        self.summary_label = QtWidgets.QLabel()
        self.summary_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        footer.addWidget(self.summary_label, stretch=1)
        self.scan_btn = QtWidgets.QPushButton("Analizar Drive")
        self.scan_btn.clicked.connect(self.scan_requested.emit)
        footer.addWidget(self.scan_btn)
        self.save_btn = QtWidgets.QPushButton("Guardar selección")
        self.save_btn.clicked.connect(lambda: self.save_requested.emit(self.rules()))
        footer.addWidget(self.save_btn)
        layout.addLayout(footer)

        self.show_tree(None, None)

    # ----- carga -----

    def show_tree(self, tree: Optional[dict], rules: Optional[dict]):
        rules = dict(rules or {})
        roots = list((tree or {}).get("roots") or [])
        self._loading = True
        self.tree.blockSignals(True)
        self.tree.clear()
        self._items.clear()
        courses: Dict[str, QtWidgets.QTreeWidgetItem] = {}
        leaves = []
        for root in roots:
            course_name = str(root.get("materia") or "Materia")
            course = courses.get(course_name)
            if course is None:
                course = QtWidgets.QTreeWidgetItem(self.tree, [course_name, ""])
                course.setFlags(course.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsAutoTristate)
                font = course.font(0)
                font.setBold(True)
                course.setFont(0, font)
                courses[course_name] = course
            leaves.extend(self._add_root(course, root, rules))
        for item, checked in leaves:
            item.setCheckState(0, Checked if checked else Unchecked)
        for course in courses.values():
            self._refresh_sizes(course)
        self.tree.expandToDepth(0)
        self.tree.blockSignals(False)
        self._loading = False
        self._dirty = False

        scanned = str((tree or {}).get("scanned_at") or "")
        if not roots:
            self.status_label.setText(
                "Todavía no hay links de Drive analizados. Elegí las materias en Materias y tocá «Analizar Drive»."
            )
        else:
            self.status_label.setText(
                f"Analizado el {self._format_time(scanned)}. Marcá lo que querés descargar y tocá «Guardar selección». "
                "Lo nuevo dentro de una carpeta marcada se descarga solo."
            )
        self._update_summary()

    def _add_root(self, parent, root: dict, rules: dict):
        node = root.get("node") or {}
        drive_id = str(root.get("id") or node.get("id") or "")
        label = str(root.get("link_name") or node.get("name") or "Drive")
        if root.get("modulo"):
            label += f" — {root['modulo']}"
        if root.get("new"):
            label += "  · nuevo"
        item = self._make_item(parent, drive_id, label, node, [drive_id], rules)
        item.setData(0, ROLE_ROOT, True)
        error = str(root.get("error") or "")
        if error:
            item.setToolTip(0, error)
            item.setText(1, error)
            for column in (0, 1):
                item.setForeground(column, QtGui.QBrush(QtGui.QColor(TEXT_SECONDARY)))
            item.setForeground(1, QtGui.QBrush(QtGui.QColor(ERROR)))
        chain = [drive_id] if node.get("id", drive_id) == drive_id else [drive_id, str(node.get("id"))]
        return self._add_children(item, node, chain, rules) or [(item, nearest_rule(rules, chain))]

    def _make_item(self, parent, drive_id, label, node, chain, rules):
        item = QtWidgets.QTreeWidgetItem(parent, [label, ""])
        flags = item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
        if node.get("children"):
            flags |= QtCore.Qt.ItemFlag.ItemIsAutoTristate
        item.setFlags(flags)
        item.setData(0, ROLE_ID, drive_id)
        item.setData(0, ROLE_BASE, nearest_rule(rules, chain))
        native = str(node.get("mime") or "").startswith("application/vnd.google-apps.")
        size = int(node.get("size") or 0)
        item.setData(0, ROLE_SIZE, size)
        if node.get("kind") != "folder":
            item.setText(1, "—" if native or not size else format_bytes(size))
        self._items[drive_id] = item
        return item

    def _add_children(self, item, node: dict, chain, rules):
        leaves = []
        for child in node.get("children") or []:
            child_id = str(child.get("id") or "")
            child_chain = chain + [child_id]
            child_item = self._make_item(item, child_id, str(child.get("name") or ""), child, child_chain, rules)
            nested = self._add_children(child_item, child, child_chain, rules)
            leaves.extend(nested or [(child_item, nearest_rule(rules, child_chain))])
        return leaves

    # ----- estado -----

    def item_for(self, drive_id: str) -> Optional[QtWidgets.QTreeWidgetItem]:
        return self._items.get(drive_id)

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_saved(self):
        self._dirty = False

    def set_busy(self, busy: bool, text: str = ""):
        self.scan_btn.setEnabled(not busy)
        self.save_btn.setEnabled(not busy)
        self.tree.setEnabled(not busy)
        if text:
            self.status_label.setText(text)

    def show_message(self, text: str):
        self.status_label.setText(text)

    def rules(self) -> Dict[str, str]:
        rules: Dict[str, str] = {}
        for index in range(self.tree.topLevelItemCount()):
            course = self.tree.topLevelItem(index)
            for child in range(course.childCount()):
                self._emit_rules(course.child(child), None, rules)
        return rules

    def _emit_rules(self, item, inherited, rules):
        state = item.checkState(0)
        if state == Checked:
            desired = INCLUDE
        elif state == Unchecked:
            desired = EXCLUDE
        else:
            # A partly selected folder keeps the rule it had, so files the
            # professor adds later keep following it.
            desired = INCLUDE if item.data(0, ROLE_BASE) else EXCLUDE
        if inherited is None or desired != inherited:
            rules[item.data(0, ROLE_ID)] = desired
        if state == QtCore.Qt.CheckState.PartiallyChecked:
            for child in range(item.childCount()):
                self._emit_rules(item.child(child), desired, rules)

    def _on_item_changed(self, item, column):
        if self._loading or column != 0:
            return
        # A folder the student fully (un)checks remembers that choice, so
        # unticking one file later keeps the folder's own rule.
        self._loading = True
        current = item
        while current is not None:
            state = current.checkState(0)
            if state != QtCore.Qt.CheckState.PartiallyChecked:
                current.setData(0, ROLE_BASE, state == Checked)
            current = current.parent()
        self._loading = False
        self._dirty = True
        self._update_summary()

    def _refresh_sizes(self, item) -> int:
        if item.childCount() == 0:
            return int(item.data(0, ROLE_SIZE) or 0)
        total = sum(self._refresh_sizes(item.child(index)) for index in range(item.childCount()))
        if not item.text(1):
            item.setText(1, format_bytes(total) if total else "—")
        return total

    def _update_summary(self):
        selected = total = 0
        for item in self._items.values():
            if item.childCount():
                continue
            size = int(item.data(0, ROLE_SIZE) or 0)
            total += size
            if item.checkState(0) == Checked:
                selected += size
        self.summary_label.setText(f"Seleccionado: {format_bytes(selected)} de {format_bytes(total)}")

    @staticmethod
    def _format_time(value: str) -> str:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
            return moment.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return value or "—"
