"""Evaluate stage — live/field scoring (Req 4).

The human evaluator scores the squad against an approved rubric version while
observing the attack. Two ways to fill in a score:

  - Tap the tier a metric earns directly on a tablet (`record_score`) —
    always the scorer of record.
  - Speak or type a narrative of the observed performance and let the model
    suggest a tier per metric (`score_from_narrative`), pre-filling the
    checklist so the evaluator reviews/confirms or overrides each tap instead
    of starting from a blank sheet. This is for the audio field-scoring
    feature: recorded observation audio is transcribed elsewhere
    (`app.model_client.transcribe_audio`) and handed to this function as text.

Auto-suggested scores are tagged `source="auto"` on their `MetricScore` and
stay provisional until a human taps a tier (which sets `source="human"`) —
the model never gets to be the scorer of record, consistent with the app's
"flag, don't hide" approach to anything AI-generated. The provenance caveat
travels with every session (Req 4.7).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.config import AppConfig, get_config
from app.model_client import generate_structured
from app.models import EvaluationScoring, EvaluationSession, MetricScore, RubricVersion
from app.prompts import build_evaluate_prompt
from app.provenance import provenance_caveat
from app import store


class EvaluateError(Exception):
    """Raised for evaluate-stage problems (e.g., no approved rubric). UI-safe."""


def list_versions() -> list[RubricVersion]:
    """Approved rubric versions available for scoring (Req 4.1)."""
    return store.list_versions()


def start_session(version_id: str, unit_label: str = "") -> EvaluationSession:
    """Create a field scoring session from an approved rubric version (Req 4.1, 4.2).

    Raises EvaluateError if no approved rubric exists / the version is unknown.
    """
    if not store.list_versions():
        raise EvaluateError("An approved rubric is required before evaluation.")  # Req 4.8
    version = store.get_version(version_id)
    if version is None:
        raise EvaluateError(f"Approved rubric version '{version_id}' was not found.")

    scores = [
        MetricScore(
            metric_id=m.metric_id,
            step_ref=m.step_ref,
            spear_dimension=m.spear_dimension,
            tier_awarded=None,
        )
        for m in version.all_metrics()
    ]
    session = EvaluationSession(
        session_id=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        rubric_version_id=version.version_id,
        event_code=version.event_code,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        unit_label=unit_label,
        scores=scores,
        provenance_caveat=provenance_caveat(version.provenance),
    )
    store.save_session(session)
    return session


def record_score(
    session_id: str, metric_id: str, tier_awarded: str, note: str = ""
) -> EvaluationSession:
    """Record the evaluator's tier selection for one metric (Req 4.4, 4.5)."""
    session = store.get_session(session_id)
    if session is None:
        raise EvaluateError(f"Scoring session '{session_id}' was not found.")
    for s in session.scores:
        if s.metric_id == metric_id:
            s.tier_awarded = tier_awarded
            s.source = "human"
            if note:
                s.note = note
            break
    else:
        raise EvaluateError(f"Metric '{metric_id}' is not part of this session.")
    store.save_session(session)
    return session


def score_from_narrative(
    session_id: str, narrative: str, config: AppConfig | None = None
) -> EvaluationSession:
    """Auto-fill tier awards from a free-text (or transcribed-audio) narrative.

    Calls the model with the session's locked rubric + narrative, then applies
    each returned tier award as a `MetricScore(source="auto")`. A metric the
    model doesn't mention is left as-is. Raises EvaluateError if the session or
    its rubric version is missing, or ModelError/ModelParseError on model
    failure (surfaced the same way generation failures are elsewhere).
    """
    if not narrative.strip():
        raise EvaluateError("A performance narrative is required to auto-score.")
    session = store.get_session(session_id)
    if session is None:
        raise EvaluateError(f"Scoring session '{session_id}' was not found.")
    version = store.get_version(session.rubric_version_id)
    if version is None:
        raise EvaluateError("The rubric version for this session is missing.")

    config = config or get_config()
    system, user = build_evaluate_prompt(version, narrative, config)
    result: EvaluationScoring = generate_structured(system, user, EvaluationScoring)

    by_id = {s.metric_id: s for s in session.scores}
    for scored in result.scores:
        target = by_id.get(scored.metric_id)
        if target is None:
            continue  # model referenced an unknown metric id; ignore rather than invent one
        target.tier_awarded = scored.tier_awarded
        target.source = "auto"
        if scored.rationale:
            target.note = scored.rationale
    session.auto_summary = result.summary
    store.save_session(session)
    return session


def summarize(session: EvaluationSession, tier_values: dict[str, int]) -> dict:
    """Compute a simple roll-up over scored metrics (Req 4.6).

    tier_values maps tier name -> numeric value (from config). Returns counts per
    tier, per-dimension averages, and an overall average across scored metrics.
    """
    scored = [s for s in session.scores if s.tier_awarded]
    tier_counts: dict[str, int] = {}
    dim_totals: dict[str, list[int]] = {}
    total = 0
    for s in scored:
        tier_counts[s.tier_awarded] = tier_counts.get(s.tier_awarded, 0) + 1
        val = tier_values.get(s.tier_awarded, 0)
        total += val
        dim_totals.setdefault(s.spear_dimension, []).append(val)
    overall = round(total / len(scored), 2) if scored else 0.0
    dim_avg = {d: round(sum(v) / len(v), 2) for d, v in dim_totals.items()}
    return {
        "scored": len(scored),
        "total_metrics": len(session.scores),
        "tier_counts": tier_counts,
        "dimension_averages": dim_avg,
        "overall_average": overall,
    }
