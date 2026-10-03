import os
from pathlib import Path
import subprocess
import sys


def pyinstaller_command(root: Path) -> list[str]:
    core_name = "scrappy-core.exe" if os.name == "nt" else "scrappy-core"
    core_path = root / "bin" / core_name
    if not core_path.is_file():
        raise FileNotFoundError(f"Missing Go core: {core_path}. Run scripts/build_core.py first.")
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "Scrappy",
        "--add-binary",
        f"{core_path}{os.pathsep}.",
        "--hidden-import",
        "keyring.backends.chainer",
        "--hidden-import",
        "keyring.backends.fail",
        "--hidden-import",
        "keyring.backends.null",
        "--hidden-import",
        "keyring.backends.macOS",
        "--hidden-import",
        "keyring.backends.Windows",
        "--hidden-import",
        "keyring.backends.SecretService",
        "--hidden-import",
        "keyring.backends.kwallet",
        "--hidden-import",
        "backports",
        "--hidden-import",
        "backports.tarfile",
        "--collect-submodules",
        "backports",
        "main.py",
    ]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    subprocess.run(pyinstaller_command(root), cwd=root, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

