# T&R Rubric Evaluation Generator

A hackathon prototype that automates two stages of the ADDIE instructional design
lifecycle for Marine Corps infantry training:

- **Design** — generate a structured performance rubric from a Training & Readiness
  (T&R) task standard. Rubrics are built from KSTs (Knowledge/Skill/Task statements),
  organized under the S.P.E.A.R. dimensions, with a behavioral anchor per rubric tier
  (BARS methodology). Every anchor is checked for traceability to the source standard;
  unsupported anchors are flagged, not invented. An SME reviews and approves before a
  rubric is locked as a version.
- **Evaluate** — score an observed performance against an approved rubric and produce a
  structured result plus a plain-language summary an evaluator could hand to a commander.

This is the smallest working end-to-end slice, built for a two-person team to operate
in a live demo. It is **not** the production system.

## What's built now vs. deferred

### Built in this prototype
- Index-driven task selector (NAVMC 3500.44D events from `machine_indexes/events.json`)
- Exact source-record lookup (no search, embeddings, or vector store)
- Design-stage rubric generation with a single, swappable model call
- Verified traceability: an anchor is "traceable" only if its cited excerpt actually
  appears in the source grounding fields
- Side-by-side SME review: inline edit, approve/reject, soft traceability gate on lock,
  immutable versions
- Evaluate-stage scoring against an approved rubric — by hand (tap a tier per metric) or
  **auto-scored from a field observation**: record audio (or type/paste a narrative) while
  watching the squad perform, and the model suggests a tier per metric for you to confirm
  or override, instead of tapping through the whole checklist live
- A runtime **Settings page** (`/settings`) to switch model provider/endpoint/key without
  restarting the app or editing env vars — useful for swapping models mid-demo
- Configuration-driven rubric structure (tiers, competency ladder, S.P.E.A.R. dimensions)
- A visible, non-hideable provenance caveat on every rubric and evaluation result

### Future phases (documented production roadmap — NOT built here)
The remaining ADDIE stages — **Analyze, Develop, Implement** — are future phases.
The full production architecture (Amazon Bedrock multi-agent orchestration, five
segmented knowledge bases, OpenSearch/Aurora pgvector, Neptune, DynamoDB, multi-tenant
IAM, Cognito role groups, offline-first PWA, AppSync/DataStore, IoT Greengrass,
Snowball Edge, CodePipeline contributor path, training-provider integration, and
GovCloud/compliance controls) is the team's post-event roadmap. See the attached
AWS ADDIE architecture document for that direction.

## Requirements

- Python 3.11+ (developed on 3.12)
- A local, OpenAI-compatible model endpoint (default: Nemotron-3-Lightning-30b)
- The source corpus present at `corpus/work/fireteam-forge-corpus/`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/ and choose **Design a rubric** or **Evaluate a performance**.

## Model configuration (one function, switchable providers, no restart needed)

All model inference goes through a single function (`app/model_client.py`), selectable
by the `MODEL_PROVIDER` environment variable and/or the **Settings page** at `/settings`
in the running app — no code changes (Req 6). Env vars set the process-level default;
the Settings page (backed by `data/model_settings.json`, gitignored) overrides them live,
which is the easiest way to swap models during a demo without restarting `uvicorn`.

### Bedrock (used for the demo)

```powershell
$env:MODEL_PROVIDER  = "bedrock"
$env:AWS_REGION      = "us-east-1"
$env:BEDROCK_MODEL_ID = "amazon.nova-pro-v1:0"   # invokes on-demand, no Marketplace sub
```

Amazon Nova Pro is the default because it invokes on-demand in `us-east-1` without an
AWS Marketplace subscription. Newer Anthropic models (e.g. Claude Sonnet) require an
inference profile and a Marketplace subscription that the workshop instance role does
not have — enable model access in the Bedrock console first if you want to use them,
then set `BEDROCK_MODEL_ID` to the profile id (e.g. `us.anthropic.claude-sonnet-4-6`).

### OpenAI-compatible endpoint (OpenAI, local Nemotron, GenAI.mil, DGX Spark)

The same `openai` provider path works for the real OpenAI API, a local Nemotron/DGX
Spark server, or an enterprise gateway like GenAI.mil — they all speak the same
`POST {endpoint}/chat/completions` shape.

```powershell
$env:MODEL_PROVIDER = "openai"
$env:MODEL_NAME     = "nemotron-3-lightning-30b"
$env:MODEL_ENDPOINT = "http://localhost:8000/v1/chat/completions"
$env:MODEL_API_KEY  = ""                          # optional
```

**Using OpenAI directly** (e.g. a hackathon-provided key): set `MODEL_ENDPOINT` to
`https://api.openai.com/v1/chat/completions` and `MODEL_NAME` to a real OpenAI model id
(e.g. `gpt-4o-mini`), or just fill these in on the `/settings` page instead of env vars.

**Not sure if you actually have OpenAI access?** Check it two ways:
1. In the app, go to `/settings`, fill in the OpenAI endpoint/model/key, click
   **Test connection**.
2. From a terminal: `.\.venv\Scripts\python.exe scripts\check_model_access.py` — checks
   that your key is valid and that the chosen model responds, without touching the app.
   Add `--audio path\to\file.wav` to also check transcription access (used by the audio
   field-scoring feature below).

**GenAI.mil** — not yet wired up live (no access at time of writing), but the generic
`openai` provider is built to point at it once you have an endpoint/key: set
`MODEL_ENDPOINT` to the GenAI.mil chat-completions URL, and if it authenticates with a
header other than `Authorization: Bearer <key>` (common on DoD/enterprise gateways),
fill in "Extra auth header name/value" on the Settings page instead of a code change.

## Hosting note

This prototype runs **locally** and calls Amazon Bedrock for inference. AWS App Runner
hosting was evaluated but is blocked by an organization Service Control Policy in the
workshop account (`apprunner:*` denied); lifting that requires an AWS Organizations
admin. Deploying the app itself to AWS remains part of the production roadmap.

## Rubric configuration

`config.json` at the project root defines the rubric structure — no code changes needed:

- `rubric_tiers` — default: Unsatisfactory / Satisfactory / Proficient
- `competency_levels` — default: Foundation / Intermediate / Expert
- `spear_dimensions` — Speed, Precision, Executive Control, Adaptability, Risk Exposure

> **S.P.E.A.R. definitions come only from `config.json`, never from the corpus.** The
> ONR S.P.E.A.R. technical material was never publicly available, so the corpus
> deliberately contains no S.P.E.A.R. definitions. The definitions in `config.json` are
> the team's own working definitions.

Edits to `config.json` are picked up on the next request.

## Provenance and honesty

Every generated rubric and every evaluation result carries a visible caveat: the tool
works from **NAVMC 3500.44D**, a public proxy of the controlled T&R manual. 3500.44D
was superseded by **3500.44E**, which was not publicly downloadable when this corpus was
built. Verify against the current controlled source before operational use. This caveat
cannot be hidden.

## Audio field-scoring

On a scoring session's page, above the metric checklist, there's an **Auto-score from an
observation** panel:

- **Record** — click Start recording, narrate what you observe (e.g. "the fireteam moved
  in a staggered column, team leader called contact within a few seconds..."), click Stop.
  The audio is transcribed (OpenAI-compatible `/audio/transcriptions`, e.g. OpenAI Whisper)
  and the transcript is scored against the locked rubric; matching metrics get pre-filled
  tier buttons marked **AUTO**. Audio is processed in-memory and never written to disk.
- **Type/paste instead** — a collapsible narrative textarea underneath does the same
  scoring pass on typed text, useful when recording live isn't practical, or as a fallback
  if the mic/transcription isn't available on stage.

Auto-filled scores are provisional: the evaluator still taps a tier to confirm or change
any metric, which marks it as a human score again. The model never becomes the scorer of
record — same "flag, don't hide" posture as the untraceable-anchor flags in Review. This
needs a working transcription endpoint (see the Settings section above); without one, the
narrative-text path still works standalone since it skips transcription entirely.

## Running the demo (and the recorded backup)

1. Start your model endpoint, then run the app (see **Run** above).
2. **Design**: pick a task → review the source standard and provenance → Generate rubric.
3. **Review**: edit/approve/reject KSTs → acknowledge any untraceable anchors → Lock.
4. **Evaluate**: pick the locked version → record an observation or paste a performance
   description → auto-score, then confirm/override any tier as needed.

**Recorded backup.** All app state is local JSON under `data/` (approved versions,
drafts, and prewritten demo scenarios). If the live model misbehaves on stage, fall back
to a screen recording of a prior successful run; the `data/` folder preserves the
approved rubrics and demo scenarios used in that run.

## Project layout

```
app/            FastAPI app + services (config, corpus, model_client, model_settings,
                design, review, evaluate, store, provenance, prompts)
templates/      Jinja2 pages (selector, source, review, evaluate, settings)
static/         styles + record.js (browser audio recording for field-scoring)
scripts/        standalone helper scripts (check_model_access.py)
config.json     rubric structure (tiers, ladder, S.P.E.A.R.)
examples/       hand-written few-shot example rubrics
data/           local app state (versions, drafts, demo scenarios, model_settings.json*)
corpus/         source corpus (read-only)
```
\* `data/model_settings.json` may contain an API key; it's gitignored.

## Notes on scope

Analyze, Develop, and Implement are named as future phases in the UI. This prototype
provisions no cloud infrastructure; it runs locally against a model endpoint you supply.
