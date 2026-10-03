import os
from pathlib import Path
import subprocess

GDRIVE_PACKAGE = "github.com/Maxi49/Scrappy/internal/gdrive"
# Google credentials come from the environment (GitHub secrets in CI) so they
# never live in the repository.
GOOGLE_CREDENTIALS = {
    "SCRAPPY_GOOGLE_API_KEY": "apiKey",
    "SCRAPPY_GOOGLE_CLIENT_ID": "clientID",
    "SCRAPPY_GOOGLE_CLIENT_SECRET": "clientSecret",
}


def go_build_command(destination: Path, environ) -> list[str]:
    flags = ["-s", "-w"]
    for env_name, variable in GOOGLE_CREDENTIALS.items():
        value = environ.get(env_name, "").strip()
        if value:
            flags.append(f"-X {GDRIVE_PACKAGE}.{variable}={value}")
    return ["go", "build", "-trimpath", "-ldflags=" + " ".join(flags), "-o", str(destination), "./cmd/scrappy-core"]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    bin_dir = root / "bin"
    bin_dir.mkdir(exist_ok=True)
    name = "scrappy-core.exe" if os.name == "nt" else "scrappy-core"
    destination = bin_dir / name
    subprocess.run(go_build_command(destination, os.environ), cwd=root, check=True)
    missing = [env for env in GOOGLE_CREDENTIALS if not os.environ.get(env, "").strip()]
    if missing:
        print(f"Aviso: sin {', '.join(missing)}; Google Drive queda deshabilitado en este build.")
    print(f"Built {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
