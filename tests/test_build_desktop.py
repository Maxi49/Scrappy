import importlib.util
import os
from pathlib import Path


def load_build_desktop_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build_desktop.py"
    spec = importlib.util.spec_from_file_location("build_desktop", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pyinstaller_command_embeds_go_core(tmp_path):
    module = load_build_desktop_module()
    core_name = "scrappy-core.exe" if os.name == "nt" else "scrappy-core"
    core = tmp_path / "bin" / core_name
    core.parent.mkdir()
    core.write_bytes(b"binary")

    command = module.pyinstaller_command(tmp_path)

    index = command.index("--add-binary")
    assert command[index + 1] == f"{core}{os.pathsep}."
    assert command[-1] == "main.py"

