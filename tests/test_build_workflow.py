from pathlib import Path


WORKFLOW = Path(".github/workflows/build-binaries.yml")


def test_linux_smoke_test_runs_in_clean_environment() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "env -i HOME=\"$HOME\" QT_QPA_PLATFORM=offscreen packaged-check/Scrappy/Scrappy --help" in workflow


def test_linux_smoke_test_checks_backports_inside_pyinstaller_archive() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "pyi-archive_viewer packaged-check/Scrappy/Scrappy" in workflow
    assert "grep -q \"'backports'\"" in workflow
    assert "grep -q \"'backports.tarfile'\"" in workflow
