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
