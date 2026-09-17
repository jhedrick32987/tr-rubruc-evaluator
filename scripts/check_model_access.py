#!/usr/bin/env python
"""Standalone sanity check for OpenAI (or any OpenAI-compatible) access.

Run this from a terminal BEFORE relying on the app's Settings page, to find
out quickly whether a hackathon-provided key/endpoint actually works and what
it's allowed to do. Uses the project's own dependencies (httpx), so run it
with the project's venv python:

    .\\.venv\\Scripts\\python.exe scripts\\check_model_access.py
    .\\.venv\\Scripts\\python.exe scripts\\check_model_access.py --model gpt-4o-mini
    .\\.venv\\Scripts\\python.exe scripts\\check_model_access.py --audio path\\to\\sample.wav

Reads the key from --api-key, or the OPENAI_API_KEY / MODEL_API_KEY env var.
Does NOT print the key. Exits non-zero if any requested check fails.
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx


def check_models(base_url: str, api_key: str) -> bool:
    print(f"[1/2] GET {base_url}/models ...", end=" ", flush=True)
    try:
        resp = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        print(f"FAILED (could not reach endpoint: {exc})")
        return False
    if resp.status_code != 200:
        print(f"FAILED (HTTP {resp.status_code}: {resp.text[:200]})")
        return False
    try:
        count = len(resp.json().get("data", []))
    except ValueError:
        count = "?"
    print(f"ok — key is valid, {count} models visible")
    return True


def check_chat(base_url: str, api_key: str, model: str) -> bool:
    print(f"[2/2] POST {base_url}/chat/completions (model={model}) ...", end=" ", flush=True)
    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "temperature": 0,
                "max_tokens": 5,
            },
            timeout=30,
        )
    except httpx.HTTPError as exc:
        print(f"FAILED (could not reach endpoint: {exc})")
        return False
    if resp.status_code != 200:
        print(f"FAILED (HTTP {resp.status_code}: {resp.text[:300]})")
        return False
    try:
        reply = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        print(f"FAILED (unexpected response shape: {resp.text[:300]})")
        return False
    print(f'ok — model responded: "{reply.strip()}"')
    return True


def check_audio(base_url: str, api_key: str, audio_path: str, stt_model: str) -> bool:
    print(f"[audio] POST {base_url}/audio/transcriptions (model={stt_model}) ...", end=" ", flush=True)
    try:
        with open(audio_path, "rb") as f:
            resp = httpx.post(
                f"{base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": stt_model},
                files={"file": (os.path.basename(audio_path), f, "application/octet-stream")},
                timeout=60,
            )
    except OSError as exc:
        print(f"FAILED (could not read {audio_path}: {exc})")
        return False
    except httpx.HTTPError as exc:
        print(f"FAILED (could not reach endpoint: {exc})")
        return False
    if resp.status_code != 200:
        print(f"FAILED (HTTP {resp.status_code}: {resp.text[:300]})")
        return False
    text = resp.json().get("text", "")
    print(f'ok — transcribed: "{text.strip()[:80]}"')
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY") or os.getenv("MODEL_API_KEY", ""))
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--audio", default="", help="Path to a short audio file to test transcription")
    parser.add_argument("--stt-model", default="whisper-1")
    args = parser.parse_args()

    if not args.api_key:
        print("No API key found. Pass --api-key or set OPENAI_API_KEY.", file=sys.stderr)
        return 2

    ok = check_models(args.base_url, args.api_key)
    ok = check_chat(args.base_url, args.api_key, args.model) and ok
    if args.audio:
        ok = check_audio(args.base_url, args.api_key, args.audio, args.stt_model) and ok
    else:
        print("[audio] skipped — pass --audio <file> to test transcription access")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
