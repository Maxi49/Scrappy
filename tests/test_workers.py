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
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.sync.return_value = {"ok": True}
            w = ScraperWorker("u", "p", "/tmp", [], {}, "tok")
            w.finished.connect(lambda ok, msg: results.append((ok, msg)))
            w.run()
        self.assertEqual(results, [(True, "")])

    def test_finished_signal_emits_on_failure(self):
        from gui.workers import ScraperWorker
        results = []
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.sync.return_value = {"ok": False, "error": "falló"}
            w = ScraperWorker("u", "p", "/tmp", [], {}, "")
            w.finished.connect(lambda ok, msg: results.append((ok, msg)))
            w.run()
        self.assertFalse(results[0][0])

    def test_report_summary_is_streamed_before_finishing(self):
        from gui.workers import ScraperWorker
        lines, results = [], []
        report = {
            "downloaded": 3, "links_saved": 2, "unchanged": 5, "skipped": 0,
            "inaccessible": 1, "failed": 1,
            "failures": [{"materia": "Rota", "modulo": "", "recurso": "", "error": "HTTP 403"}],
        }
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.sync.return_value = {"ok": False, "error": "parcial", "report": report}
            w = ScraperWorker("u", "p", "/tmp", [], {}, "tok")
            w.progress.connect(lines.append)
            w.finished.connect(lambda ok, msg: results.append((ok, msg)))
            w.run()
        summary = "\n".join(lines)
        self.assertIn("3 descargados", summary)
        self.assertIn("2 enlaces", summary)
        self.assertIn("5 sin cambios", summary)
        self.assertIn("1 con error", summary)
        self.assertIn("Rota", summary)
        self.assertEqual(results, [(False, "parcial")])

    def test_fetch_worker_uses_go_core(self):
        from gui.models import Materia
        from gui.workers import FetchMateriasWorker

        results = []
        materias = [Materia("Materia", "https://moodle/course/1", "1")]
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.list_courses.return_value = (materias, "tok")
            worker = FetchMateriasWorker("u", "p", "https://moodle")
            worker.finished.connect(lambda *args: results.append(args))
            worker.run()
        self.assertEqual(results, [(True, materias, "", "tok")])

if __name__ == "__main__": unittest.main()
