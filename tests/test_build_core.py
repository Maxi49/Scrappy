import importlib.util
from pathlib import Path


def load_build_core():
    spec = importlib.util.spec_from_file_location("build_core", Path("scripts/build_core.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_google_credentials_are_linked_from_the_environment():
    build_core = load_build_core()
    command = build_core.go_build_command(
        Path("bin/scrappy-core"),
        {"SCRAPPY_GOOGLE_API_KEY": "KEY", "SCRAPPY_GOOGLE_CLIENT_ID": "CID", "SCRAPPY_GOOGLE_CLIENT_SECRET": "SECRET"},
    )
    flags = next(arg for arg in command if arg.startswith("-ldflags="))
    assert "-X github.com/Maxi49/Scrappy/internal/gdrive.apiKey=KEY" in flags
    assert "-X github.com/Maxi49/Scrappy/internal/gdrive.clientID=CID" in flags
    assert "-X github.com/Maxi49/Scrappy/internal/gdrive.clientSecret=SECRET" in flags
    assert flags.startswith("-ldflags=-s -w")


def test_missing_google_credentials_are_left_out():
    build_core = load_build_core()
    command = build_core.go_build_command(Path("bin/scrappy-core"), {})
    assert "-ldflags=-s -w" in command
