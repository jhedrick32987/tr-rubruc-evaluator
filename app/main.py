"""FastAPI application for the T&R Rubric Evaluation Generator.

Run locally with:
    uvicorn app.main:app --reload

Routes:
  GET  /                         landing page (links to Design / Evaluate)
  GET  /design                   task selector (Req 1.1)
  GET  /design/{event_code}      show source + provenance before generation (Req 1.6-1.8)
  POST /design/{event_code}/generate   generate rubric -> review (Req 2)
  GET  /review/{event_code}      side-by-side review of the working draft (Req 3.1)
  POST /review/{event_code}/kst  inline edit / approve / reject (Req 3.2, 3.3)
  POST /review/{event_code}/lock lock into an immutable version (Req 3.5-3.9)
  GET  /evaluate                 select approved rubric + enter performance (Req 4.1-4.3)
  POST /evaluate/score           score a performance (Req 4.4-4.7)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import corpus, design, evaluate, review, store
from app.config import ConfigError, get_config
from app.corpus import CorpusError
from app.model_client import ModelError, ModelParseError, generate_structured, transcribe_audio
from app.model_settings import RuntimeModelSettings, load_settings, save_settings
from app.models import KSTStatus
from app.paths import STATIC_DIR, TEMPLATES_DIR, ensure_data_dirs
from app.review import ReviewError
from pydantic import BaseModel

app = FastAPI(title="T&R Rubric Evaluation Generator", version="1.0.0")
ensure_data_dirs()

logger = logging.getLogger("tr_rubric_evaluator")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def _page(request: Request, template: str, **ctx) -> HTMLResponse:
    base = {"request": request}
    base.update(ctx)
    return templates.TemplateResponse(template, base)


def _error_page(request: Request, message: str, status: int = 400) -> HTMLResponse:
    resp = _page(request, "error.html", message=message)
    resp.status_code = status
    return resp


@app.exception_handler(Exception)
def _unhandled_exception(request: Request, exc: Exception) -> HTMLResponse:
    """Never show a raw traceback to a live audience; log it server-side instead."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_page(
        request,
        "An unexpected error occurred. Check the server log for details.",
        500,
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return _page(request, "index.html", title="T&R Rubric Evaluation Generator")


# --------------------------------------------------------------------------- #
# Design stage
# --------------------------------------------------------------------------- #
@app.get("/design", response_class=HTMLResponse)
def design_selector(request: Request) -> HTMLResponse:
    try:
        tasks = corpus.list_tasks()  # Req 1.1, 1.2, 1.3
    except CorpusError as exc:
        return _error_page(request, str(exc), 500)
    return _page(request, "design_select.html", title="Design — Select Task", tasks=tasks)


@app.get("/design/{event_code}", response_class=HTMLResponse)
def design_source(request: Request, event_code: str) -> HTMLResponse:
    try:
        record = corpus.load_record(event_code)  # Req 1.4-1.6
        config = get_config()
    except (CorpusError, ConfigError) as exc:
        return _error_page(request, str(exc))
    return _page(
        request,
        "design_source.html",
        title=f"Design — {record.event_code}",
        record=record,
        steps=record.grounding_fields.numbered_steps(),  # backbone (Req 2.2)
        spear_dimensions=config.spear_dimensions,  # Req 1.7, 1.8 shows provenance
    )


@app.post("/design/{event_code}/generate")
def design_generate(request: Request, event_code: str):
    try:
        rubric = design.generate_rubric(event_code)  # Req 2
        store.save_draft(rubric)
    except (CorpusError, ConfigError) as exc:
        return _error_page(request, str(exc))
    except ModelError as exc:
        return _error_page(request, str(exc), 502)  # Req 8.4
    except ModelParseError as exc:
        return _error_page(request, f"Rubric generation failed: {exc}", 502)  # Req 2.9
    return RedirectResponse(url=f"/review/{event_code}", status_code=303)


# --------------------------------------------------------------------------- #
# Review stage
# --------------------------------------------------------------------------- #
@app.get("/review/{event_code}", response_class=HTMLResponse)
def review_page(request: Request, event_code: str) -> HTMLResponse:
    draft = store.get_draft(event_code)
    if draft is None:
        return _error_page(request, "No rubric draft found. Generate one first.", 404)
    try:
        record = corpus.load_record(event_code)
    except CorpusError as exc:
        return _error_page(request, str(exc))
    not_derived = review.not_step_derived(draft)
    try:
        tier_names = [t.name for t in get_config().rubric_tiers]
    except ConfigError as exc:
        return _error_page(request, str(exc))
    return _page(
        request,
        "review.html",
        title=f"Review — {event_code}",
        record=record,
        rubric=draft,
        tier_names=tier_names,
        untraceable_count=len(not_derived),
    )


@app.post("/review/{event_code}/kst")
def review_metric_action(
    request: Request,
    event_code: str,
    step_index: int = Form(...),
    metric_index: int = Form(...),
    action: str = Form(...),
    field: str = Form(default=""),
    value: str = Form(default=""),
):
    draft = store.get_draft(event_code)
    if draft is None:
        return _error_page(request, "No rubric draft found.", 404)
    try:
        if action == "edit":
            review.edit_metric(draft, step_index, metric_index, field, value)  # Req 3.2
        elif action == "approve":
            review.set_metric_status(draft, step_index, metric_index, KSTStatus.approved)  # Req 3.3
        elif action == "reject":
            review.set_metric_status(draft, step_index, metric_index, KSTStatus.rejected)  # Req 3.3
        else:
            return _error_page(request, f"Unknown action '{action}'.")
    except ReviewError as exc:
        return _error_page(request, str(exc))
    store.save_draft(draft)
    return RedirectResponse(url=f"/review/{event_code}", status_code=303)


@app.post("/review/{event_code}/lock")
def review_lock(
    request: Request,
    event_code: str,
    acknowledged: str = Form(default=""),
):
    draft = store.get_draft(event_code)
    if draft is None:
        return _error_page(request, "No rubric draft found.", 404)
    ack = acknowledged.lower() in {"on", "true", "1", "yes"}
    try:
        version = review.lock(draft, acknowledged=ack)  # Req 3.5-3.9
    except ReviewError as exc:
        return _error_page(request, str(exc))
    return RedirectResponse(url=f"/evaluate?version={version.version_id}", status_code=303)


# --------------------------------------------------------------------------- #
# Evaluate stage
# --------------------------------------------------------------------------- #
@app.get("/evaluate", response_class=HTMLResponse)
def evaluate_page(request: Request, version: str = "") -> HTMLResponse:
    versions = evaluate.list_versions()  # Req 4.1
    return _page(
        request,
        "evaluate.html",
        title="Evaluate",
        versions=versions,
        selected_version=version,
    )


@app.post("/evaluate/start")
def evaluate_start(
    request: Request,
    version_id: str = Form(...),
    unit_label: str = Form(default=""),
):
    try:
        session = evaluate.start_session(version_id, unit_label)  # Req 4.1, 4.2
    except evaluate.EvaluateError as exc:
        return _error_page(request, str(exc))
    return RedirectResponse(url=f"/evaluate/session/{session.session_id}", status_code=303)


def _render_session(request: Request, session) -> HTMLResponse:
    version = store.get_version(session.rubric_version_id)
    if version is None:
        return _error_page(request, "The rubric version for this session is missing.", 404)
    try:
        config = get_config()
    except ConfigError as exc:
        return _error_page(request, str(exc))
    tier_values = {t.name: t.value for t in config.rubric_tiers}
    scores_by_metric = {s.metric_id: s for s in session.scores}
    summary = evaluate.summarize(session, tier_values)
    return _page(
        request,
        "score.html",
        title=f"Score — {session.event_code}",
        session=session,
        version=version,
        tier_names=[t.name for t in config.rubric_tiers],
        scores_by_metric=scores_by_metric,
        summary=summary,
    )


@app.get("/evaluate/session/{session_id}", response_class=HTMLResponse)
def evaluate_session(request: Request, session_id: str) -> HTMLResponse:
    session = store.get_session(session_id)
    if session is None:
        return _error_page(request, "Scoring session not found.", 404)
    return _render_session(request, session)


@app.post("/evaluate/session/{session_id}/score")
def evaluate_record(
    request: Request,
    session_id: str,
    metric_id: str = Form(...),
    tier_awarded: str = Form(...),
    note: str = Form(default=""),
):
    try:
        evaluate.record_score(session_id, metric_id, tier_awarded, note)  # Req 4.4, 4.5
    except evaluate.EvaluateError as exc:
        return _error_page(request, str(exc))
    return RedirectResponse(
        url=f"/evaluate/session/{session_id}#m-{metric_id}", status_code=303
    )


@app.post("/evaluate/session/{session_id}/narrate")
def evaluate_narrate(
    request: Request,
    session_id: str,
    narrative: str = Form(...),
):
    try:
        evaluate.score_from_narrative(session_id, narrative)
    except evaluate.EvaluateError as exc:
        return _error_page(request, str(exc))
    except ModelError as exc:
        return _error_page(request, str(exc), 502)
    except ModelParseError as exc:
        return _error_page(request, f"Auto-scoring failed: {exc}", 502)
    return RedirectResponse(url=f"/evaluate/session/{session_id}", status_code=303)


@app.post("/evaluate/session/{session_id}/transcribe")
async def evaluate_transcribe(
    request: Request,
    session_id: str,
    audio: UploadFile = File(...),
):
    audio_bytes = await audio.read()
    if not audio_bytes:
        return _error_page(request, "No audio was received. Try recording again.")
    try:
        narrative = transcribe_audio(audio_bytes, audio.filename or "observation.webm")
        evaluate.score_from_narrative(session_id, narrative)
    except evaluate.EvaluateError as exc:
        return _error_page(request, str(exc))
    except ModelError as exc:
        return _error_page(request, str(exc), 502)
    except ModelParseError as exc:
        return _error_page(request, f"Auto-scoring failed: {exc}", 502)
    return RedirectResponse(url=f"/evaluate/session/{session_id}", status_code=303)


# --------------------------------------------------------------------------- #
# Settings — runtime model provider picker
# --------------------------------------------------------------------------- #
class _PingResponse(BaseModel):
    ok: bool


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, tested: str = "", test_ok: str = "", test_message: str = ""):
    settings = load_settings()
    return _page(
        request,
        "settings.html",
        title="Model Settings",
        settings=settings,
        tested=tested == "1",
        test_ok=test_ok == "1",
        test_message=test_message,
    )


@app.post("/settings")
def settings_save(
    request: Request,
    provider: str = Form(default=""),
    model: str = Form(default=""),
    endpoint_url: str = Form(default=""),
    api_key: str = Form(default=""),
    region: str = Form(default=""),
    extra_header_name: str = Form(default=""),
    extra_header_value: str = Form(default=""),
    stt_endpoint_url: str = Form(default=""),
    stt_model: str = Form(default=""),
    stt_api_key: str = Form(default=""),
):
    current = load_settings()
    updated = RuntimeModelSettings(
        provider=provider.strip().lower(),
        model=model.strip(),
        endpoint_url=endpoint_url.strip(),
        # Keep the previously saved key if the field was left blank (the page
        # never echoes a saved key back into the input for display).
        api_key=api_key.strip() or current.api_key,
        region=region.strip(),
        extra_header_name=extra_header_name.strip(),
        extra_header_value=extra_header_value.strip() or current.extra_header_value,
        stt_endpoint_url=stt_endpoint_url.strip(),
        stt_model=stt_model.strip(),
        stt_api_key=stt_api_key.strip() or current.stt_api_key,
    )
    save_settings(updated)
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/clear-keys")
def settings_clear_keys():
    current = load_settings()
    current.api_key = ""
    current.stt_api_key = ""
    save_settings(current)
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/test")
def settings_test(request: Request):
    try:
        generate_structured(
            "You respond only with a single valid JSON object matching the requested schema.",
            'Respond with exactly this JSON object: {"ok": true}',
            _PingResponse,
        )
    except ModelError as exc:
        return RedirectResponse(
            url=f"/settings?tested=1&test_ok=0&test_message={_url_escape(str(exc))}",
            status_code=303,
        )
    except ModelParseError as exc:
        return RedirectResponse(
            url=f"/settings?tested=1&test_ok=0&test_message={_url_escape('Model reached, but response was unparseable: ' + str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        url="/settings?tested=1&test_ok=1&test_message=Connection+succeeded.",
        status_code=303,
    )


def _url_escape(text: str) -> str:
    from urllib.parse import quote

    return quote(text[:300])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
