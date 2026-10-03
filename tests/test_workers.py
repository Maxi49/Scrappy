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
            w.finished.connect(lambda status, msg: results.append((status, msg)))
            w.run()
        self.assertEqual(results, [("ok", "")])

    def test_finished_signal_emits_on_failure(self):
        from gui.workers import ScraperWorker
        results = []
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.sync.return_value = {"ok": False, "error": "falló"}
            w = ScraperWorker("u", "p", "/tmp", [], {}, "")
            w.finished.connect(lambda status, msg: results.append((status, msg)))
            w.run()
        self.assertEqual(results, [("error", "falló")])

    def test_failure_after_syncing_is_reported_as_partial(self):
        from gui.workers import ScraperWorker
        results = []
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.sync.return_value = {"ok": False, "error": "2 fallaron", "report": {"downloaded": 5}}
            w = ScraperWorker("u", "p", "/tmp", [], {}, "")
            w.finished.connect(lambda status, msg: results.append((status, msg)))
            w.run()
        self.assertEqual(results, [("partial", "2 fallaron")])

    def test_cancelled_sync_is_reported_as_cancelled(self):
        from gui.workers import ScraperWorker
        results = []
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.sync.return_value = {"ok": False, "cancelled": True, "error": "x", "report": {}}
            w = ScraperWorker("u", "p", "/tmp", [], {}, "")
            w.finished.connect(lambda status, msg: results.append((status, msg)))
            w.run()
        self.assertEqual(results[0][0], "cancelled")

    def test_cancel_reaches_the_core_client(self):
        from gui.workers import FetchMateriasWorker, ScraperWorker
        with patch("gui.workers.CoreClient") as Mock:
            ScraperWorker("u", "p", "/tmp", [], {}, "").cancel()
            FetchMateriasWorker("u", "p", "https://moodle").cancel()
        self.assertEqual(Mock.return_value.cancel.call_count, 2)

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
            w.finished.connect(lambda status, msg: results.append((status, msg)))
            w.run()
        summary = "\n".join(lines)
        self.assertIn("3 descargados", summary)
        self.assertIn("2 enlaces", summary)
        self.assertIn("5 sin cambios", summary)
        self.assertIn("1 con error", summary)
        self.assertIn("Rota", summary)
        self.assertEqual(results, [("partial", "parcial")])

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

    def test_missing_core_is_reported_by_the_worker(self):
        from gui.workers import ScraperWorker
        results = []
        with patch.dict("os.environ", {"SCRAPPY_CORE_PATH": ""}), \
                patch("gui.core_bridge.CoreClient._resolve_command", side_effect=RuntimeError("sin core")):
            w = ScraperWorker("u", "p", "/tmp", [], {}, "")
            w.finished.connect(lambda status, msg: results.append((status, msg)))
            w.run()
        self.assertEqual(results, [("error", "sin core")])

    def test_duplicates_worker_scans_or_removes(self):
        from gui.workers import DuplicatesWorker
        results = []
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.find_duplicates.return_value = {"ok": True, "duplicates": [], "bytes": 0}
            Mock.return_value.remove_duplicates.return_value = {"ok": True, "removed": ["a_1.pdf"]}
            scan = DuplicatesWorker("/out")
            scan.finished.connect(lambda *args: results.append(args))
            scan.run()
            remove = DuplicatesWorker("/out", ["a_1.pdf"])
            remove.finished.connect(lambda *args: results.append(args))
            remove.run()
        Mock.return_value.find_duplicates.assert_called_once_with("/out")
        Mock.return_value.remove_duplicates.assert_called_once_with("/out", ["a_1.pdf"])
        self.assertEqual(results[0][0], True)
        self.assertEqual(results[1][1]["removed"], ["a_1.pdf"])

    def test_duplicates_worker_reports_errors(self):
        from gui.workers import DuplicatesWorker
        results = []
        with patch("gui.workers.CoreClient") as Mock:
            Mock.return_value.find_duplicates.side_effect = RuntimeError("no existe")
            worker = DuplicatesWorker("/out")
            worker.finished.connect(lambda *args: results.append(args))
            worker.run()
        self.assertEqual(results, [(False, {}, "no existe")])

if __name__ == "__main__": unittest.main()
