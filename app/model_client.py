"""The single Model_Client abstraction (Req 6).

Every model inference call in the app goes through `generate_structured` (and,
for the audio field-scoring feature, `transcribe_audio`). This module is the
ONLY place the model name and endpoint are selected (Req 6.4), so swapping to
another model or endpoint (OpenAI, GenAI.mil, DGX Spark, a local Nemotron
server) is a one-line/env change or a Settings-page edit (Req 6.3).

Two layers of configuration, resolved fresh on every call so a live demo can
switch providers without restarting the process:
  1. Environment variables (MODEL_PROVIDER, BEDROCK_MODEL_ID, MODEL_NAME, ...)
     — the process-level defaults.
  2. `data/model_settings.json`, edited from the /settings page (see
     `app/model_settings.py`) — overrides the env defaults per field; a blank
     field falls back to the env default.

The OpenAI-compatible path is intentionally generic: it works unmodified
against the real OpenAI API, a GenAI.mil-hosted OpenAI-shaped gateway, or a
local Nemotron/DGX Spark endpoint — only the endpoint URL, key, and (for
gateways that don't use Bearer auth) an optional extra header need to change.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.model_settings import RuntimeModelSettings, load_settings

# --- Environment-variable defaults (Req 6.4) ---
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "bedrock").lower()

# Bedrock settings. Nova Pro is the default: it invokes on-demand in us-east-1
# without an AWS Marketplace subscription. Newer Anthropic/other models may
# require an inference profile and a Marketplace subscription this role lacks.
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
BEDROCK_REGION = os.getenv("AWS_REGION", os.getenv("BEDROCK_REGION", "us-east-1"))

# OpenAI-compatible settings (OpenAI, GenAI.mil, local Nemotron, DGX Spark, etc.).
DEFAULT_MODEL = os.getenv("MODEL_NAME", "nemotron-3-lightning-30b")
ENDPOINT_URL = os.getenv("MODEL_ENDPOINT", "http://localhost:8000/v1/chat/completions")
API_KEY = os.getenv("MODEL_API_KEY", "")  # optional; some local servers ignore it
REQUEST_TIMEOUT = float(os.getenv("MODEL_TIMEOUT_SECONDS", "120"))

# Speech-to-text defaults for the audio field-scoring feature (OpenAI-shaped only).
STT_ENDPOINT_URL = os.getenv("STT_ENDPOINT", "https://api.openai.com/v1/audio/transcriptions")
STT_MODEL = os.getenv("STT_MODEL", "whisper-1")
STT_API_KEY = os.getenv("STT_API_KEY", "")

TModel = TypeVar("TModel", bound=BaseModel)

_TRANSIENT_TRANSPORT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)


class ModelError(Exception):
    """The model endpoint could not be reached or returned an HTTP error (Req 8.4)."""


class ModelParseError(Exception):
    """The model output could not be parsed/validated against the schema (Req 2.9)."""


@dataclass(frozen=True)
class _Resolved:
    provider: str
    model: str
    endpoint_url: str
    api_key: str
    region: str
    extra_header_name: str
    extra_header_value: str


def _resolve(overrides: RuntimeModelSettings | None) -> _Resolved:
    """Layer saved Settings-page values over the environment defaults.

    A blank field in `overrides` means "use the env default". `overrides=None`
    (the normal case) reads the current saved settings fresh, so a Settings
    change takes effect on the very next model call with no restart.
    """
    s = overrides if overrides is not None else load_settings()
    provider = (s.provider or MODEL_PROVIDER).lower()
    default_model = BEDROCK_MODEL if provider == "bedrock" else DEFAULT_MODEL
    return _Resolved(
        provider=provider,
        model=s.model or default_model,
        endpoint_url=s.endpoint_url or ENDPOINT_URL,
        api_key=s.api_key or API_KEY,
        region=s.region or BEDROCK_REGION,
        extra_header_name=s.extra_header_name,
        extra_header_value=s.extra_header_value,
    )


def _extract_json(content: str) -> str:
    """Pull a JSON object out of a model response.

    Tolerates code fences and leading/trailing prose while still preferring a
    clean parse. Raises ModelParseError if no object-like span is found.
    """
    text = content.strip()
    # Strip a ```json ... ``` or ``` ... ``` fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Otherwise take the outermost {...} span.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    raise ModelParseError("Model response did not contain a JSON object.")


def _post(messages: list[dict], model: str, resolved: _Resolved) -> str:
    """POST to the OpenAI-compatible endpoint and return the message content.

    One bounded retry (short backoff) for transient transport errors and for
    HTTP 429/5xx — a live demo hitting a real external API is the most likely
    place to see a momentary blip.
    """
    headers = {"Content-Type": "application/json"}
    if resolved.api_key:
        headers["Authorization"] = f"Bearer {resolved.api_key}"
    if resolved.extra_header_name:
        headers[resolved.extra_header_name] = resolved.extra_header_value
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                resp = client.post(resolved.endpoint_url, headers=headers, json=payload)
        except _TRANSIENT_TRANSPORT_ERRORS as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(1.5)
                continue
            raise ModelError(
                f"The model could not be reached at {resolved.endpoint_url}."
            ) from exc
        except httpx.HTTPError as exc:  # pragma: no cover - other transport errors
            raise ModelError(f"The model request failed: {exc}") from exc

        if resp.status_code == 429:
            if attempt == 0:
                time.sleep(2.0)
                continue
            raise ModelError(
                "The model endpoint is rate-limiting requests (HTTP 429). Wait a "
                "moment and try again."
            )
        if resp.status_code >= 500:
            if attempt == 0:
                time.sleep(1.5)
                continue
            raise ModelError(f"The model endpoint returned HTTP {resp.status_code}.")
        if resp.status_code >= 400:
            raise ModelError(f"The model endpoint returned HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ModelError("The model endpoint returned an unexpected response shape.") from exc

    raise ModelError(f"The model could not be reached at {resolved.endpoint_url}.") from last_exc


def _post_bedrock(messages: list[dict], model: str, resolved: _Resolved) -> str:
    """Call the Bedrock Converse API and return the assistant text.

    Translates the OpenAI-style messages into Converse's system/messages shape.
    Imports boto3 lazily so the OpenAI path has no hard AWS dependency.
    """
    try:
        import boto3  # lazy import
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:  # pragma: no cover
        raise ModelError(
            "The Bedrock provider requires boto3. Install it or set MODEL_PROVIDER=openai."
        ) from exc

    system_blocks = [
        {"text": m["content"]} for m in messages if m["role"] == "system"
    ]
    conv_messages = [
        {"role": m["role"], "content": [{"text": m["content"]}]}
        for m in messages
        if m["role"] in ("user", "assistant")
    ]

    try:
        client = boto3.client("bedrock-runtime", region_name=resolved.region)
        resp = client.converse(
            modelId=model,
            messages=conv_messages,
            system=system_blocks or [{"text": "Respond only with valid JSON."}],
            inferenceConfig={"maxTokens": 4096, "temperature": 0.2},
        )
    except ClientError as exc:
        raise ModelError(
            f"The Bedrock model could not be invoked: {exc.response.get('Error', {}).get('Message', exc)}"
        ) from exc
    except BotoCoreError as exc:
        raise ModelError(f"The Bedrock model could not be reached: {exc}") from exc

    try:
        return resp["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError("The Bedrock response had an unexpected shape.") from exc


def _call_model(messages: list[dict], model: str, resolved: _Resolved) -> str:
    """Dispatch to the configured provider (Req 6.1, 6.4)."""
    if resolved.provider == "bedrock":
        return _post_bedrock(messages, model, resolved)
    return _post(messages, model, resolved)


def _validate(content: str, schema: type[TModel]) -> TModel:
    raw = _extract_json(content)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelParseError("Model output was not valid JSON.") from exc
    try:
        return schema.model_validate(obj)
    except ValidationError as exc:
        raise ModelParseError(
            f"Model output did not match the expected schema: {exc.error_count()} error(s)."
        ) from exc


def generate_structured(
    system_prompt: str,
    user_prompt: str,
    schema: type[TModel],
    *,
    model: str | None = None,
    settings: RuntimeModelSettings | None = None,
) -> TModel:
    """Call the model and return an instance of `schema`.

    Uses the provider selected by env vars, layered with any saved Settings-page
    overrides (or an explicit `settings` override, e.g. for the /settings/test
    connection check). One bounded retry with a "return valid JSON only"
    reminder before failing (Req 2.9). Raises ModelError if unreachable
    (Req 8.4), ModelParseError if the output cannot be validated after the
    retry (Req 2.9).
    """
    resolved = _resolve(settings)
    effective_model = model or resolved.model
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    content = _call_model(messages, effective_model, resolved)
    try:
        return _validate(content, schema)
    except ModelParseError:
        # Bounded retry: append the bad output and a strict reminder.
        retry_messages = messages + [
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": (
                    "Your previous response could not be parsed. Respond with a "
                    "single valid JSON object matching the requested schema and "
                    "nothing else. No prose, no code fences."
                ),
            },
        ]
        retry_content = _call_model(retry_messages, effective_model, resolved)
        return _validate(retry_content, schema)


def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    *,
    settings: RuntimeModelSettings | None = None,
) -> str:
    """Transcribe recorded audio to text for the field-scoring narrative.

    Only an OpenAI-compatible transcription endpoint is supported (OpenAI's own
    API, or a gateway that mirrors its `/audio/transcriptions` shape). Audio is
    sent in-memory and not persisted to disk by this app. Raises ModelError on
    any failure (unreachable endpoint, bad key, unexpected response shape).
    """
    s = settings if settings is not None else load_settings()
    endpoint = s.stt_endpoint_url or STT_ENDPOINT_URL
    model = s.stt_model or STT_MODEL
    api_key = s.stt_api_key or s.api_key or STT_API_KEY or API_KEY

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.post(
                endpoint,
                headers=headers,
                data={"model": model},
                files={"file": (filename, audio_bytes, "application/octet-stream")},
            )
    except _TRANSIENT_TRANSPORT_ERRORS as exc:
        raise ModelError(f"The transcription endpoint could not be reached at {endpoint}.") from exc
    except httpx.HTTPError as exc:  # pragma: no cover
        raise ModelError(f"The transcription request failed: {exc}") from exc

    if resp.status_code == 429:
        raise ModelError("The transcription endpoint is rate-limiting requests. Try again shortly.")
    if resp.status_code >= 400:
        raise ModelError(f"The transcription endpoint returned HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ModelError("The transcription endpoint returned no text.")
        return text.strip()
    except json.JSONDecodeError as exc:
        raise ModelError("The transcription endpoint returned an unexpected response shape.") from exc
