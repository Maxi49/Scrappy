import io
import sys
import unittest
from contextlib import redirect_stderr

from PyQt6 import QtWidgets, QtCore, QtGui, QtTest


from scraper.models import Materia

import gui
def get_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


class FontWarningTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    def test_no_font_warning_on_scroll_and_mouse(self):
        window = gui.ScrappyGUI()
        materias = [Materia(nombre=f"Materia {i}", url=f"http://example.com/{i}") for i in range(15)]
        window._populate_materias_list(materias)
        window.resize(900, 600)
        window.show()
        self.app.processEvents()

        buf = io.StringIO()
        with redirect_stderr(buf):
            # Simular movimiento de mouse y scroll en la lista
            QtTest.QTest.mouseMove(window.materias_view.viewport(), QtCore.QPoint(5, 5))
            event = QtGui.QWheelEvent(
                QtCore.QPointF(10, 10),
                QtCore.QPointF(10, 10),
                QtCore.QPoint(0, 0),
                QtCore.QPoint(0, 120),
                QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.KeyboardModifier.NoModifier,
                QtCore.Qt.ScrollPhase.ScrollUpdate,
                False,
                QtCore.Qt.MouseEventSource.MouseEventNotSynthesized,
            )
            QtWidgets.QApplication.sendEvent(window.materias_view.viewport(), event)
            self.app.processEvents()

        output = buf.getvalue()
        self.assertNotIn("Point size <=", output)


if __name__ == "__main__":
    unittest.main()
