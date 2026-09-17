"""Corpus service: the ONLY source of doctrinal source text (Req 1, Req 10).

Integrity guarantees enforced here (design Correctness Properties 1 and 3):
  - The task list comes from machine_indexes/events.json only (Req 1.1, 1.2).
  - A record is loaded by EXACT `file`-field lookup into
    07_structured_infantry_events/ — never search/keyword/fuzzy/vector (Req 1.4, 1.5).
  - Only NAVMC 3500.44D events are selectable, checked against the record's
    source_publication front matter (Req 1.3).
  - This module reads ONLY the events index and the structured-events folder.
    It never reads 00_project_context/ or any S.P.E.A.R. material (Req 9, Req 10.3).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

import frontmatter

from app.models import EventIndexEntry, EventRecord, GroundingFields
from app.paths import EVENTS_INDEX, STRUCTURED_EVENTS_DIR

ALLOWED_SOURCE_PUBLICATION = "NAVMC 3500.44D"


class CorpusError(Exception):
    """Raised when the corpus index or a record cannot be loaded. UI-safe message."""


@lru_cache(maxsize=1)
def _load_index() -> list[EventIndexEntry]:
    if not EVENTS_INDEX.exists():
        raise CorpusError(
            f"Event Index could not be loaded: {EVENTS_INDEX.name} not found."
        )
    try:
        data = json.loads(EVENTS_INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(
            f"Event Index could not be loaded: {EVENTS_INDEX.name} is not valid JSON."
        ) from exc
    if not isinstance(data, list):
        raise CorpusError("Event Index could not be loaded: expected a JSON array.")
    entries: list[EventIndexEntry] = []
    for row in data:
        try:
            entries.append(EventIndexEntry.model_validate(row))
        except Exception:  # noqa: BLE001 - skip malformed rows, keep the demo running
            continue
    return entries


def list_index_entries() -> list[EventIndexEntry]:
    """Return every Event Index entry (unfiltered). Selector filtering is separate."""
    return list(_load_index())


def _record_path(entry: EventIndexEntry):
    """Resolve the exact record path from the index `file` field (Req 1.4)."""
    return STRUCTURED_EVENTS_DIR / entry.file


_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _split_sections(body: str) -> dict[str, str]:
    """Split a record body into {lowercased H2 heading: text} (Req 2.1)."""
    sections: dict[str, str] = {}
    matches = list(_H2.finditer(body))
    for i, m in enumerate(matches):
        heading = m.group(1).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[heading] = body[start:end].strip()
    return sections


def _parse_record(entry: EventIndexEntry) -> EventRecord:
    path = _record_path(entry)
    if not path.exists():
        # Req 1.6 — referenced file missing.
        raise CorpusError(
            f"The source record could not be loaded: file '{entry.file}' was not found."
        )
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        raise CorpusError(
            f"The source record could not be loaded: '{entry.file}' could not be read."
        ) from exc

    meta = post.metadata
    sections = _split_sections(post.content)

    def _clean(text: str) -> str:
        # Corpus uses "_No text extracted._" as a placeholder; treat as empty.
        return "" if text.strip().lower() == "_no text extracted._" else text.strip()

    # Maneuver tasks (e.g. INF-MAN-4001) use "Event Components" (nested phases);
    # individual tasks (e.g. 0300-CMBH-1001) use "Performance Steps" (flat list).
    # Prefer whichever is present so the checklist backbone is populated (Req 2.2).
    steps_text = _clean(sections.get("performance steps", "")) or _clean(
        sections.get("event components", "")
    )
    grounding = GroundingFields(
        condition=_clean(sections.get("condition", "")),
        standard=_clean(sections.get("standard", "")),
        performance_steps=steps_text,
    )

    return EventRecord(
        event_code=str(meta.get("event_code", entry.event_code)),
        title=str(meta.get("title", entry.title)),
        functional_area=meta.get("functional_area"),
        event_level=meta.get("event_level"),
        source_publication=meta.get("source_publication"),
        source_date=meta.get("source_date"),
        source_currency=meta.get("source_currency"),
        classification=meta.get("classification"),
        grounding_fields=grounding,
        primary_reference=_clean(sections.get("primary reference", "")) or None,
    )


@lru_cache(maxsize=None)
def load_record(event_code: str) -> EventRecord:
    """Load a Structured Event Record by exact index reference (Req 1.4, 1.5).

    Raises CorpusError if the event_code is unknown, the record file is missing,
    or the event is not sourced from NAVMC 3500.44D (Req 1.3, 1.6).
    """
    index = {e.event_code: e for e in _load_index()}
    entry = index.get(event_code)
    if entry is None:
        raise CorpusError(
            f"The source record could not be loaded: unknown event '{event_code}'."
        )
    record = _parse_record(entry)

    # Req 1.3 — restrict to NAVMC 3500.44D, evaluated against record front matter.
    if (record.source_publication or "").strip() != ALLOWED_SOURCE_PUBLICATION:
        raise CorpusError(
            f"Event '{event_code}' is not sourced from {ALLOWED_SOURCE_PUBLICATION} "
            "and is out of scope for this build."
        )
    return record


@lru_cache(maxsize=1)
def list_tasks() -> list[EventIndexEntry]:
    """Return the selectable T&R task list (Req 1.1, 1.2, 1.3).

    Restricted to NAVMC 3500.44D events. The restriction is evaluated against each
    record's source_publication front matter, since the index does not carry it.
    Records that cannot be loaded are omitted rather than breaking the list.
    Cached so the one-time parse cost is not repeated per request.
    """
    selectable: list[EventIndexEntry] = []
    for entry in _load_index():
        try:
            record = _parse_record(entry)
        except CorpusError:
            continue
        if (record.source_publication or "").strip() == ALLOWED_SOURCE_PUBLICATION:
            selectable.append(entry)
    return selectable
