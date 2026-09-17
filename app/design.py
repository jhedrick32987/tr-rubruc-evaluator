"""Design-stage generation service (Req 2, Req 10).

Flow: build prompt (Grounding Fields + config-only S.P.E.A.R./BARS + few-shot)
-> Model_Client.generate_structured(RubricGeneration) -> verify traceability
against the Grounding Fields -> return a Rubric with provenance.

design Correctness Property 3: a KST is traceable_to_source=yes ONLY if its
claimed supporting excerpt actually appears in the Grounding Fields.
"""
from __future__ import annotations

from app.config import AppConfig, get_config
from app.corpus import load_record
from app.model_client import generate_structured
from app.models import (
    EventRecord,
    Provenance,
    Rubric,
    RubricGeneration,
    Traceable,
)
from app.prompts import build_design_prompt


def verify_step_derivation(rubric: RubricGeneration, record: EventRecord) -> RubricGeneration:
    """Verify each metric's step_ref points to a real Performance Step (Req 2.6, 2.7, 10.4).

    A metric stays step_derived=yes only if its step_ref matches one of the task's
    numbered Performance Steps. Otherwise it is flagged step_derived=no (step_ref cleared).
    """
    valid_steps = {n for n, _ in record.grounding_fields.numbered_steps()}
    for step_block in rubric.performance_steps:
        for metric in step_block.metrics:
            ref = metric.step_ref
            if metric.step_derived == Traceable.yes and (ref is None or ref not in valid_steps):
                # Claimed derivation could not be verified against a real step.
                metric.step_derived = Traceable.no
                metric.step_ref = None
    return rubric


def generate_rubric(event_code: str, config: AppConfig | None = None) -> Rubric:
    """Generate and verify a rubric for the given event (Req 2.1-2.9, 10.4).

    Raises CorpusError (unknown/out-of-scope/missing record), ModelError
    (endpoint unreachable), or ModelParseError (invalid output).
    """
    config = config or get_config()
    record = load_record(event_code)  # exact lookup + 3500.44D enforcement

    system, user = build_design_prompt(record, config)
    generated: RubricGeneration = generate_structured(system, user, RubricGeneration)
    generated = verify_step_derivation(generated, record)

    return Rubric(
        event_code=record.event_code,
        task_attributes=generated.task_attributes,
        performance_steps=generated.performance_steps,
        provenance=Provenance(
            source_publication=record.source_publication,
            source_date=record.source_date,
            source_currency=record.source_currency,
        ),
    )
