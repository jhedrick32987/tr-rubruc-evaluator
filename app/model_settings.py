"""Runtime-editable model provider settings (Settings page).

These settings let a user switch model provider/endpoint/credentials from the
running app instead of only via environment variables at process startup —
useful for swapping models live during a demo, and for pointing the generic
OpenAI-compatible path at a different gateway (OpenAI directly, GenAI.mil, a
local Nemotron server, DGX Spark) without restarting the process.

Persisted to `data/model_settings.json`. Every field is optional; a blank
field means "fall back to the environment variable default" (see
`app/model_client.py`), so an untouched Settings page changes nothing.
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from app.paths import MODEL_SETTINGS_FILE


class RuntimeModelSettings(BaseModel):
    # Chat/generation provider (mirrors MODEL_PROVIDER/BEDROCK_*/MODEL_* env vars).
    provider: str = ""  # "bedrock" | "openai"
    model: str = ""
    endpoint_url: str = ""
    api_key: str = ""
    region: str = ""
    # Some enterprise gateways (e.g. Azure-style, some DoD gateways) authenticate
    # with a custom header instead of "Authorization: Bearer <key>".
    extra_header_name: str = ""
    extra_header_value: str = ""

    # Speech-to-text, for the audio field-scoring feature. Only an
    # OpenAI-compatible transcription endpoint is supported today.
    stt_endpoint_url: str = ""
    stt_model: str = ""
    stt_api_key: str = ""

    def has_key_set(self) -> bool:
        return bool(self.api_key)

    def has_stt_key_set(self) -> bool:
        return bool(self.stt_api_key)


def load_settings() -> RuntimeModelSettings:
    """Read saved runtime settings, or defaults (all blank) if none saved yet."""
    if not MODEL_SETTINGS_FILE.exists():
        return RuntimeModelSettings()
    try:
        data = json.loads(MODEL_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RuntimeModelSettings()
    return RuntimeModelSettings.model_validate(data)


def save_settings(settings: RuntimeModelSettings) -> None:
    MODEL_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_SETTINGS_FILE.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
