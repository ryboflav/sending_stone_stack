"""LLM bridge backed by OpenRouter's chat completions API."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/auto")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_REFERRER = os.getenv("OPENROUTER_REFERRER")
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE")
REQUEST_TIMEOUT = float(os.getenv("OPENROUTER_TIMEOUT", "30"))


def _build_headers() -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    if OPENROUTER_REFERRER:
        headers["HTTP-Referer"] = OPENROUTER_REFERRER
    if OPENROUTER_APP_TITLE:
        headers["X-Title"] = OPENROUTER_APP_TITLE
    return headers


def _post_openrouter(payload: Dict[str, Any]) -> Dict[str, Any]:
    target_url = OPENROUTER_BASE_URL.rstrip("/") + "/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(target_url, data=data, headers=_build_headers(), method="POST")
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def generate_reply(text: str) -> str:
    """Send the transcript to OpenRouter and return the assistant reply."""
    fallback = f"Echoing your words: {text}"
    if not text.strip():
        return fallback
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY missing; falling back to echo response.")
        return fallback

    payload: Dict[str, Any] = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are Speaking Stone, a concise conversational assistant co-located on a robotics hub.",
            },
            {"role": "user", "content": text},
        ],
    }

    try:
        data = _post_openrouter(payload)
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("no choices returned from OpenRouter")
        message = choices[0]["message"]["content"]
        return message.strip() if isinstance(message, str) else fallback
    except (urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        logger.error("OpenRouter request failed: %s", exc)
        return fallback
