# CLAUDE.md

## Commands

```bash
go test -race ./...
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
python scripts/build_core.py
python main.py
python scripts/build_desktop.py
```

## Architecture

- `cmd/scrappy-core`: NDJSON process protocol used by the desktop UI.
- `internal/moodle`: Moodle token authentication, Web Services client, core response parsing, module-specific API enrichment, and resource deduplication.
- `internal/syncer`: deterministic paths, atomic downloads, manifest v2, and JSON/TXT reports.
- `gui`: PyQt6 presentation, keyring integration, and the Go subprocess bridge.
- `main.py`: GUI/CLI entry point; it does not scrape or download directly.

The Python UI must not regain HTTP, Selenium, parsing, manifest, or download logic. Extend the Go core and its protocol instead. Credentials and tokens belong in the JSON request over stdin, never command-line arguments or logs.
