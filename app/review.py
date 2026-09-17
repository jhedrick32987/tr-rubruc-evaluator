"""Review and versioning service (Req 3).

Operates on a working Rubric draft whose structure is
Rubric -> performance_steps[] -> metrics[]. Supports inline edit, per-metric
approve/reject, and a lock operation with a SOFT step-derivation gate
(design Correctness Property 5): metrics not derived from a performance step
must be acknowledged before locking.
"""
from __future__ import annotations

from app.models import (
    KSTStatus,
    ObservableMetric,
    PerformanceStepBlock,
    Rubric,
    RubricVersion,
    Traceable,
)
from app import store


class ReviewError(Exception):
    """Raised when a review action is invalid (e.g., locking past an unacknowledged flag)."""


EDITABLE_FIELDS = {"statement", "competency_level", "spear_dimension"}


def _metric_at(rubric: Rubric, step_index: int, metric_index: int) -> ObservableMetric:
    if not (0 <= step_index < len(rubric.performance_steps)):
        raise ReviewError("Step index out of range.")
    step = rubric.performance_steps[step_index]
    if not (0 <= metric_index < len(step.metrics)):
        raise ReviewError("Metric index out of range.")
    return step.metrics[metric_index]


def edit_metric(
    rubric: Rubric, step_index: int, metric_index: int, field: str, value: str
) -> Rubric:
    """Inline-edit a metric field or a per-tier anchor (Req 3.2).

    `field` is a metric field (statement, competency_level, spear_dimension) or
    "anchor:<TierName>" to edit the behavioral anchor for a specific tier.
    """
    metric = _metric_at(rubric, step_index, metric_index)
    if field.startswith("anchor:"):
        tier = field.split(":", 1)[1]
        if tier not in metric.anchors:
            raise ReviewError(f"Tier '{tier}' is not part of this metric.")
        metric.anchors[tier] = value
    elif field in EDITABLE_FIELDS:
        setattr(metric, field, value)
    else:
        raise ReviewError(f"Field '{field}' is not editable.")
    return rubric


def set_metric_status(
    rubric: Rubric, step_index: int, metric_index: int, status: KSTStatus
) -> Rubric:
    """Approve or reject a single metric (Req 3.3)."""
    _metric_at(rubric, step_index, metric_index).status = status
    return rubric


def not_step_derived(rubric: Rubric) -> list[ObservableMetric]:
    """Non-rejected metrics not derived from a step — must be acknowledged (Req 3.5)."""
    return [
        m
        for m in rubric.all_metrics()
        if m.status != KSTStatus.rejected and m.step_derived == Traceable.no
    ]


def lock(rubric: Rubric, *, acknowledged: bool) -> RubricVersion:
    """Lock a rubric into an immutable version (Req 3.5-3.9).

    - If any non-rejected metric is not step-derived and `acknowledged` is False,
      refuse (soft gate; Req 3.5, 3.6).
    - Rejected metrics are excluded from the version (Req 3.7).
    - The resulting version is immutable once saved (Req 3.9).
    """
    if not_step_derived(rubric) and not acknowledged:
        raise ReviewError(
            "This rubric contains observable metrics that are not derived from a "
            "performance step. Acknowledge them explicitly before locking."
        )

    kept_steps: list[PerformanceStepBlock] = []
    for step in rubric.performance_steps:
        kept = [m for m in step.metrics if m.status != KSTStatus.rejected]
        if kept:
            kept_steps.append(
                PerformanceStepBlock(
                    step_number=step.step_number,
                    step_text=step.step_text,
                    metrics=kept,
                )
            )

    if not any(s.metrics for s in kept_steps):
        raise ReviewError("Cannot lock a rubric with no approved metrics.")

    version = store.make_version(
        rubric,
        acknowledged_untraceable=bool(not_step_derived(rubric)),
        performance_steps=kept_steps,
    )
    store.save_version(version)
    store.delete_draft(rubric.event_code)
    return version
