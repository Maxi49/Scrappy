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


def test_workflow_builds_and_smoke_tests_go_core() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "actions/setup-go@v5" in workflow
    assert "python scripts/build_core.py" in workflow
    assert "Contents/Frameworks/scrappy-core --version" in workflow
    assert "_internal/scrappy-core --version" in workflow


def test_go_tests_run_with_the_race_detector() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "go test -race ./..." in workflow


def test_every_packaged_app_downloads_end_to_end() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "python scripts/smoke_packaged.py packaged-check/Scrappy.app/Contents/MacOS/Scrappy" in workflow
    assert "python scripts/smoke_packaged.py packaged-check/Scrappy/Scrappy\n" in workflow
    assert "python scripts/smoke_packaged.py packaged-check/Scrappy/Scrappy.exe" in workflow


def test_core_build_receives_google_credentials_from_secrets() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for name in ("SCRAPPY_GOOGLE_API_KEY", "SCRAPPY_GOOGLE_CLIENT_ID", "SCRAPPY_GOOGLE_CLIENT_SECRET"):
        assert f"{name}: ${{{{ secrets.{name} }}}}" in workflow
