"""Configuration loading and validation (Req 5, Req 9).

The Config File is the single source of truth for rubric tiers, the competency
ladder, and the S.P.E.A.R. dimensions + definitions. S.P.E.A.R. definitions are
NEVER sourced from the corpus (Req 9); they live only here.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.paths import CONFIG_FILE


class ConfigError(Exception):
    """Raised when the Config File is missing, unparseable, or invalid.

    The message is safe to surface directly in the UI.
    """


class RubricTier(BaseModel):
    name: str
    value: int


class SpearDimension(BaseModel):
    name: str
    definition: str


class AppConfig(BaseModel):
    rubric_tiers: list[RubricTier]
    competency_levels: list[str]
    spear_dimensions: list[SpearDimension]


def _load_raw(path: Path) -> dict:
    if not path.exists():
        # Req 5.6 — missing file.
        raise ConfigError(
            f"Configuration could not be loaded: file not found at {path.name}."
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - unusual IO failure
        raise ConfigError(
            f"Configuration could not be loaded: unable to read {path.name} ({exc})."
        ) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # Req 5.6 — unparseable file.
        raise ConfigError(
            f"Configuration could not be loaded: {path.name} is not valid JSON "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(
            "Configuration could not be loaded: top-level JSON must be an object."
        )
    return data


def load_config(path: Path = CONFIG_FILE) -> AppConfig:
    """Load and validate the Config File.

    Raises ConfigError with a UI-safe message for:
      - missing / unparseable file (Req 5.6)
      - missing spear_dimensions -> S.P.E.A.R. required (Req 9.4)
      - empty rubric_tiers / competency_levels / spear_dimensions (Req 5.7)
    """
    data = _load_raw(path)

    # Req 9.4 — S.P.E.A.R. must be present. Checked before generic validation so
    # the message is specific to the S.P.E.A.R. boundary.
    if "spear_dimensions" not in data:
        raise ConfigError(
            "S.P.E.A.R. configuration is required: 'spear_dimensions' is missing "
            "from the Config File."
        )

    try:
        config = AppConfig.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ())) or "config"
        raise ConfigError(
            f"Configuration could not be loaded: invalid field '{loc}' "
            f"({first.get('msg', 'invalid value')})."
        ) from exc

    # Req 5.7 — empty/zero-length sections, named explicitly.
    empty_sections = [
        section
        for section, values in (
            ("rubric_tiers", config.rubric_tiers),
            ("competency_levels", config.competency_levels),
            ("spear_dimensions", config.spear_dimensions),
        )
        if len(values) == 0
    ]
    if empty_sections:
        raise ConfigError(
            "Invalid configuration: the following section(s) must not be empty: "
            + ", ".join(empty_sections)
            + "."
        )

    return config


@lru_cache(maxsize=1)
def _cached_config() -> AppConfig:
    return load_config()


def get_config(*, fresh: bool = False) -> AppConfig:
    """Return the app config.

    By default returns a cached instance; pass fresh=True to re-read from disk
    (useful when editing config.json live during a demo).
    """
    if fresh:
        _cached_config.cache_clear()
    return _cached_config()
