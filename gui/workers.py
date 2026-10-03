from typing import Optional, List
from PyQt6 import QtCore
from gui.core_bridge import CoreClient
from gui.models import Materia
from utils.config import Config


def summarize_report(report: Optional[dict]) -> List[str]:
    """Convierte el reporte del core Go en líneas legibles para el registro."""
    if not report:
        return []
    lines = [
        "Resumen: "
        f"{report.get('downloaded', 0)} descargados · "
        f"{report.get('links_saved', 0)} enlaces · "
        f"{report.get('unchanged', 0)} sin cambios · "
        f"{report.get('skipped', 0)} omitidos · "
        f"{report.get('inaccessible', 0)} inaccesibles · "
        f"{report.get('failed', 0)} con error"
    ]
    for failure in report.get("failures") or []:
        where = " / ".join(
            part for part in (failure.get("materia"), failure.get("modulo"), failure.get("recurso")) if part
        )
        lines.append(f"  ✗ {where}: {failure.get('error', '')}")
    return lines


class ScraperWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(bool, str)
    progress = QtCore.pyqtSignal(str)

    def __init__(
        self,
        username: str,
        password: str,
        output_path: str,
        materias: Optional[List[Materia]] = None,
        materia_modes: Optional[dict] = None,
        api_token: str = "",
    ):
        super().__init__()
        self.username = username
        self.password = password
        self.output_path = output_path
        self.materias = materias
        self.materia_modes = materia_modes or {}
        self.api_token = api_token

    def run(self):
        try:
            result = CoreClient().sync(
                username=self.username,
                password=self.password,
                token=self.api_token,
                base_url=Config.BASE_URL,
                output_path=self.output_path,
                materias=self.materias or [],
                materia_modes=self.materia_modes,
                progress=lambda msg: self.progress.emit(msg),
            )
            for line in summarize_report(result.get("report")):
                self.progress.emit(line)
            ok = bool(result.get("ok"))
            self.finished.emit(ok, "" if ok else str(result.get("error", "Error durante la descarga.")))
        except Exception as exc:
            self.finished.emit(False, str(exc))


class FetchMateriasWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(bool, list, str, str)

    def __init__(self, username: str, password: str, base_url: str):
        super().__init__()
        self.username = username
        self.password = password
        self.base_url = base_url

    def run(self):
        try:
            materias, token = CoreClient().list_courses(
                self.username, self.password, self.base_url
            )
            if not materias:
                self.finished.emit(False, [], "No se encontraron materias.", token)
                return
            self.finished.emit(True, materias, "", token)
        except Exception as exc:
            self.finished.emit(False, [], str(exc), "")
