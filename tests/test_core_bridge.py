import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

from gui.core_bridge import CREATE_NO_WINDOW, CoreCancelled, CoreClient
from gui.models import Materia


def fake_client(script: str) -> CoreClient:
    """CoreClient that runs a Python fake core; works on every OS (Windows
    cannot execute a shebang script directly)."""
    client = CoreClient(script)
    client._resolved_command = [sys.executable, script]
    return client


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
    materias, token = fake_client(core).list_courses("user", "password", "https://moodle")
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
    result = fake_client(core).sync(
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
    client = fake_client(str(script))
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
    client = fake_client(make_fake_core(tmp_path, []))
    client.cancel()
    try:
        client.list_courses("user", "password", "https://moodle")
    except CoreCancelled:
        return
    raise AssertionError("expected CoreCancelled")


def make_echo_core(tmp_path: Path) -> str:
    script = tmp_path / "echo-core"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'event': 'result', 'ok': True, 'request': request}), flush=True)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


def test_duplicate_actions_send_the_output_folder(tmp_path):
    client = fake_client(make_echo_core(tmp_path))

    found = client.find_duplicates("/descargas")
    removed = client.remove_duplicates("/descargas", ["Materia/a_1.pdf"])

    assert found["request"]["action"] == "duplicates"
    assert found["request"]["output_path"] == "/descargas"
    assert removed["request"]["action"] == "remove_duplicates"
    assert removed["request"]["paths"] == ["Materia/a_1.pdf"]


def test_core_never_opens_a_console_window_on_windows(tmp_path):
    client = fake_client(make_fake_core(tmp_path, []))
    with patch("gui.core_bridge.subprocess.Popen", side_effect=OSError("stop")) as popen, \
            patch("gui.core_bridge.IS_WINDOWS", True):
        try:
            client.list_courses("user", "password", "https://moodle")
        except Exception:
            pass
    assert popen.call_args.kwargs["creationflags"] == CREATE_NO_WINDOW


def test_google_login_opens_consent_url_and_returns_session(tmp_path):
    core = make_fake_core(
        tmp_path,
        [
            {"event": "progress", "message": "Esperando"},
            {"event": "open_url", "url": "https://accounts.google.com/o/oauth2/v2/auth?x=1"},
            {"event": "result", "ok": True, "refresh_token": "RT", "email": "a@ucc.edu.ar"},
        ],
    )
    opened = []
    result = fake_client(core).google_login(open_url=opened.append)
    assert opened == ["https://accounts.google.com/o/oauth2/v2/auth?x=1"]
    assert result == {"refresh_token": "RT", "email": "a@ucc.edu.ar"}


def make_recording_core(tmp_path: Path, result: dict) -> tuple[str, Path]:
    """Fake core that saves the request it got and answers with result."""
    script = tmp_path / "recording-core"
    request_file = tmp_path / "request.json"
    script.write_text(
        "import json, sys\n"
        "request = sys.stdin.readline()\n"
        f"open({str(request_file)!r}, 'w', encoding='utf-8').write(request)\n"
        f"print({json.dumps(json.dumps(result))}, flush=True)\n",
        encoding="utf-8",
    )
    return str(script), request_file


def test_sync_sends_the_google_session(tmp_path):
    core, request_file = make_recording_core(tmp_path, {"event": "result", "ok": True, "report": {}})
    fake_client(core).sync(
        username="u", password="p", token="t", base_url="https://moodle", output_path=str(tmp_path),
        materias=[Materia("Materia", "https://moodle/12", "12")], materia_modes={},
        google_refresh_token="RT",
    )
    assert json.loads(request_file.read_text(encoding="utf-8"))["google_refresh_token"] == "RT"


def test_drive_scan_sends_courses_and_session(tmp_path):
    tree = {"scanned_at": "x", "roots": []}
    core, request_file = make_recording_core(tmp_path, {"event": "result", "ok": True, "tree": tree, "rules": {}})
    result = fake_client(core).drive_scan(
        username="u", password="p", token="t", base_url="https://moodle", output_path=str(tmp_path),
        materias=[Materia("Materia", "https://moodle/12", "12")], google_refresh_token="RT",
    )
    request = json.loads(request_file.read_text(encoding="utf-8"))
    assert request["action"] == "drive_scan"
    assert request["courses"][0]["id"] == 12
    assert request["google_refresh_token"] == "RT"
    assert result["tree"] == tree


def test_drive_state_and_selection_save(tmp_path):
    core, request_file = make_recording_core(tmp_path, {"event": "result", "ok": True, "tree": None, "rules": None})
    client = fake_client(core)
    assert client.drive_state(str(tmp_path))["ok"] is True
    assert json.loads(request_file.read_text(encoding="utf-8"))["action"] == "drive_state"
    client = fake_client(core)
    client.save_drive_selection(str(tmp_path), {"ROOT": "include"})
    request = json.loads(request_file.read_text(encoding="utf-8"))
    assert request["action"] == "drive_selection_save"
    assert request["rules"] == {"ROOT": "include"}
