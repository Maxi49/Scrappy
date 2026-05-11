import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from PyQt6 import QtCore, QtGui, QtWidgets

import gui
from scraper.models import Materia


def get_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class MateriasGridRenderTest(unittest.TestCase):
    def setUp(self):
        self.app = get_app()

    @patch("keyring.get_password", return_value=None)
    def test_no_qt_errors_on_grid_scroll(self, _get_password):
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
            QtWidgets.QApplication.sendEvent(viewport, event)
            self.app.processEvents()

        self.assertNotIn("Point size <=", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
