import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

from gui.core_bridge import CoreCancelled, CoreClient
from gui.models import Materia


def make_fake_core(tmp_path: Path, lines: list[dict]) -> str:
    script = tmp_path / "fake-core"
    encoded = repr([json.dumps(line) for line in lines])
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "request = json.loads(sys.stdin.readline())\n"
        "assert request['cancel_on_stdin_close'] is True\n"
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


def test_cancel_stops_a_running_core(tmp_path):
    script = tmp_path / "slow-core"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, time\n"
        "sys.stdin.readline()\n"
        "print(json.dumps({'event': 'progress', 'message': 'Descargando'}), flush=True)\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'event': 'result', 'ok': False, 'cancelled': True, 'error': 'x'}), flush=True)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    client = CoreClient(str(script))
    started = time.monotonic()
    result = client.sync(
        username="user",
        password="password",
        token="token",
        base_url="https://moodle",
        output_path=str(tmp_path),
        materias=[Materia("Materia", "https://moodle/12", "12")],
        materia_modes={},
        progress=lambda _message: client.cancel(),
    )
    assert time.monotonic() - started < 3
    assert result["ok"] is False
    assert result["cancelled"] is True


def test_cancelled_course_listing_raises(tmp_path):
    client = CoreClient(make_fake_core(tmp_path, []))
    client.cancel()
    try:
        client.list_courses("user", "password", "https://moodle")
    except CoreCancelled:
        return
    raise AssertionError("expected CoreCancelled")
