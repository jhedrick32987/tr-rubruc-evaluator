"""Local file store for app state (Req 8.2). No database.

- Rubric versions: data/rubric_versions/<version_id>.json  (immutable once written)
- Drafts:          data/drafts/<event_code>.json           (in-progress review)
- Demo scenarios:  data/demo_scenarios.json                 (read-only seed)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models import DemoScenario, EvaluationSession, Rubric, RubricVersion
from app.paths import (
    DEMO_SCENARIOS_FILE,
    DRAFTS_DIR,
    RUBRIC_VERSIONS_DIR,
    SESSIONS_DIR,
    ensure_data_dirs,
)


class StoreError(Exception):
    """Raised for store-level failures (e.g., writing over an immutable version)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_version_id(event_code: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{event_code}-{stamp}"


# --------------------------------------------------------------------------- #
# Rubric versions (immutable)
# --------------------------------------------------------------------------- #
def save_version(version: RubricVersion) -> RubricVersion:
    """Write a rubric version. Refuses to overwrite an existing one (Req 3.9)."""
    ensure_data_dirs()
    path = RUBRIC_VERSIONS_DIR / f"{version.version_id}.json"
    if path.exists():
        raise StoreError(
            f"Rubric version '{version.version_id}' already exists and is immutable."
        )
    path.write_text(version.model_dump_json(indent=2), encoding="utf-8")
    return version


def make_version(
    rubric: Rubric, *, acknowledged_untraceable: bool, performance_steps
) -> RubricVersion:
    """Build a RubricVersion snapshot from a working rubric (Req 3.7, 3.8)."""
    return RubricVersion(
        version_id=_new_version_id(rubric.event_code),
        event_code=rubric.event_code,
        created_at=_now_iso(),
        task_attributes=rubric.task_attributes,
        performance_steps=performance_steps,
        provenance=rubric.provenance,
        acknowledged_untraceable=acknowledged_untraceable,
    )


def list_versions() -> list[RubricVersion]:
    """Return all saved rubric versions, newest first (Req 4.1)."""
    ensure_data_dirs()
    versions: list[RubricVersion] = []
    for path in RUBRIC_VERSIONS_DIR.glob("*.json"):
        try:
            versions.append(RubricVersion.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    versions.sort(key=lambda v: v.created_at, reverse=True)
    return versions


def get_version(version_id: str) -> RubricVersion | None:
    path = RUBRIC_VERSIONS_DIR / f"{version_id}.json"
    if not path.exists():
        return None
    try:
        return RubricVersion.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Drafts (mutable working state)
# --------------------------------------------------------------------------- #
def save_draft(rubric: Rubric) -> None:
    ensure_data_dirs()
    path = DRAFTS_DIR / f"{rubric.event_code}.json"
    path.write_text(rubric.model_dump_json(indent=2), encoding="utf-8")


def get_draft(event_code: str) -> Rubric | None:
    path = DRAFTS_DIR / f"{event_code}.json"
    if not path.exists():
        return None
    try:
        return Rubric.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def delete_draft(event_code: str) -> None:
    path = DRAFTS_DIR / f"{event_code}.json"
    path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Demo scenarios (read-only seed)
# --------------------------------------------------------------------------- #
def list_demo_scenarios() -> list[DemoScenario]:
    if not DEMO_SCENARIOS_FILE.exists():
        return []
    try:
        data = json.loads(DEMO_SCENARIOS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scenarios: list[DemoScenario] = []
    for row in data:
        try:
            scenarios.append(DemoScenario.model_validate(row))
        except ValueError:
            continue
    return scenarios


def get_demo_scenario(scenario_id: str) -> DemoScenario | None:
    for s in list_demo_scenarios():
        if s.scenario_id == scenario_id:
            return s
    return None


# --------------------------------------------------------------------------- #
# Evaluation sessions (live field scoring; mutable during a session)
# --------------------------------------------------------------------------- #
def save_session(session: EvaluationSession) -> EvaluationSession:
    ensure_data_dirs()
    path = SESSIONS_DIR / f"{session.session_id}.json"
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    return session


def get_session(session_id: str) -> EvaluationSession | None:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        return EvaluationSession.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
