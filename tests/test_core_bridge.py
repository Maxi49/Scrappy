import json
from pathlib import Path
import sys
from unittest.mock import patch

from gui.core_bridge import CoreClient
from gui.models import Materia


def make_fake_core(tmp_path: Path, lines: list[dict]) -> str:
    script = tmp_path / "fake-core"
    encoded = repr([json.dumps(line) for line in lines])
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "_ = sys.stdin.read()\n"
        f"for line in {encoded}: print(line, flush=True)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


def test_list_courses_maps_go_result(tmp_path):
    core = make_fake_core(
        tmp_path,
        [
            {"event": "progress", "message": "ok"},
            {
                "event": "result",
                "ok": True,
                "token": "token",
                "courses": [{"id": 12, "name": "Materia", "url": "https://moodle/12"}],
            },
        ],
    )
    materias, token = CoreClient(core).list_courses("user", "password", "https://moodle")
    assert token == "token"
    assert materias == [Materia("Materia", "https://moodle/12", "12")]


def test_sync_streams_progress_and_course_mode(tmp_path):
    core = make_fake_core(
        tmp_path,
        [
            {"event": "progress", "message": "Analizando"},
            {"event": "result", "ok": True, "report": {"downloaded": 1}},
        ],
    )
    progress = []
    result = CoreClient(core).sync(
        username="user",
        password="password",
        token="token",
        base_url="https://moodle",
        output_path=str(tmp_path),
        materias=[Materia("Materia", "https://moodle/12", "12")],
        materia_modes={"Materia": {"mode": "full", "scan_existing": True}},
        progress=progress.append,
    )
    assert result["ok"] is True
    assert progress == ["Analizando"]


def test_packaged_core_is_resolved_from_meipass(tmp_path):
    core_name = "scrappy-core.exe" if sys.platform == "win32" else "scrappy-core"
    core = tmp_path / core_name
    core.write_bytes(b"binary")

    with patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
        client = CoreClient()

    assert client._command == [str(core)]
