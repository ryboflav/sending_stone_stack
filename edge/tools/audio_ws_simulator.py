"""Helper script that replays a WAV file over the audio websocket."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import wave

import numpy as np
import websockets

from speaking_stone_edge import protocol

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # bytes (16-bit)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "wav_path",
        type=Path,
        help="Path to a PCM16 mono WAV file (e.g. tests/data/audio/test_speech.wav)",
    )
    parser.add_argument(
        "--url",
        default="ws://127.0.0.1:8000/ws/audio",
        help="Websocket URL for the edge server",
    )
    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=80,
        help="Approximate duration per frame in milliseconds",
    )
    parser.add_argument(
        "--post-delay",
        type=float,
        default=2.0,
        help="Seconds to wait after sending speech_end before closing",
    )
    return parser.parse_args()


def _load_wav(path: Path) -> tuple[bytes, int, int, int]:
    """Return PCM bytes plus (sample_rate, channels, bits_per_sample)."""

    if not path.exists():
        raise FileNotFoundError(path)

    with wave.open(str(path), "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        bits_per_sample = sample_width * 8
        pcm = wav.readframes(wav.getnframes())

    pcm = _convert_to_required_format(pcm, sample_rate, channels, sample_width)
    return pcm, TARGET_SAMPLE_RATE, TARGET_CHANNELS, TARGET_SAMPLE_WIDTH * 8


def _convert_to_required_format(
    pcm: bytes, sample_rate: int, channels: int, sample_width: int
) -> bytes:
    """Convert arbitrary PCM to 16-bit mono at 16 kHz using numpy."""

    samples = _pcm_bytes_to_float32(pcm, sample_width, channels)
    if sample_rate != TARGET_SAMPLE_RATE:
        samples = _resample(samples, sample_rate, TARGET_SAMPLE_RATE)
    pcm16 = _float32_to_pcm16(samples)
    return pcm16


def _pcm_bytes_to_float32(pcm: bytes, sample_width: int, channels: int) -> np.ndarray:
    """Decode PCM bytes into float32 samples in [-1, 1]."""
    if sample_width == 1:
        data = np.frombuffer(pcm, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    else:
        raise ValueError(f"Unsupported sample width: {sample_width * 8} bits")

    if channels > 1:
        total_samples = data.shape[0] // channels
        if total_samples == 0:
            return np.array([], dtype=np.float32)
        data = data[: total_samples * channels]
        data = data.reshape(total_samples, channels).mean(axis=1)
    return data


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Resample mono float32 audio to the target rate."""
    if audio.size == 0 or source_rate == target_rate:
        return audio
    duration = audio.size / source_rate
    target_length = max(1, int(round(duration * target_rate)))
    original_times = np.linspace(0.0, duration, num=audio.size, endpoint=False)
    target_times = np.linspace(0.0, duration, num=target_length, endpoint=False)
    resampled = np.interp(target_times, original_times, audio)
    return resampled.astype(np.float32, copy=False)


def _float32_to_pcm16(audio: np.ndarray) -> bytes:
    """Convert float32 samples in [-1, 1] to PCM16 bytes."""
    if audio.size == 0:
        return b""
    clipped = np.clip(audio, -1.0, 1.0)
    int_samples = (clipped * 32767.0).astype("<i2")
    return int_samples.tobytes()


def _chunk_bytes(data: bytes, chunk_size: int) -> list[bytes]:
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


async def _listen_for_responses(ws: websockets.WebSocketClientProtocol) -> None:
    try:
        while True:
            message = await ws.recv()
            if isinstance(message, str):
                print(f"<< text: {message}")
            else:
                print(f"<< received {len(message)} bytes (likely TTS chunk)")
    except websockets.ConnectionClosed:
        print("<< connection closed by server")


async def _send_audio_frames(
    ws: websockets.WebSocketClientProtocol,
    pcm: bytes,
    sample_rate: int,
    channels: int,
    bits_per_sample: int,
    chunk_ms: int,
) -> None:
    bytes_per_sample = (bits_per_sample // 8) * channels
    samples_per_chunk = max(1, sample_rate * chunk_ms // 1000)
    chunk_size = samples_per_chunk * bytes_per_sample

    sequence = 0
    for chunk in _chunk_bytes(pcm, chunk_size):
        header = protocol.AudioFrameHeader(
            sequence=sequence,
            payload_len=len(chunk),
            sample_rate=sample_rate,
            channels=channels,
            bits_per_sample=bits_per_sample,
        )
        await ws.send(header.to_bytes() + chunk)
        sequence += 1
        await asyncio.sleep(chunk_ms / 1000.0)

    await ws.send(protocol.encode_control_message("speech_end", {}))


async def _run(args: argparse.Namespace) -> None:
    pcm, sample_rate, channels, bits_per_sample = _load_wav(args.wav_path)

    print(f"Connecting to {args.url} ...")
    async with websockets.connect(args.url, ping_interval=None) as ws:
        listener = asyncio.create_task(_listen_for_responses(ws))
        await _send_audio_frames(ws, pcm, sample_rate, channels, bits_per_sample, args.chunk_ms)
        await asyncio.sleep(args.post_delay)
        await ws.close()
        await listener


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)


if __name__ == "__main__":
    main()
