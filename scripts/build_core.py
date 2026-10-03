import os
from pathlib import Path
import subprocess


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    bin_dir = root / "bin"
    bin_dir.mkdir(exist_ok=True)
    name = "scrappy-core.exe" if os.name == "nt" else "scrappy-core"
    destination = bin_dir / name
    subprocess.run(
        ["go", "build", "-trimpath", "-ldflags=-s -w", "-o", str(destination), "./cmd/scrappy-core"],
        cwd=root,
        check=True,
    )
    print(f"Built {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

