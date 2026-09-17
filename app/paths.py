"""Central path constants for the T&R Rubric Evaluation Generator.

Every filesystem location the app depends on is defined here so a relocation
is a single-edit change (Req 8, design "Assumptions").
"""
from __future__ import annotations

from pathlib import Path

# Project root = the directory containing this app/ package's parent.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The verified corpus root (read-only). The app never writes here.
CORPUS_ROOT = PROJECT_ROOT / "corpus" / "work" / "fireteam-forge-corpus"

# Corpus sub-locations used by the app (design "Verified corpus facts").
EVENTS_INDEX = CORPUS_ROOT / "machine_indexes" / "events.json"
STRUCTURED_EVENTS_DIR = CORPUS_ROOT / "07_structured_infantry_events"

# Local, writable application state (Req 8.2). No database.
DATA_DIR = PROJECT_ROOT / "data"
RUBRIC_VERSIONS_DIR = DATA_DIR / "rubric_versions"
DRAFTS_DIR = DATA_DIR / "drafts"
SESSIONS_DIR = DATA_DIR / "sessions"
DEMO_SCENARIOS_FILE = DATA_DIR / "demo_scenarios.json"

# Runtime-editable model provider settings (Settings page). May contain an API
# key; never committed (see .gitignore).
MODEL_SETTINGS_FILE = DATA_DIR / "model_settings.json"

# Hand-written few-shot example rubrics (Req 2.1).
EXAMPLES_DIR = PROJECT_ROOT / "examples"

# The single local configuration file (Req 5.4).
CONFIG_FILE = PROJECT_ROOT / "config.json"

# UI assets.
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"


def ensure_data_dirs() -> None:
    """Create the writable data directories if they do not yet exist."""
    for d in (DATA_DIR, RUBRIC_VERSIONS_DIR, DRAFTS_DIR, SESSIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)
