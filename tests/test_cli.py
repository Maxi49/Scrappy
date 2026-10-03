import pytest

import main


def test_cli_does_not_accept_a_password_argument(capsys):
    # A password on the command line is visible to every process (ps) and
    # lands in shell history; it must come from UCC_PASSWORD or the prompt.
    parser = main.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--password", "secreto"])
    assert "secreto" not in capsys.readouterr().out


def test_cli_still_accepts_username_and_output():
    args = main.build_parser().parse_args(["-u", "alumno", "-o", "/tmp/destino"])
    assert args.username == "alumno"
    assert args.output == "/tmp/destino"


def test_cli_survives_a_legacy_console_encoding(monkeypatch):
    # Windows pipes default to cp1252; the banner and progress marks are not
    # encodable there. A crash in the windowed build shows a modal dialog and
    # hangs, so the CLI must degrade the characters instead.
    import io
    import sys

    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    monkeypatch.setattr(sys, "argv", ["Scrappy", "-o", "destino"])
    monkeypatch.setenv("UCC_USERNAME", "alumno")
    monkeypatch.setenv("UCC_PASSWORD", "clave")

    class FakeCore:
        def list_courses(self, *args):
            return [], "token"

        def sync(self, *, progress, **kwargs):
            progress("✓ apunte.pdf")
            return {"ok": True}

    monkeypatch.setattr(main, "CoreClient", FakeCore)
    assert main.main_cli() == 0
    stdout.flush()
    assert b"apunte.pdf" in stdout.buffer.getvalue()
