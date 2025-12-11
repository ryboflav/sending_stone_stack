"""Text-to-speech synthesis via ElevenLabs (official Python SDK)."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel (default demo voice)
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID")  # optional; let API default if unset
ELEVENLABS_API_HOST = os.getenv("ELEVENLABS_API_HOST", "https://api.elevenlabs.io")
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # bytes (16-bit)


def _placeholder_response(text: str) -> bytes:
    logger.info("tts_placeholder len_chars=%d", len(text))
    # Return 0.5s of silence at 16 kHz mono, 16-bit to avoid loud static in players.
    samples = int(TARGET_SAMPLE_RATE * 0.5)
    return b"\x00\x00" * samples


@lru_cache(maxsize=1)
def _get_client():
    """Lazy-load ElevenLabs client."""
    try:
        from elevenlabs.client import ElevenLabs
    except Exception as exc:  # pragma: no cover - import error in minimal env
        logger.error("Failed to import ElevenLabs SDK: %s", exc)
        return None

    if not ELEVENLABS_API_KEY:
        logger.warning("ELEVENLABS_API_KEY not set; using placeholder TTS")
        return None

    try:
        return ElevenLabs(api_key=ELEVENLABS_API_KEY, base_url=ELEVENLABS_API_HOST)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialize ElevenLabs client: %s", exc)
        return None


def _synthesize_with_elevenlabs(text: str) -> Optional[bytes]:
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            optimize_streaming_latency="0",  # lowest latency
            model_id=ELEVENLABS_MODEL_ID,
            output_format=f"pcm_{TARGET_SAMPLE_RATE}",
            text=text,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("ElevenLabs synthesis failed: %s", exc)
        return None

    audio_bytes = b"".join(response)
    if not audio_bytes:
        logger.error("ElevenLabs returned empty audio for %d characters", len(text))
        return None

    logger.info(
        "tts_succeeded provider=elevenlabs len_chars=%d bytes=%d voice_id=%s model_id=%s",
        len(text),
        len(audio_bytes),
        ELEVENLABS_VOICE_ID,
        ELEVENLABS_MODEL_ID or "default",
    )
    return audio_bytes


def synthesize_speech(text: str) -> bytes:
    """Synthesize speech using ElevenLabs when configured, otherwise return placeholder bytes."""
    if not text:
        return b""

    pcm = _synthesize_with_elevenlabs(text)
    if pcm is None:
        return _placeholder_response(text)
    return pcm
