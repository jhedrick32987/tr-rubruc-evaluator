"""The single source of the Provenance Caveat text (Req 2.11, 4.7).

Every generated rubric and every evaluation result carries this caveat; it is
never hidden (design Correctness Property 6). Centralizing it here guarantees the
Design and Evaluate stages show the same honest statement.
"""
from __future__ import annotations

from app.models import Provenance

CAVEAT_HEADLINE = (
    "This rubric derives from a PUBLIC PROXY of the controlled T&R manual, "
    "not the current controlled version."
)

CAVEAT_DETAIL = (
    "Source: NAVMC 3500.44D, which was superseded by NAVMC 3500.44E. "
    "3500.44E was not publicly downloadable when this corpus was built. "
    "Verify against the current controlled T&R source before operational use."
)


def provenance_caveat(prov: Provenance | None = None) -> str:
    """Return the full caveat, appending source_currency/date when available."""
    parts = [CAVEAT_HEADLINE, CAVEAT_DETAIL]
    if prov is not None:
        extra = []
        if prov.source_publication:
            extra.append(f"source_publication: {prov.source_publication}")
        if prov.source_date:
            extra.append(f"source_date: {prov.source_date}")
        if extra:
            parts.append(" | ".join(extra))
    return " ".join(parts)
