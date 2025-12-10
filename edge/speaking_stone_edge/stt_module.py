"""Speech-to-text implementation backed by faster-whisper."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Iterable, List

import numpy as np
from faster_whisper import WhisperModel

from .protocol import AudioFrameHeader

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE")
WHISPER_SAMPLE_RATE = 16000


@lru_cache(maxsize=1)
def _get_model() -> WhisperModel:
    """Lazy-load the Whisper model so startup stays fast."""
    return WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)


def _pcm16_mono_to_float32(pcm: bytes, header: AudioFrameHeader) -> np.ndarray:
    """Convert raw PCM16 mono bytes into float32 samples in [-1.0, 1.0]."""
    if header.bits_per_sample != 16:
        raise ValueError(f"Only 16-bit PCM supported, got {header.bits_per_sample}")
    if header.channels != 1:
        raise ValueError(f"Only mono audio supported, got {header.channels} channels")
    if len(pcm) % 2 != 0:
        raise ValueError("PCM payload size must be aligned to 16-bit samples")

    samples = np.frombuffer(pcm, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def _collect_text(segments: Iterable) -> str:
    """Join non-empty segment texts."""
    texts: List[str] = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            texts.append(text)
    return " ".join(texts) if texts else ""


def transcribe_audio(pcm: bytes, header: AudioFrameHeader) -> str:
    """Transcribe the provided PCM bytes using faster-whisper."""
    if not pcm:
        return ""
    if header.sample_rate != WHISPER_SAMPLE_RATE:
        raise ValueError(f"Whisper expects {WHISPER_SAMPLE_RATE} Hz audio, got {header.sample_rate}")

    audio = _pcm16_mono_to_float32(pcm, header)
    model = _get_model()

    segments, _ = model.transcribe(
        audio=audio,
        language=WHISPER_LANGUAGE,
        vad_filter=True,
    )
    transcript = _collect_text(segments)
    return transcript or ""
