"""Smoke test de punta a punta para la app empaquetada.

Levanta un Moodle falso en localhost, ejecuta el binario empaquetado en modo
CLI con un entorno mínimo y verifica que descargue los archivos esperados.
Uso: python scripts/smoke_packaged.py <ruta-al-ejecutable>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TOKEN = "smoke-token"
USERNAME = "alumno"
PASSWORD = "clave de prueba"
COURSES = {1: "Álgebra", 2: "Física I"}
FILES_PER_COURSE = 2
TIMEOUT_SECONDS = 120


class FakeMoodle(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def log_request(self, code="-", size="-"):
        # Shows how far the app got if it stalls; the query (token) is dropped.
        print(f"[fake-moodle] {self.command} {urlparse(self.path).path} -> {code}", flush=True)

    def _json(self, body) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))

        def field(name: str) -> str:
            return form.get(name, [""])[0]

        if self.path.startswith("/login/token.php"):
            if field("username") == USERNAME and field("password") == PASSWORD:
                return self._json({"token": TOKEN})
            return self._json({"error": "Datos de acceso inválidos"})
        if field("wstoken") != TOKEN:
            return self._json({"exception": "moodle_exception", "errorcode": "invalidtoken", "message": "Token inválido"})
        function = field("wsfunction")
        if function == "core_webservice_get_site_info":
            return self._json({"userid": 1, "functions": []})
        if function == "core_enrol_get_users_courses":
            return self._json([{"id": cid, "fullname": name} for cid, name in COURSES.items()])
        if function == "core_course_get_contents":
            course = field("courseid")
            base = f"http://{self.headers['Host']}"
            modules = [
                {
                    "id": 100 + index,
                    "name": f"Apunte {index}",
                    "modname": "resource",
                    "uservisible": 1,
                    "contents": [{
                        "type": "file",
                        "filename": f"apunte{index}.pdf",
                        "filepath": "/",
                        "filesize": 4,
                        "fileurl": f"{base}/webservice/pluginfile.php/{course}{index}/mod_resource/content/1/apunte{index}.pdf",
                    }],
                }
                for index in range(FILES_PER_COURSE)
            ]
            return self._json([{"id": 1, "name": "Unidad 1", "section": 1, "modules": modules}])
        return self._json({"exception": "webservice_access_exception", "message": "no disponible"})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith("/webservice/pluginfile.php/") and parse_qs(url.query).get("token") == [TOKEN]:
            self.send_response(200)
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"%PDF")
            return
        self.send_response(302)
        self.send_header("Location", "/login/index.php")
        self.end_headers()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    executable = Path(sys.argv[1]).resolve()
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMoodle)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with tempfile.TemporaryDirectory() as output:
        env = {
            "MOODLE_BASE_URL": f"http://127.0.0.1:{server.server_port}",
            "UCC_USERNAME": USERNAME,
            "UCC_PASSWORD": PASSWORD,
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
        # Keep only what an OS needs to start a process, like a fresh login.
        for name in ("HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA"):
            if name in os.environ:
                env[name] = os.environ[name]
        lines: list[str] = []
        process = subprocess.Popen(
            [str(executable), "--output", output],
            env=env,
            cwd=tempfile.gettempdir(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        def pump() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.append(line)
                print(f"[app] {line.rstrip()}", flush=True)

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            returncode = process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            server.shutdown()
            print(f"FAIL: app still running after {TIMEOUT_SECONDS}s", file=sys.stderr)
            return 1
        reader.join(timeout=10)
        server.shutdown()
        if returncode != 0:
            print(f"FAIL: exit code {returncode}", file=sys.stderr)
            return 1

        expected = {
            Path(name, "Unidad 1", f"apunte{index}.pdf")
            for name in COURSES.values()
            for index in range(FILES_PER_COURSE)
        }
        missing = [str(path) for path in expected if not (Path(output) / path).is_file()]
        report_path = Path(output) / ".scrappy" / "sync-report.json"
        if missing or not report_path.is_file():
            print(f"FAIL: missing {missing or report_path}", file=sys.stderr)
            return 1
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("downloaded") != len(expected) or report.get("failed"):
            print(f"FAIL: unexpected report {report}", file=sys.stderr)
            return 1
    print(f"OK: packaged app downloaded {len(expected)} files through the Go core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
