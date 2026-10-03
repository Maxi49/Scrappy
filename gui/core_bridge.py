"""Puente de proceso entre la UI PyQt y el núcleo Go de Scrappy."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from typing import Callable, Iterable, Optional

from gui.models import Materia


class CoreError(RuntimeError):
    pass


class CoreCancelled(CoreError):
    pass


CANCEL_GRACE_SECONDS = 5

IS_WINDOWS = os.name == "nt"
# The packaged app has no console; without this flag Windows opens a console
# window for the core every time it runs.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


class CoreClient:
    def __init__(self, core_path: Optional[str] = None):
        self._project_root = Path(__file__).resolve().parents[1]
        self._core_path = core_path
        self._resolved_command: Optional[list[str]] = None
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False

    @property
    def _command(self) -> list[str]:
        # Resolved on first use so a missing core surfaces as a worker error,
        # not as an exception while the UI builds the worker.
        if self._resolved_command is None:
            self._resolved_command = self._resolve_command(self._core_path)
        return self._resolved_command

    def cancel(self) -> None:
        """Pide al núcleo Go que termine; puede llamarse desde otro hilo.

        El core atrapa la señal, guarda el manifiesto con lo ya descargado y
        sale. Si no lo hace a tiempo, se lo mata.
        """
        with self._lock:
            self._cancelled = True
            process = self._process
        if process is not None:
            self._stop(process)

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        """Cierra el stdin del core (su señal de cancelación en toda plataforma)
        y lo mata sólo si no terminó dentro del margen."""
        if process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass

        def force_stop():
            if process.poll() is None:
                process.kill()

        timer = threading.Timer(CANCEL_GRACE_SECONDS, force_stop)
        timer.daemon = True
        timer.start()

    def list_courses(
        self, username: str, password: str, base_url: str
    ) -> tuple[list[Materia], str]:
        result = self._run(
            {
                "action": "courses",
                "base_url": base_url,
                "username": username,
                "password": password,
            }
        )
        courses = [Materia.from_core(item) for item in result.get("courses", [])]
        courses = [course for course in courses if course.nombre and course.id_curso]
        return courses, str(result.get("token", ""))

    def find_duplicates(self, output_path: str) -> dict:
        return self._run({"action": "duplicates", "output_path": output_path})

    def remove_duplicates(self, output_path: str, paths: list[str]) -> dict:
        return self._run(
            {"action": "remove_duplicates", "output_path": output_path, "paths": list(paths)}
        )

    def sync(
        self,
        *,
        username: str,
        password: str,
        token: str,
        base_url: str,
        output_path: str,
        materias: Iterable[Materia],
        materia_modes: dict,
        export: bool = True,
        progress: Optional[Callable[[str], None]] = None,
    ) -> dict:
        courses = []
        for materia in materias:
            mode = materia_modes.get(
                materia.nombre, {"mode": "update", "scan_existing": True}
            )
            courses.append(materia.to_core(mode))
        return self._run(
            {
                "action": "sync",
                "base_url": base_url,
                "username": username,
                "password": password,
                "token": token,
                "output_path": output_path,
                "export": export,
                "courses": courses,
            },
            progress=progress,
            allow_failure=True,
        )

    def _run(
        self,
        payload: dict,
        progress: Optional[Callable[[str], None]] = None,
        allow_failure: bool = False,
    ) -> dict:
        with self._lock:
            if self._cancelled:
                return self._cancelled_outcome(None, allow_failure)
        try:
            process = subprocess.Popen(
                self._command,
                cwd=str(self._project_root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0,
            )
        except OSError as exc:
            raise CoreError(f"No se pudo iniciar el núcleo Go: {exc}") from exc
        with self._lock:
            self._process = process
            cancelled = self._cancelled
        if cancelled:
            self._stop(process)

        assert process.stdin is not None
        assert process.stdout is not None
        # stdin stays open: closing it is how cancel() asks the core to stop,
        # and it also stops the core if this process dies.
        payload = {**payload, "cancel_on_stdin_close": True}
        try:
            json.dump(payload, process.stdin, ensure_ascii=False)
            process.stdin.write("\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            process.kill()
            process.wait()
            with self._lock:
                self._process = None
                if self._cancelled:
                    return self._cancelled_outcome(None, allow_failure)
            raise CoreError("El núcleo Go se cerró antes de recibir la solicitud.") from exc

        result: Optional[dict] = None
        diagnostics: list[str] = []
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                diagnostics.append(line)
                continue
            if event.get("event") == "progress" and progress:
                progress(str(event.get("message", "")))
            elif event.get("event") == "result":
                result = event

        return_code = process.wait()
        with self._lock:
            self._process = None
            try:
                process.stdin.close()
            except OSError:
                pass
            cancelled = self._cancelled
        if cancelled or (result is not None and result.get("cancelled")):
            return self._cancelled_outcome(result, allow_failure)
        if result is None:
            detail = diagnostics[-1] if diagnostics else f"código de salida {return_code}"
            raise CoreError(f"El núcleo Go no devolvió un resultado válido: {detail}")
        if return_code != 0 and result.get("ok"):
            raise CoreError(f"El núcleo Go terminó con código de salida {return_code}.")
        if not result.get("ok") and not allow_failure:
            raise CoreError(str(result.get("error") or "Error desconocido del núcleo Go."))
        return result

    @staticmethod
    def _cancelled_outcome(result: Optional[dict], allow_failure: bool) -> dict:
        if not allow_failure:
            raise CoreCancelled("Operación cancelada.")
        outcome = dict(result or {})
        outcome.update(ok=False, cancelled=True)
        outcome.setdefault("error", "Operación cancelada.")
        return outcome

    def _resolve_command(self, explicit_path: Optional[str]) -> list[str]:
        executable_name = "scrappy-core.exe" if os.name == "nt" else "scrappy-core"
        candidates: list[Path] = []
        configured = explicit_path or os.environ.get("SCRAPPY_CORE_PATH")
        if configured:
            candidates.append(Path(configured).expanduser())

        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            candidates.append(Path(bundle_root) / executable_name)
        candidates.extend(
            [
                Path(sys.executable).resolve().parent / executable_name,
                self._project_root / "bin" / executable_name,
            ]
        )
        on_path = shutil.which(executable_name)
        if on_path:
            candidates.append(Path(on_path))
        for candidate in candidates:
            if candidate.is_file():
                return [str(candidate)]

        go = shutil.which("go")
        if go and (self._project_root / "go.mod").exists():
            return [go, "run", "./cmd/scrappy-core"]
        raise CoreError(
            "No se encontró scrappy-core. Recompilá la aplicación o definí SCRAPPY_CORE_PATH."
        )
