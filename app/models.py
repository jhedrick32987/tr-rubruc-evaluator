"""Core data models (Req 2, 3, 4).

These Pydantic models define the fixed shapes used across the app:
  - the Event Index entry and Structured Event Record (corpus, read-only)
  - the Rubric Schema (KST) produced by generation
  - the immutable Rubric Version produced on lock
  - the Evaluation Result produced by scoring

The Model_Client validates model output against RubricGeneration / EvaluationResult,
so partially-valid data never reaches the UI (design "Interface contracts").
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- #
# Corpus (read-only) models
# --------------------------------------------------------------------------- #
class EventIndexEntry(BaseModel):
    """One entry in machine_indexes/events.json (verified fields)."""
    event_code: str
    title: str
    functional_area: Optional[str] = None
    event_level: Optional[str] = None
    file: str
    has_condition: bool = False
    has_standard: bool = False
    has_components_or_steps: bool = False


class GroundingFields(BaseModel):
    """The labeled sections used as source text and step-derivation basis (Req 2.1)."""
    condition: str = ""
    standard: str = ""
    performance_steps: str = ""

    def as_source_text(self) -> str:
        return (
            f"Condition:\n{self.condition}\n\n"
            f"Standard:\n{self.standard}\n\n"
            f"Performance Steps:\n{self.performance_steps}"
        ).strip()

    def numbered_steps(self) -> list[tuple[int, str]]:
        """Parse the steps text into an ordered [(number, text)] checklist (Req 2.2).

        Handles two corpus formats:
          - Flat "Performance Steps": "1. Do X 2. Do Y 3. Do Z" (individual tasks).
          - Nested "Event Components": "1. Phase a. sub b. sub 2. Phase a. sub ..."
            (maneuver tasks like INF-MAN-4001). Nested sub-steps are flattened into
            an ordered checklist, each labeled with its phase, e.g.
            "Preparation for the attack — Movement to the assembly area".

        Returns a single re-numbered ordered list suitable for a checklist backbone.
        """
        import re as _re

        text = (self.performance_steps or "").strip()
        if not text:
            return []

        # Split into top-level numbered blocks: "1. ... 2. ... 3. ...".
        num_tokens = _re.split(r"(?:^|\s)(\d+)\.\s+", text)
        blocks: list[tuple[int, str]] = []
        i = 1
        while i < len(num_tokens):
            if num_tokens[i].isdigit() and i + 1 < len(num_tokens):
                blocks.append((int(num_tokens[i]), num_tokens[i + 1].strip()))
                i += 2
            else:
                i += 1

        if not blocks:
            return [(1, text)]

        checklist: list[tuple[int, str]] = []
        seq = 0
        for _, body in blocks:
            # A block may be "Phase title a. sub b. sub ..." — split on letter markers.
            letter_split = _re.split(r"(?:^|\s)([a-z])\.\s+", body)
            phase_title = letter_split[0].strip().rstrip(".")
            subs: list[str] = []
            j = 1
            while j < len(letter_split):
                if _re.fullmatch(r"[a-z]", letter_split[j]) and j + 1 < len(letter_split):
                    subs.append(letter_split[j + 1].strip())
                    j += 2
                else:
                    j += 1
            if subs:
                for sub in subs:
                    seq += 1
                    checklist.append((seq, f"{phase_title} — {sub}"))
            else:
                seq += 1
                checklist.append((seq, phase_title))
        return checklist


class EventRecord(BaseModel):
    """A parsed Structured Event Record: front matter + Grounding Fields."""
    event_code: str
    title: str
    functional_area: Optional[str] = None
    event_level: Optional[str] = None
    source_publication: Optional[str] = None
    source_date: Optional[str] = None
    source_currency: Optional[str] = None
    classification: Optional[str] = None
    grounding_fields: GroundingFields = Field(default_factory=GroundingFields)
    # The full extracted Task Attributes header text, for display (Req 2.8).
    primary_reference: Optional[str] = None


# --------------------------------------------------------------------------- #
# Rubric Schema (generation output, Req 2.2, 2.8)
#
# Structure mirrors a BARS S.P.E.A.R. rubric:
#   Rubric -> dimensions[] -> criteria[] -> anchors{tier: text}
# Each criterion is the atomic KST unit: a statement organized under one S.P.E.A.R.
# dimension, tagged with a competency level, with one behavioral anchor per tier,
# and a single traceability judgment against the source (Req 2.2-2.7).
# --------------------------------------------------------------------------- #
class Traceable(str, Enum):
    yes = "yes"
    no = "no"


class TraceableToSource(BaseModel):
    traceable: Traceable
    supporting_excerpt: Optional[str] = None


class KSTStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ObservableMetric(BaseModel):
    """One observable metric derived from a performance step (Req 2.3-2.7).

    S.P.E.A.R. is the lens (spear_dimension) through which the metric views its
    step. Carries one behavioral anchor per rubric tier, keyed by tier name.
    step_ref is the Performance Step number it derives from; step_derived flags
    whether it could be tied to a step at all.
    """
    metric_id: str
    statement: str
    spear_dimension: str
    competency_level: str
    step_ref: Optional[int] = None
    anchors: dict[str, str]  # { tier_name: behavioral anchor text }
    step_derived: Traceable
    # Review state (app-managed, not model-generated; Req 3.3).
    status: KSTStatus = KSTStatus.pending


class PerformanceStepBlock(BaseModel):
    """A performance step and the observable metrics generated for it (Req 2.2, 2.8)."""
    step_number: int
    step_text: str
    metrics: list[ObservableMetric]


class TaskAttributes(BaseModel):
    """Reference-rubric header shape (Req 2.8).

    Model output sometimes returns list-valued fields (e.g. key_performance_steps
    as an array of steps). A validator coerces any list/None to a clean string so
    generation does not fail on a cosmetic shape difference.
    """
    tr_code: str = ""
    echelon: Optional[str] = None
    sustainment_interval: Optional[str] = None
    condition: Optional[str] = None
    standard: Optional[str] = None
    key_performance_steps: Optional[str] = None
    reference: Optional[str] = None

    @field_validator(
        "tr_code",
        "echelon",
        "sustainment_interval",
        "condition",
        "standard",
        "key_performance_steps",
        "reference",
        mode="before",
    )
    @classmethod
    def _coerce_to_string(cls, v):
        if v is None:
            return v
        if isinstance(v, list):
            return "; ".join(str(x) for x in v)
        if isinstance(v, (int, float)):
            return str(v)
        return v


class Provenance(BaseModel):
    source_publication: Optional[str] = None
    source_date: Optional[str] = None
    source_currency: Optional[str] = None


class RubricGeneration(BaseModel):
    """The schema the model must return for Design-stage generation (Req 2.2, 2.8)."""
    task_attributes: TaskAttributes
    performance_steps: list[PerformanceStepBlock]


class Rubric(BaseModel):
    """A working (pre-lock) rubric for a task, plus provenance for display."""
    event_code: str
    task_attributes: TaskAttributes
    performance_steps: list[PerformanceStepBlock]
    provenance: Provenance

    def all_metrics(self) -> list[ObservableMetric]:
        return [m for s in self.performance_steps for m in s.metrics]


# --------------------------------------------------------------------------- #
# Rubric Version (immutable snapshot on lock, Req 3.7-3.9)
# --------------------------------------------------------------------------- #
class RubricVersion(BaseModel):
    version_id: str
    event_code: str
    created_at: str
    task_attributes: TaskAttributes
    performance_steps: list[PerformanceStepBlock]  # rejected metrics excluded at lock (Req 3.7)
    provenance: Provenance
    acknowledged_untraceable: bool = False

    def all_metrics(self) -> list[ObservableMetric]:
        return [m for s in self.performance_steps for m in s.metrics]


# --------------------------------------------------------------------------- #
# Field scoring session — the human evaluator taps a tier per metric on a tablet
# while observing the squad perform each step (Req 4).
# --------------------------------------------------------------------------- #
class MetricScore(BaseModel):
    """One score for a metric during a live evaluation.

    `source` distinguishes a human tap from a model suggestion pre-filled by
    narrative/audio auto-scoring, so the UI can flag it as provisional until a
    human confirms or overrides it — the app never lets an auto-score pass as
    a human judgment silently. Old session files without this field default
    to "human" (they predate the auto-scoring feature).
    """
    metric_id: str
    step_ref: Optional[int] = None
    spear_dimension: str
    tier_awarded: Optional[str] = None  # None until scored
    note: str = ""
    source: str = "human"  # "human" | "auto"


class EvaluationSession(BaseModel):
    """A live/field scoring session against an approved rubric version (Req 4)."""
    session_id: str
    rubric_version_id: str
    event_code: str
    created_at: str
    unit_label: str = ""  # e.g. "1st Squad, 2d Plt"
    scores: list[MetricScore]
    provenance_caveat: str
    # Plain-language summary from the most recent narrative/audio auto-score
    # pass, if any (Req 4.6, extended). Empty until score_from_narrative runs.
    auto_summary: str = ""

    def scored_count(self) -> int:
        return sum(1 for s in self.scores if s.tier_awarded)


class ScoredMetric(BaseModel):
    """One model-suggested tier award, from narrative/audio auto-scoring."""
    metric_id: str
    spear_dimension: Optional[str] = None
    step_ref: Optional[int] = None
    tier_awarded: str
    rationale: Optional[str] = None


class EvaluationScoring(BaseModel):
    """The schema the model must return for narrative/audio auto-scoring.

    Matches the schema_hint in `app.prompts.build_evaluate_prompt`. The model
    proposes a tier per metric plus a plain-language summary; these are
    applied as MetricScore(source="auto") entries for the human evaluator to
    confirm or override (Req 4.4-4.6, extended for the audio field-scoring
    feature).
    """
    scores: list[ScoredMetric]
    summary: str = ""


class DemoScenario(BaseModel):
    scenario_id: str
    title: str
    description: str
