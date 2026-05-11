# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Create and activate virtualenv
python -m venv venv && source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app (GUI mode when no args, CLI mode when args are passed)
python main.py
python main.py --username USER --password PASS --headless

# Run tests
python -m pytest tests/
python -m pytest tests/test_ui_warnings.py  # single test file
```

## Architecture

**Entry point:** `main.py` — detects whether to launch GUI (`gui.py`) or CLI (`scraper/navigator.py`) based on whether CLI args are present.

**Core scraping pipeline** (`scraper/`):
- `auth.py` — `MoodleAuthenticator`: handles Selenium-based login to `https://presencial.ucc.edu.ar`
- `parser.py` — `MoodleParser`: extracts course list from dashboard (AJAX-loaded) and resources from module pages via Selenium + BeautifulSoup
- `navigator.py` — `MoodleScraper`: orchestrates the full scrape; spawns 3–4 parallel browser workers (`_scrapear_lote_worker`) via `concurrent.futures`, merges results, downloads files with `requests`, and manages the per-subject manifest
- `models.py` — dataclasses: `Materia` → `Modulo` → `Recurso` (with `TipoRecurso` enum)

**Manifest system** (`output/config/manifest.json`): tracks an MD5 hash of each module's resources so unchanged modules are skipped on subsequent runs. Three scraping modes per subject: `update` (skip unchanged), `new_modules_only` (skip known modules entirely), and full re-download.

**GUI** (`gui.py`): PyQt6 app (`ScrappyGUI`). Fetches courses in a background `QThread` (`FetchMateriasWorker`), renders them in a `QListView` with checkboxes and per-item mode dropdowns, then runs the scrape in another thread.

**Config** (`utils/config.py`): `Config` class with class-level constants. Credentials come from `.env` (`UCC_USERNAME`, `UCC_PASSWORD`) or are prompted at runtime. `MODULOS_EXCLUIDOS` lists tile names to skip (accent/case-insensitive via `parser.py:normalizar_texto`).

**Output:** files downloaded to `output/<materia>/<modulo>/`; Google Drive links saved as `.url` shortcuts; results also exported to `output/recursos_encontrados.json` and `output/recursos_encontrados.txt`.

## Key Notes

- Requires Google Chrome installed; `webdriver-manager` downloads ChromeDriver automatically.
- Credentials are never stored in code — use `.env` or the GUI's keyring integration.
- `TIMEOUT` in `Config` (default 30s) controls all Selenium waits; increase for slow connections.
- `MODULOS_EXCLUIDOS` matching is accent- and case-insensitive (full tile names only, not individual resource names).
