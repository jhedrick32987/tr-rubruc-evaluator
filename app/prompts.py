"""Prompt construction for Design and Evaluate stages.

S.P.E.A.R. dimensions/definitions and the BARS tier scaffold are drawn ONLY from
the Config File (Req 9). The only doctrinal source text is the selected event's
Grounding Fields (Req 2.1, Req 10). Few-shot examples are hand-written rubrics.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import AppConfig
from app.models import EventRecord, RubricVersion
from app.paths import EXAMPLES_DIR


def _spear_block(config: AppConfig) -> str:
    lines = ["S.P.E.A.R. DIMENSIONS (from configuration — do not infer from source text):"]
    for d in config.spear_dimensions:
        lines.append(f"- {d.name}: {d.definition}")
    return "\n".join(lines)


def _tier_block(config: AppConfig) -> str:
    tiers = ", ".join(f"{t.name} ({t.value})" for t in config.rubric_tiers)
    return f"RUBRIC TIERS (BARS, from configuration): {tiers}"


def _ladder_block(config: AppConfig) -> str:
    return "COMPETENCY LEVELS (from configuration): " + ", ".join(config.competency_levels)


def _load_few_shots(limit: int = 2) -> list[dict]:
    examples: list[dict] = []
    for path in sorted(EXAMPLES_DIR.glob("example_rubric_*.json")):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data.pop("_note", None)
        examples.append(data)
        if len(examples) >= limit:
            break
    return examples


DESIGN_SYSTEM = (
    "You are an instructional-design assistant that writes Marine Corps Training "
    "& Readiness performance rubrics using the BARS (Behaviorally Anchored Rating "
    "Scale) methodology. You ground every behavioral anchor in the provided source "
    "standard text. You NEVER invent standards, tactics, or S.P.E.A.R. definitions. "
    "If the source does not clearly support an anchor, you set traceable_to_source "
    "to \"no\" and leave supporting_excerpt null. You respond with a single valid "
    "JSON object matching the requested schema and nothing else."
)


def build_design_prompt(record: EventRecord, config: AppConfig) -> tuple[str, str]:
    """Build (system, user) prompts for step-anchored generation (Req 2.1-2.7, 9.3)."""
    few_shots = _load_few_shots()
    few_shot_text = ""
    if few_shots:
        few_shot_text = (
            "\n\nEXAMPLE RUBRIC (format reference; ground your own output in THIS "
            "task's performance steps, not this example):\n"
            + "\n".join(json.dumps(ex, ensure_ascii=False) for ex in few_shots)
        )

    tier_names = [t.name for t in config.rubric_tiers]
    dim_names = [d.name for d in config.spear_dimensions]

    steps = record.grounding_fields.numbered_steps()
    steps_block = "\n".join(f"  Step {n}: {t}" for n, t in steps) or "  (no performance steps found)"

    schema_hint = (
        '{"task_attributes": {"tr_code","echelon","sustainment_interval","condition",'
        '"standard","key_performance_steps","reference"}, '
        '"performance_steps": [{"step_number": <int>, "step_text": "<the step>", '
        '"metrics": [{"metric_id": "<short id>", "statement": "<observable metric for this step>", '
        '"spear_dimension": "<one S.P.E.A.R. dimension name>", '
        '"competency_level": "<one competency level>", "step_ref": <the step_number>, '
        '"anchors": {' + ", ".join(f'"{t}": "<anchor for {t}>"' for t in tier_names) + "}, "
        '"step_derived": "yes"}]}]}'
    )

    user = f"""Generate a performance rubric for this T&R task. The task's PERFORMANCE STEPS are
the backbone of the rubric. S.P.E.A.R. is only a lens for phrasing legitimate observable
metrics — it is NOT the organizing structure.

TASK CODE: {record.event_code}
TITLE: {record.title}

CONDITION: {record.grounding_fields.condition}
STANDARD: {record.grounding_fields.standard}

PERFORMANCE STEPS (the source of truth — build the rubric around these):
{steps_block}

{_spear_block(config)}

{_tier_block(config)}

{_ladder_block(config)}

INSTRUCTIONS:
- Produce one performance_steps entry for EACH numbered Performance Step above, preserving its
  step_number and step_text exactly.
- For each Performance Step, generate 1-2 Observable Metrics that describe what an evaluator
  would observe to judge that specific step. Each metric's statement must be tied to its step.
- Tag each metric with exactly one S.P.E.A.R. dimension (from the list above) that best fits how
  you would observe that step. Use S.P.E.A.R. as the lens for phrasing the metric, not as a
  category to fill. Different steps may use different dimensions; not every dimension must appear.
- Tag each metric with one competency level from the list above.
- For each metric, set step_ref to the step_number it derives from, and set step_derived to "yes".
- If (and only if) you must write a metric that does not correspond to any Performance Step, set
  step_derived to "no" and step_ref to null. Prefer step-derived metrics; do not invent metrics
  unrelated to the steps.
- For each metric, provide one behavioral anchor for EVERY rubric tier ({", ".join(tier_names)}),
  keyed by the exact tier name, describing escalating observable behavior for that step.
- Populate task_attributes from the source where available; leave unknown fields empty.

S.P.E.A.R. dimensions available as lenses ({len(dim_names)}): {", ".join(dim_names)}

Respond with a single JSON object of this shape:
{schema_hint}{few_shot_text}"""
    return DESIGN_SYSTEM, user


EVALUATE_SYSTEM = (
    "You are an evaluator scoring an observed Marine performance against an approved "
    "T&R rubric using its BARS tiers. You assign each rubric KST the tier best "
    "supported by the performance description, with a short rationale, then write a "
    "plain-language summary an evaluator could hand to a commander. You respond with "
    "a single valid JSON object matching the requested schema and nothing else."
)


def build_evaluate_prompt(
    version: RubricVersion, performance_description: str, config: AppConfig
) -> tuple[str, str]:
    """Build (system, user) prompts for Evaluate-stage scoring (Req 4.4)."""
    rubric_json = json.dumps(
        {
            "event_code": version.event_code,
            "performance_steps": [
                {
                    "step_number": s.step_number,
                    "step_text": s.step_text,
                    "metrics": [
                        {
                            "metric_id": m.metric_id,
                            "statement": m.statement,
                            "spear_dimension": m.spear_dimension,
                            "anchors": m.anchors,
                        }
                        for m in s.metrics
                    ],
                }
                for s in version.performance_steps
            ],
        },
        ensure_ascii=False,
    )
    schema_hint = (
        '{"scores": [{"metric_id","spear_dimension","step_ref","tier_awarded","rationale"}], '
        '"summary": "string"}'
    )
    user = f"""Score this observed performance against the approved rubric.

{_tier_block(config)}

APPROVED RUBRIC:
{rubric_json}

OBSERVED PERFORMANCE DESCRIPTION:
{performance_description}

INSTRUCTIONS:
- For EACH observable metric under EACH performance step, award exactly one tier from the tiers
  above (use the exact tier name), matching the anchor that best fits the performance.
- Include the metric's step_ref in each score.
- Give a one- to two-sentence rationale grounded in the performance description.
- Write a plain-language summary suitable for a commander.

Respond with a single JSON object of this shape:
{schema_hint}"""
    return EVALUATE_SYSTEM, user
