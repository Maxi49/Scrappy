# UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rediseñar la GUI de Scrappy con layout de sidebar + paneles, paleta VS Code/macOS, y cards para la selección de materias.

**Architecture:** Se convierte `gui.py` (monolítico) en un paquete `gui/` con archivos por responsabilidad: `theme.py` para la paleta, `workers.py` para los QThreads, `sidebar.py` para la navegación, un archivo por panel en `gui/panels/`, y `main_window.py` como coordinador. `main.py` no se toca — `gui/__init__.py` exporta `ScrappyGUI` y `main` manteniendo la interfaz pública.

**Tech Stack:** PyQt6, keyring, scraper workers existentes (sin cambios)

---

## File Map

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `gui/__init__.py` | Crear | Exporta `ScrappyGUI`, `main` |
| `gui/theme.py` | Crear | Constantes de color + stylesheet global |
| `gui/workers.py` | Crear | `ScraperWorker`, `FetchMateriasWorker` (movidos de gui.py) |
| `gui/sidebar.py` | Crear | `SidebarButton`, `Sidebar` |
| `gui/panels/__init__.py` | Crear | Vacío |
| `gui/panels/conexion.py` | Crear | `StatusDot`, `ConexionPanel` |
| `gui/panels/materias.py` | Crear | `MateriaCard`, `MateriasGrid`, `MateriasPanel` |
| `gui/panels/configuracion.py` | Crear | `ConfiguracionPanel` |
| `gui/panels/registro.py` | Crear | `RegistroPanel` |
| `gui/main_window.py` | Crear | `ScrappyGUI` — coordina todo |
| `tests/test_ui_warnings.py` | Modificar | Actualizar al nuevo API |
| `gui.py` | Eliminar | Reemplazado por el paquete `gui/` |

---

## Task 1: Skeleton del paquete + theme.py

**Files:**
- Create: `gui/__init__.py`
- Create: `gui/theme.py`
- Create: `gui/panels/__init__.py`
- Test: `tests/test_theme.py`

- [ ] **Step 1: Crear los directorios y archivos vacíos**

```bash
mkdir -p gui/panels
touch gui/__init__.py gui/panels/__init__.py
```

- [ ] **Step 2: Escribir el test**

Crear `tests/test_theme.py`:

```python
import re, unittest

class ThemeTest(unittest.TestCase):
    def test_color_constants_are_valid_hex(self):
        from gui.theme import (
            BG_APP, BG_SIDEBAR, BG_CARD, BG_INPUT, BG_ITEM_ACTIVE, BG_ITEM_HOVER,
            BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT, SUCCESS, ERROR, LOG_BG, LOG_FG,
        )
        hex_re = re.compile(r'''#[0-9a-fA-F]{6}''')
        for c in [BG_APP, BG_SIDEBAR, BG_CARD, BG_INPUT, BG_ITEM_ACTIVE, BG_ITEM_HOVER,
                  BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT, SUCCESS, ERROR, LOG_BG, LOG_FG]:
            self.assertRegex(c, hex_re, f"Invalid hex color: {c}")

    def test_stylesheet_is_nonempty_string(self):
        from gui.theme import GLOBAL_STYLESHEET
        self.assertIsInstance(GLOBAL_STYLESHEET, str)
        self.assertGreater(len(GLOBAL_STYLESHEET), 100)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Correr el test — debe FALLAR**

```bash
python -m pytest tests/test_theme.py -v
```

Esperado: `ModuleNotFoundError: No module named 'gui.theme'`

- [ ] **Step 4: Crear `gui/theme.py`**

```python
BG_APP           = "#1e1e1e"
BG_SIDEBAR       = "#252526"
BG_CARD          = "#2d2d2d"
BG_INPUT         = "#3c3c3c"
BG_ITEM_ACTIVE   = "#37373d"
BG_ITEM_HOVER    = "#2a2d2e"
BORDER           = "#3e3e42"
TEXT_PRIMARY     = "#cccccc"
TEXT_SECONDARY   = "#858585"
ACCENT           = "#0078d4"
SUCCESS          = "#4ec9b0"
ERROR            = "#f44747"
LOG_BG           = "#060d1a"
LOG_FG           = "#a3e635"

GLOBAL_STYLESHEET = f"""
QWidget {{
    background-color: {BG_APP};
    color: {TEXT_PRIMARY};
    font-family: -apple-system, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
}}
QLabel {{ background: transparent; }}
QLineEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 8px 10px;
    color: {TEXT_PRIMARY};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled {{ color: {TEXT_SECONDARY}; }}
QPushButton {{
    background-color: {ACCENT};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: #1a8fe3; }}
QPushButton:pressed {{ background-color: #006bbf; }}
QPushButton:disabled {{ background-color: #37373d; color: {TEXT_SECONDARY}; }}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid {BORDER};
    color: {TEXT_PRIMARY};
}}
QPushButton#ghost:hover {{ border-color: #555; background: {BG_ITEM_HOVER}; }}
QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
}}
QCheckBox {{ spacing: 8px; color: {TEXT_PRIMARY}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 3px;
    border: 1px solid {BORDER};
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {BG_APP};
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: #555;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
"""
```

- [ ] **Step 5: Correr el test — debe PASAR**

```bash
python -m pytest tests/test_theme.py -v
```

Esperado: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add gui/__init__.py gui/panels/__init__.py gui/theme.py tests/test_theme.py
git commit -m "feat: add gui package skeleton and theme constants"
```

---

## Task 2: gui/workers.py

**Files:**
- Create: `gui/workers.py`
- Test: `tests/test_workers.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_workers.py`:

```python
import unittest
from PyQt6 import QtWidgets
from unittest.mock import patch

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class ScraperWorkerSignalTest(unittest.TestCase):
    def setUp(self): self.app = get_app()

    def test_finished_signal_emits_on_success(self):
        from gui.workers import ScraperWorker
        results = []
        with patch("gui.workers.MoodleScraper") as Mock:
            Mock.return_value.ejecutar.return_value = True
            w = ScraperWorker("u", "p", "/tmp", True, [], {}, "tok")
            w.finished.connect(lambda ok, msg: results.append((ok, msg)))
            w.run()
        self.assertEqual(results, [(True, "")])

    def test_finished_signal_emits_on_failure(self):
        from gui.workers import ScraperWorker
        results = []
        with patch("gui.workers.MoodleScraper") as Mock:
            Mock.return_value.ejecutar.return_value = False
            w = ScraperWorker("u", "p", "/tmp", True, [], {}, "")
            w.finished.connect(lambda ok, msg: results.append((ok, msg)))
            w.run()
        self.assertFalse(results[0][0])

if __name__ == "__main__": unittest.main()
```

- [ ] **Step 2: Correr el test — debe FALLAR**

```bash
python -m pytest tests/test_workers.py -v
```

Esperado: `ModuleNotFoundError: No module named 'gui.workers'`

- [ ] **Step 3: Crear `gui/workers.py`**

```python
from typing import Optional, List
from PyQt6 import QtCore
from scraper.navigator import MoodleScraper
from scraper.models import Materia


class ScraperWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(bool, str)
    progress = QtCore.pyqtSignal(str)

    def __init__(self, username, password, output_path, headless,
                 materias=None, materia_modes=None, api_token=""):
        super().__init__()
        self.username = username
        self.password = password
        self.output_path = output_path
        self.headless = headless
        self.materias = materias
        self.materia_modes = materia_modes or {}
        self.api_token = api_token

    def run(self):
        try:
            scraper = MoodleScraper(headless=self.headless, api_token=self.api_token)
            scraper.progress_cb = lambda msg: self.progress.emit(msg)
            scraper.config.OUTPUT_DIR = self.output_path
            ok = scraper.ejecutar(
                username=self.username, password=self.password,
                exportar=True, materias=self.materias, materia_modes=self.materia_modes,
            )
            self.finished.emit(bool(ok), "" if ok else "Error durante el scraping.")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class FetchMateriasWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(bool, list, str, str)

    def __init__(self, username, password, base_url):
        super().__init__()
        self.username = username
        self.password = password
        self.base_url = base_url

    def run(self):
        from scraper.auth import get_moodle_token
        from scraper.api import MoodleAPIClient, api_courses_to_materias
        token = get_moodle_token(self.username, self.password, self.base_url) or ""
        try:
            if token:
                client = MoodleAPIClient(token, self.base_url)
                info = client.get_site_info()
                courses = client.get_enrolled_courses(info["userid"])
                materias = api_courses_to_materias(courses)
            else:
                scraper = MoodleScraper(headless=True)
                materias = scraper.obtener_materias_con_credenciales(
                    username=self.username, password=self.password)
            if not materias:
                self.finished.emit(False, [], "No se encontraron materias.", token)
                return
            self.finished.emit(True, materias, "", token)
        except Exception as exc:
            self.finished.emit(False, [], str(exc), token)
```

- [ ] **Step 4: Correr el test — debe PASAR**

```bash
python -m pytest tests/test_workers.py -v
```

Esperado: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add gui/workers.py tests/test_workers.py
git commit -m "feat: add gui/workers.py with ScraperWorker and FetchMateriasWorker"
```

---

## Task 3: gui/sidebar.py

**Files:**
- Create: `gui/sidebar.py`
- Test: `tests/test_sidebar.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_sidebar.py`:

```python
import unittest
from PyQt6 import QtWidgets

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class SidebarTest(unittest.TestCase):
    def setUp(self): self.app = get_app()

    def test_nav_changed_emits_correct_index(self):
        from gui.sidebar import Sidebar
        s = Sidebar()
        received = []
        s.nav_changed.connect(received.append)
        s.navigate_to(2)
        self.assertEqual(received, [2])

    def test_set_active_checks_correct_button(self):
        from gui.sidebar import Sidebar
        s = Sidebar()
        s.set_active(1)
        self.assertTrue(s._buttons[1].isChecked())
        self.assertFalse(s._buttons[0].isChecked())

    def test_sidebar_has_four_buttons(self):
        from gui.sidebar import Sidebar
        self.assertEqual(len(Sidebar()._buttons), 4)

if __name__ == "__main__": unittest.main()
```

- [ ] **Step 2: Correr el test — debe FALLAR**

```bash
python -m pytest tests/test_sidebar.py -v
```

Esperado: `ModuleNotFoundError: No module named 'gui.sidebar'`

- [ ] **Step 3: Crear `gui/sidebar.py`**

```python
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
```

- [ ] **Step 4: Correr el test — debe PASAR**

```bash
python -m pytest tests/test_sidebar.py -v
```

Esperado: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add gui/sidebar.py tests/test_sidebar.py
git commit -m "feat: add Sidebar with SidebarButton and nav_changed signal"
```

---

## Task 4: gui/panels/conexion.py

**Files:**
- Create: `gui/panels/conexion.py`
- Test: `tests/test_panel_conexion.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_panel_conexion.py`:

```python
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

if __name__ == "__main__": unittest.main()
```

- [ ] **Step 2: Correr el test — debe FALLAR**

```bash
python -m pytest tests/test_panel_conexion.py -v
```

Esperado: `ModuleNotFoundError`

- [ ] **Step 3: Crear `gui/panels/conexion.py`**

```python
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

        for lbl_text, attr, pw in [("Usuario UCC", "username_input", False), ("Contraseña", "password_input", True)]:
            lbl = QtWidgets.QLabel(lbl_text)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
            inp = QtWidgets.QLineEdit()
            if pw:
                inp.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            setattr(self, attr, inp)
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
```

- [ ] **Step 4: Correr el test — debe PASAR**

```bash
python -m pytest tests/test_panel_conexion.py -v
```

Esperado: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add gui/panels/conexion.py tests/test_panel_conexion.py
git commit -m "feat: add ConexionPanel with StatusDot and login_requested signal"
```

---

## Task 5: MateriaCard y MateriasGrid

**Files:**
- Create: `gui/panels/materias.py`
- Test: `tests/test_materia_card.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_materia_card.py`:

```python
import unittest
from PyQt6 import QtWidgets
from scraper.models import Materia

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class MateriaCardTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()
        self.m = Materia(nombre="Física I", url="http://x/1", id_curso="1")

    def test_card_starts_selected(self):
        from gui.panels.materias import MateriaCard
        self.assertTrue(MateriaCard(self.m).is_selected())

    def test_set_selected_false_deselects(self):
        from gui.panels.materias import MateriaCard
        card = MateriaCard(self.m)
        card.set_selected(False)
        self.assertFalse(card.is_selected())

    def test_toggled_signal_emits(self):
        from gui.panels.materias import MateriaCard
        card, received = MateriaCard(self.m), []
        card.toggled.connect(lambda m, s: received.append((m, s)))
        card.set_selected(False)
        self.assertEqual(received, [(self.m, False)])

    def test_grid_populate_creates_cards(self):
        from gui.panels.materias import MateriasGrid
        grid = MateriasGrid()
        grid.populate([Materia(nombre=f"M{i}", url=f"http://x/{i}", id_curso=str(i)) for i in range(4)])
        self.assertEqual(len(grid._cards), 4)

    def test_grid_get_selected_excludes_deselected(self):
        from gui.panels.materias import MateriasGrid
        grid = MateriasGrid()
        ms = [Materia(nombre=f"M{i}", url=f"http://x/{i}", id_curso=str(i)) for i in range(3)]
        grid.populate(ms)
        grid._cards[1].set_selected(False)
        self.assertEqual(len(grid.get_selected()), 2)
        self.assertNotIn(ms[1], grid.get_selected())

if __name__ == "__main__": unittest.main()
```

- [ ] **Step 2: Correr el test — debe FALLAR**

```bash
python -m pytest tests/test_materia_card.py -v
```

Esperado: `ModuleNotFoundError`

- [ ] **Step 3: Crear `gui/panels/materias.py`**

```python
from typing import List
from PyQt6 import QtCore, QtGui, QtWidgets
from scraper.models import Materia
from gui.theme import BG_INPUT, BG_ITEM_ACTIVE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT


class MateriaCard(QtWidgets.QFrame):
    toggled = QtCore.pyqtSignal(object, bool)

    def __init__(self, materia, parent=None):
        super().__init__(parent)
        self.materia = materia
        self._selected = True
        self.setFixedSize(160, 90)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        top = QtWidgets.QHBoxLayout()
        top.addStretch()
        self._check = QtWidgets.QLabel("✓")
        self._check.setStyleSheet(f"color: {ACCENT}; font-size: 12px; font-weight: 700; background: transparent; border: none;")
        top.addWidget(self._check)
        layout.addLayout(top)

        self._name = QtWidgets.QLabel(materia.nombre)
        self._name.setWordWrap(True)
        self._name.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(self._name)
        layout.addStretch()
        self._update_style()

    def mousePressEvent(self, event):
        self.set_selected(not self._selected)

    def set_selected(self, selected):
        self._selected = selected
        self._update_style()
        self.toggled.emit(self.materia, selected)

    def is_selected(self):
        return self._selected

    def _update_style(self):
        if self._selected:
            self.setStyleSheet(f"QFrame {{ background: {BG_ITEM_ACTIVE}; border: 1px solid {ACCENT}; border-radius: 6px; }}")
            self._check.setVisible(True)
            f = self._name.font(); f.setStrikeOut(False); self._name.setFont(f)
            self._name.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;")
        else:
            self.setStyleSheet(f"QFrame {{ background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 6px; }}")
            self._check.setVisible(False)
            f = self._name.font(); f.setStrikeOut(True); self._name.setFont(f)
            self._name.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")


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
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(0, 0, 8, 0)
        self.setWidget(self._container)
        self._cards: List[MateriaCard] = []

    def populate(self, materias):
        for card in self._cards:
            self._grid.removeWidget(card); card.deleteLater()
        self._cards.clear()
        for i, m in enumerate(materias):
            card = MateriaCard(m)
            self._cards.append(card)
            self._grid.addWidget(card, i // 2, i % 2)
        self._grid.setRowStretch(len(materias) // 2 + 1, 1)

    def get_selected(self):
        return [c.materia for c in self._cards if c.is_selected()]

    def select_all(self):
        for c in self._cards:
            if not c.is_selected(): c.set_selected(True)

    def select_none(self):
        for c in self._cards:
            if c.is_selected(): c.set_selected(False)

    def count(self): return len(self._cards)
    def selected_count(self): return sum(1 for c in self._cards if c.is_selected())
```

- [ ] **Step 4: Correr el test — debe PASAR**

```bash
python -m pytest tests/test_materia_card.py -v
```

Esperado: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add gui/panels/materias.py tests/test_materia_card.py
git commit -m "feat: add MateriaCard and MateriasGrid with toggle and selection"
```

---

## Task 6: MateriasPanel

**Files:**
- Modify: `gui/panels/materias.py` (agregar MateriasPanel al final)
- Test: `tests/test_panel_materias.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_panel_materias.py`:

```python
import unittest
from PyQt6 import QtWidgets
from scraper.models import Materia

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

def make_materias(n=4):
    return [Materia(nombre=f"Materia {i}", url=f"http://x/{i}", id_curso=str(i)) for i in range(n)]

class MateriasPanelTest(unittest.TestCase):
    def setUp(self): self.app = get_app()

    def test_populate_updates_counter(self):
        from gui.panels.materias import MateriasPanel
        panel = MateriasPanel()
        panel.populate(make_materias(6))
        self.assertIn("6", panel._counter_label.text())

    def test_get_selected_materias_returns_all_by_default(self):
        from gui.panels.materias import MateriasPanel
        panel = MateriasPanel()
        panel.populate(make_materias(3))
        self.assertEqual(len(panel.get_selected_materias()), 3)

    def test_get_mode_returns_dict(self):
        from gui.panels.materias import MateriasPanel
        mode = MateriasPanel().get_mode()
        self.assertIn("mode", mode)
        self.assertIn("scan_existing", mode)

    def test_set_running_disables_button(self):
        from gui.panels.materias import MateriasPanel
        panel = MateriasPanel()
        panel.set_running(True)
        self.assertFalse(panel.start_btn.isEnabled())
        panel.set_running(False)
        self.assertTrue(panel.start_btn.isEnabled())

if __name__ == "__main__": unittest.main()
```

- [ ] **Step 2: Correr el test — debe FALLAR**

```bash
python -m pytest tests/test_panel_materias.py -v
```

Esperado: error porque `MateriasPanel` no existe.

- [ ] **Step 3: Agregar `MateriasPanel` al final de `gui/panels/materias.py`**

```python

class MateriasPanel(QtWidgets.QWidget):
    start_requested = QtCore.pyqtSignal(list, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Materias")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY}; background: transparent;")
        self._counter_label = QtWidgets.QLabel("")
        self._counter_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; background: transparent;")
        header.addWidget(title)
        header.addWidget(self._counter_label)
        header.addStretch()

        for href, slot in [("Todas", lambda _: self._grid.select_all()), ("Ninguna", lambda _: self._grid.select_none())]:
            lnk = QtWidgets.QLabel(f'<a href="{href}" style="color:{ACCENT};text-decoration:none;">{href}</a>')
            lnk.setOpenExternalLinks(False)
            lnk.linkActivated.connect(slot)
            if href == "Ninguna":
                sep = QtWidgets.QLabel("·")
                sep.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
                header.addWidget(sep)
            header.addWidget(lnk)
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
        self._progress_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
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

    def populate(self, materias):
        self._grid.populate(materias)
        self._counter_label.setText(f"· {len(materias)} disponibles")

    def get_selected_materias(self):
        return self._grid.get_selected()

    def get_mode(self):
        data = self.mode_combo.currentData()
        return {"mode": data[0], "scan_existing": data[1]} if data else {"mode": "update", "scan_existing": True}

    def set_running(self, running):
        self.start_btn.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self._progress_label.setVisible(running)
        self._progress_bar.setVisible(running)

    def update_progress(self, text):
        self._progress_label.setText(text)

    def _on_start_clicked(self):
        materias = self.get_selected_materias()
        if materias:
            mode = self.get_mode()
            self.start_requested.emit(materias, {m.nombre: mode for m in materias})
```

- [ ] **Step 4: Correr el test — debe PASAR**

```bash
python -m pytest tests/test_panel_materias.py -v
```

Esperado: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add gui/panels/materias.py tests/test_panel_materias.py
git commit -m "feat: add MateriasPanel with card grid, mode combo, and progress"
```

---

## Task 7: gui/panels/configuracion.py

**Files:**
- Create: `gui/panels/configuracion.py`
- Test: `tests/test_panel_configuracion.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_panel_configuracion.py`:

```python
import unittest
from PyQt6 import QtWidgets

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class ConfiguracionPanelTest(unittest.TestCase):
    def setUp(self): self.app = get_app()

    def test_get_output_path_returns_initial_value(self):
        from gui.panels.configuracion import ConfiguracionPanel
        self.assertEqual(ConfiguracionPanel("/tmp/test", True).get_output_path(), "/tmp/test")

    def test_get_headless_reflects_checkbox(self):
        from gui.panels.configuracion import ConfiguracionPanel
        panel = ConfiguracionPanel("/tmp", True)
        self.assertTrue(panel.get_headless())
        panel.headless_toggle.setChecked(False)
        self.assertFalse(panel.get_headless())

    def test_set_output_path_updates_display(self):
        from gui.panels.configuracion import ConfiguracionPanel
        panel = ConfiguracionPanel("/tmp", False)
        panel.set_output_path("/new/path")
        self.assertEqual(panel.get_output_path(), "/new/path")

if __name__ == "__main__": unittest.main()
```

- [ ] **Step 2: Correr el test — debe FALLAR**

```bash
python -m pytest tests/test_panel_configuracion.py -v
```

- [ ] **Step 3: Crear `gui/panels/configuracion.py`**

```python
from PyQt6 import QtCore, QtWidgets
from gui.theme import BG_CARD, BORDER, TEXT_PRIMARY, TEXT_SECONDARY


class ConfiguracionPanel(QtWidgets.QWidget):
    output_path_changed = QtCore.pyqtSignal(str)

    def __init__(self, output_path, headless, parent=None):
        super().__init__(parent)
        self._output_path = output_path
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        card = QtWidgets.QFrame()
        card.setStyleSheet(f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}")
        card.setMaximumWidth(480)
        cl = QtWidgets.QVBoxLayout(card)
        cl.setContentsMargins(32, 32, 32, 32)
        cl.setSpacing(20)

        title = QtWidgets.QLabel("Configuración")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY}; background: transparent; border: none;")
        cl.addWidget(title)

        cl.addWidget(self._make_label("Carpeta de destino"))
        row = QtWidgets.QHBoxLayout()
        self._path_display = QtWidgets.QLineEdit(output_path)
        self._path_display.setReadOnly(True)
        self._path_display.setCursorPosition(0)
        browse = QtWidgets.QPushButton("Elegir")
        browse.setObjectName("ghost")
        browse.setFixedWidth(70)
        browse.clicked.connect(self._browse)
        row.addWidget(self._path_display)
        row.addWidget(browse)
        cl.addLayout(row)
        cl.addWidget(self._make_label("Se guarda automáticamente al cambiar.", size=11))

        self.headless_toggle = QtWidgets.QCheckBox("Ocultar navegador mientras trabaja")
        self.headless_toggle.setChecked(headless)
        cl.addWidget(self.headless_toggle)
        cl.addWidget(self._make_label("Con API activa el navegador no se usa de todas formas.", size=11))
        cl.addStretch()

        h = QtWidgets.QHBoxLayout()
        h.addStretch(); h.addWidget(card); h.addStretch()
        layout.addStretch(); layout.addLayout(h); layout.addStretch()

    def _make_label(self, text, size=12):
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: {size}px; background: transparent; border: none;")
        return lbl

    def _browse(self):
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", self._output_path)
        if selected:
            self.set_output_path(selected)
            self.output_path_changed.emit(selected)

    def get_output_path(self): return self._output_path
    def set_output_path(self, path):
        self._output_path = path
        self._path_display.setText(path)
        self._path_display.setCursorPosition(0)
    def get_headless(self): return self.headless_toggle.isChecked()
```

- [ ] **Step 4: Correr el test — debe PASAR**

```bash
python -m pytest tests/test_panel_configuracion.py -v
```

Esperado: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add gui/panels/configuracion.py tests/test_panel_configuracion.py
git commit -m "feat: add ConfiguracionPanel with path picker and headless toggle"
```

---

## Task 8: gui/panels/registro.py

**Files:**
- Create: `gui/panels/registro.py`
- Test: `tests/test_panel_registro.py`

- [ ] **Step 1: Escribir el test**

Crear `tests/test_panel_registro.py`:

```python
import unittest
from PyQt6 import QtWidgets

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class RegistroPanelTest(unittest.TestCase):
    def setUp(self): self.app = get_app()

    def test_append_adds_text(self):
        from gui.panels.registro import RegistroPanel
        panel = RegistroPanel()
        panel.append("hola mundo")
        self.assertIn("hola mundo", panel.log_view.toPlainText())

    def test_clear_empties_log(self):
        from gui.panels.registro import RegistroPanel
        panel = RegistroPanel()
        panel.append("línea 1")
        panel.clear()
        self.assertEqual(panel.log_view.toPlainText().strip(), "")

    def test_empty_text_not_appended(self):
        from gui.panels.registro import RegistroPanel
        panel = RegistroPanel()
        panel.append("")
        self.assertEqual(panel.log_view.toPlainText().strip(), "")

if __name__ == "__main__": unittest.main()
```

- [ ] **Step 2: Correr el test — debe FALLAR**

```bash
python -m pytest tests/test_panel_registro.py -v
```

- [ ] **Step 3: Crear `gui/panels/registro.py`**

```python
from PyQt6 import QtGui, QtWidgets
from gui.theme import BORDER, TEXT_SECONDARY, LOG_BG, LOG_FG


class RegistroPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel("Registro de actividad")
        lbl.setStyleSheet(f"font-weight: 600; color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        clear_btn = QtWidgets.QPushButton("Limpiar")
        clear_btn.setObjectName("ghost")
        clear_btn.setFixedHeight(26)
        clear_btn.setStyleSheet(f"""
            QPushButton#ghost {{
                font-size: 11px; padding: 2px 10px;
                border: 1px solid {BORDER}; border-radius: 4px;
                background: transparent; color: {TEXT_SECONDARY};
            }}
            QPushButton#ghost:hover {{ color: #aaa; border-color: #555; }}
        """)
        clear_btn.clicked.connect(self.clear)
        header.addWidget(lbl); header.addStretch(); header.addWidget(clear_btn)
        layout.addLayout(header)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QtGui.QFont("Menlo", 11))
        self.log_view.setStyleSheet(f"""
            QTextEdit {{
                background: {LOG_BG}; border: 1px solid {BORDER};
                border-radius: 6px; color: {LOG_FG}; padding: 8px;
            }}
        """)
        layout.addWidget(self.log_view)

    def append(self, text):
        if not text: return
        self.log_view.append(text)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def clear(self):
        self.log_view.clear()
```

- [ ] **Step 4: Correr el test — debe PASAR**

```bash
python -m pytest tests/test_panel_registro.py -v
```

Esperado: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add gui/panels/registro.py tests/test_panel_registro.py
git commit -m "feat: add RegistroPanel with append, clear, and auto-scroll"
```

---

## Task 9: gui/main_window.py

**Files:**
- Create: `gui/main_window.py`

- [ ] **Step 1: Crear `gui/main_window.py`**

```python
import json
from pathlib import Path
from typing import Optional, List

import keyring
from PyQt6 import QtCore, QtGui, QtWidgets

from utils.config import Config
from scraper.models import Materia
from gui.theme import GLOBAL_STYLESHEET, BG_APP
from gui.workers import ScraperWorker, FetchMateriasWorker
from gui.sidebar import Sidebar
from gui.panels.conexion import ConexionPanel
from gui.panels.materias import MateriasPanel
from gui.panels.configuracion import ConfiguracionPanel
from gui.panels.registro import RegistroPanel

PANEL_CONEXION = 0; PANEL_MATERIAS = 1; PANEL_CONFIGURACION = 2; PANEL_REGISTRO = 3


class ScrappyGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self._output_path = str(Path.home() / "Downloads")
        self._settings_path = Path("config/user_settings.json")
        self._load_last_output_path()
        self._api_token = ""
        self._username = ""
        self._password = ""
        self._keyring_service = "scrappy_moodle_ucc"
        self.worker: Optional[ScraperWorker] = None
        self.fetch_worker: Optional[FetchMateriasWorker] = None
        self._setup_window()
        self._build_ui()
        self._load_saved_credentials()

    def _setup_window(self):
        self.setWindowTitle("Scrappy · Moodle UCC")
        self.resize(960, 640)
        self.setMinimumSize(860, 560)
        self.setStyleSheet(GLOBAL_STYLESHEET)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.nav_changed.connect(self._on_nav_changed)
        root.addWidget(self.sidebar)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.setStyleSheet(f"background: {BG_APP};")

        self.conexion_panel = ConexionPanel()
        self.conexion_panel.login_requested.connect(self._start_fetch)
        self.materias_panel = MateriasPanel()
        self.materias_panel.start_requested.connect(self._start_scraping)
        self.config_panel = ConfiguracionPanel(self._output_path, self.config.HEADLESS)
        self.config_panel.output_path_changed.connect(self._on_output_path_changed)
        self.registro_panel = RegistroPanel()

        for panel in (self.conexion_panel, self.materias_panel, self.config_panel, self.registro_panel):
            self.stack.addWidget(panel)
        root.addWidget(self.stack, stretch=1)

    def _navigate_to(self, index):
        self.stack.setCurrentIndex(index)
        self.sidebar.set_active(index)

    def _on_nav_changed(self, index):
        self.stack.setCurrentIndex(index)

    def _start_fetch(self, username, password):
        self._username, self._password = username, password
        self.conexion_panel.set_loading(True)
        self.fetch_worker = FetchMateriasWorker(username, password, self.config.BASE_URL)
        self.fetch_worker.finished.connect(self._on_fetch_finished)
        self.fetch_worker.start()

    def _on_fetch_finished(self, success, materias, message, token):
        self.conexion_panel.set_loading(False)
        self._api_token = token
        if success:
            if self.conexion_panel.should_remember():
                self._save_credentials()
            else:
                self._clear_saved_credentials()
            self.materias_panel.populate(materias)
            self.conexion_panel.set_status("connected", "Conectado" + (" · API ✓" if token else ""))
            self._navigate_to(PANEL_MATERIAS)
        else:
            self.conexion_panel.set_status("error", message or "Error de conexión")
            QtWidgets.QMessageBox.critical(self, "Error de conexión", message or "No se pudieron listar las materias.")

    def _start_scraping(self, materias, materia_modes):
        self.materias_panel.set_running(True)
        self.registro_panel.clear()
        self._navigate_to(PANEL_REGISTRO)
        self.worker = ScraperWorker(
            username=self._username, password=self._password,
            output_path=self.config_panel.get_output_path(),
            headless=self.config_panel.get_headless(),
            materias=materias, materia_modes=materia_modes, api_token=self._api_token,
        )
        self.worker.progress.connect(self.registro_panel.append)
        self.worker.finished.connect(self._on_scraping_finished)
        self.worker.start()

    def _on_scraping_finished(self, success, message):
        self.materias_panel.set_running(False)
        if success:
            self.registro_panel.append("✓ Descarga completada.")
            self.registro_panel.append(f"  Guardado en: {self.config_panel.get_output_path()}")
        else:
            self.registro_panel.append(f"✗ Error: {message or 'desconocido'}")
            QtWidgets.QMessageBox.critical(self, "Error durante el scraping", message or "Error desconocido.")

    def _on_output_path_changed(self, path):
        self._output_path = path
        self._save_last_output_path()

    def _load_last_output_path(self):
        try:
            if self._settings_path.exists():
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    last = json.load(f).get("last_output_path")
                    if last: self._output_path = last
        except Exception: pass

    def _save_last_output_path(self):
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump({"last_output_path": self._output_path}, f, ensure_ascii=False)
        except Exception: pass

    def _load_saved_credentials(self):
        try:
            u = keyring.get_password(self._keyring_service, "last_username")
            if not u: return
            p = keyring.get_password(self._keyring_service, u)
            if not p: return
            self.conexion_panel.set_credentials(u, p)
            self.conexion_panel.set_remember(True)
            QtCore.QTimer.singleShot(200, lambda: self._start_fetch(u, p))
        except Exception: pass

    def _save_credentials(self):
        try:
            keyring.set_password(self._keyring_service, "last_username", self._username)
            keyring.set_password(self._keyring_service, self._username, self._password)
        except Exception: pass

    def _clear_saved_credentials(self):
        for key in ["last_username", self._username]:
            try: keyring.delete_password(self._keyring_service, key)
            except Exception: pass


def main():
    app = QtWidgets.QApplication([])
    app.setFont(QtGui.QFont("-apple-system", 13))
    window = ScrappyGUI()
    window.show()
    app.exec()
```

- [ ] **Step 2: Commit**

```bash
git add gui/main_window.py
git commit -m "feat: add ScrappyGUI main window wiring sidebar, panels, and workers"
```

---

## Task 10: Finalizar paquete, actualizar tests, eliminar gui.py

**Files:**
- Modify: `gui/__init__.py`
- Modify: `tests/test_ui_warnings.py`
- Delete: `gui.py`

- [ ] **Step 1: Completar `gui/__init__.py`**

```python
from gui.main_window import ScrappyGUI, main

__all__ = ["ScrappyGUI", "main"]
```

- [ ] **Step 2: Correr todos los tests — deben pasar**

```bash
python -m pytest tests/ -v
```

Esperado: todos los tests de tasks 1-8 pasan.

- [ ] **Step 3: Reescribir `tests/test_ui_warnings.py`**

El test anterior usaba `materias_view` (QListView). Con el nuevo diseño las materias son cards en QGridLayout. Reemplazar el archivo completo:

```python
import io, unittest
from contextlib import redirect_stderr
from PyQt6 import QtWidgets, QtCore, QtGui
from scraper.models import Materia
import gui

def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

class MateriasGridRenderTest(unittest.TestCase):
    def setUp(self): self.app = get_app()

    def test_no_qt_errors_on_grid_scroll(self):
        window = gui.ScrappyGUI()
        window.materias_panel.populate([
            Materia(nombre=f"Materia {i}", url=f"http://example.com/{i}", id_curso=str(i))
            for i in range(15)
        ])
        window.resize(960, 640)
        window.show()
        buf = io.StringIO()
        with redirect_stderr(buf):
            self.app.processEvents()
            viewport = window.materias_panel._grid.viewport()
            event = QtGui.QWheelEvent(
                QtCore.QPointF(10, 10), QtCore.QPointF(10, 10),
                QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
                QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.KeyboardModifier.NoModifier,
                QtCore.Qt.ScrollPhase.ScrollUpdate, False,
                QtCore.Qt.MouseEventSource.MouseEventNotSynthesized,
            )
            QtWidgets.QApplication.sendEvent(viewport, event)
            self.app.processEvents()
        self.assertNotIn("Point size <=", buf.getvalue())

if __name__ == "__main__": unittest.main()
```

- [ ] **Step 4: Correr el test actualizado**

```bash
python -m pytest tests/test_ui_warnings.py -v
```

Esperado: `1 passed`

- [ ] **Step 5: Correr la suite completa**

```bash
python -m pytest tests/ -v
```

Esperado: todos los tests pasan.

- [ ] **Step 6: Eliminar `gui.py`**

```bash
git rm gui.py
```

- [ ] **Step 7: Verificar la app visualmente**

```bash
python main.py
```

Verificar:
- Sidebar con 4 ítems a la izquierda
- Panel Conexión al inicio (o Materias con auto-login si hay credenciales guardadas)
- Paleta oscura neutra sin purple/teal
- Cards en grilla al navegar a Materias
- Panel Configuración con un solo toggle headless
- Panel Registro con terminal verde sobre negro
- Al iniciar descarga, navega automáticamente a Registro

- [ ] **Step 8: Commit final**

```bash
git add gui/__init__.py tests/test_ui_warnings.py
git commit -m "feat: complete ui redesign — sidebar, panel cards, VS Code dark theme"
```
