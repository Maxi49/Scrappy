import os
import platform
import shutil
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    dist_dir = project_root / "dist"
    artifacts_dir = project_root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)

    artifact_name = os.environ.get("SCRAPPY_ARTIFACT_NAME")
    if not artifact_name:
        system = platform.system().lower()
        if system == "darwin":
            artifact_name = "Scrappy-macos"
        elif system == "windows":
            artifact_name = "Scrappy-windows"
        elif system == "linux":
            artifact_name = "Scrappy-linux"
        else:
            artifact_name = f"Scrappy-{system or 'unknown'}"

    candidates = [
        dist_dir / "Scrappy.app",
        dist_dir / "Scrappy",
        dist_dir / "Scrappy.exe",
    ]
    package_root = next((path for path in candidates if path.exists()), None)
    if package_root is None:
        print("No PyInstaller output found in dist/", file=sys.stderr)
        return 1

    archive_base = artifacts_dir / artifact_name
    archive_path = shutil.make_archive(str(archive_base), "zip", package_root.parent, package_root.name)
    print(f"Created {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
