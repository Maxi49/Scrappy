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
