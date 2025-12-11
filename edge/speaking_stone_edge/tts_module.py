"""Text-to-speech synthesis via Piper."""

from __future__ import annotations

import io
import logging
import os
import wave
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from piper import PiperVoice
except ImportError:  # pragma: no cover - dependency missing only in constrained envs
    PiperVoice = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH")
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH")
PIPER_SPEAKER_ID = os.getenv("PIPER_SPEAKER_ID")
PIPER_USE_CUDA = os.getenv("PIPER_USE_CUDA", "false").lower() in ("1", "true", "yes", "on")
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # bytes (16-bit)


def _placeholder_response(text: str) -> bytes:
    return f"[tts-placeholder for '{text}']".encode()


@lru_cache(maxsize=1)
def _load_voice() -> Optional[PiperVoice]:
    if PiperVoice is None:
        logger.warning("piper-tts not installed; using placeholder TTS.")
        return None
    if not PIPER_MODEL_PATH:
        logger.warning("PIPER_MODEL_PATH not set; using placeholder TTS.")
        return None

    model_path = Path(PIPER_MODEL_PATH)
    if not model_path.exists():
        logger.error("Piper model path does not exist: %s", model_path)
        return None

    config_path = Path(PIPER_CONFIG_PATH) if PIPER_CONFIG_PATH else None
    if config_path and not config_path.exists():
        logger.warning("Piper config path missing: %s (continuing without it)", config_path)
        config_path = None

    logger.info("Loading Piper voice from %s", model_path)
    try:
        voice = PiperVoice.load(str(model_path), config_path=str(config_path) if config_path else None, use_cuda=PIPER_USE_CUDA)
        return voice
    except Exception as exc:  # noqa: BLE001
        logger.error("Unable to load Piper model: %s", exc)
        return None


def _synthesize_with_piper(text: str) -> Optional[bytes]:
    voice = _load_voice()
    if voice is None:
        return None

    # Resolve speaker selection: only pass sid for multi-speaker models.
    speaker_id = None
    try:
        max_speakers = getattr(voice.config, "num_speakers", 1)
    except Exception:
        max_speakers = 1
    if max_speakers > 1:
        if PIPER_SPEAKER_ID is not None:
            try:
                speaker_id = int(PIPER_SPEAKER_ID)
            except ValueError:
                logger.warning("Invalid PIPER_SPEAKER_ID=%s; ignoring.", PIPER_SPEAKER_ID)
        else:
            speaker_id = 0  # default to first speaker for multi-speaker models

    try:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            channels = getattr(voice.config, "audio", None)
            channels = getattr(channels, "num_channels", TARGET_CHANNELS)
            sample_rate = getattr(voice.config, "sample_rate", TARGET_SAMPLE_RATE)
            wav_file.setnchannels(channels or TARGET_CHANNELS)
            wav_file.setsampwidth(TARGET_SAMPLE_WIDTH)
            wav_file.setframerate(sample_rate or TARGET_SAMPLE_RATE)
            logger.info(
                "Piper synth params sample_rate=%s channels=%s speaker_id=%s",
                sample_rate,
                channels,
                speaker_id,
            )
            if speaker_id is None:
                voice.synthesize(text, wav_file)
            else:
                voice.synthesize(text, wav_file, speaker_id=speaker_id)
        pcm_with_header = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.error("Piper synthesis failed: %s", exc)
        return None

    # The BytesIO now contains a WAV header + PCM. Strip the header to send raw PCM.
    header_size = 44  # standard PCM WAV header size
    pcm = pcm_with_header[header_size:]
    return pcm


def synthesize_speech(text: str) -> bytes:
    """Synthesize speech using Piper when configured, otherwise return placeholder bytes."""
    if not text:
        return b""

    pcm = _synthesize_with_piper(text)
    if pcm is None:
        return _placeholder_response(text)
    return pcm
