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
