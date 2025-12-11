from dataclasses import dataclass, field
import json
import logging
import time
from typing import Dict, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from . import protocol
from .llm_module import generate_reply
from . import stt_module
from .stt_module import transcribe_audio
from .tts_module import synthesize_speech

app = FastAPI(title="Speaking Stone Edge", version="0.1.0")
logger = logging.getLogger("speaking_stone_edge")
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s")
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


@dataclass
class AudioStreamBuffer:
    """Accumulate PCM payloads for a websocket session."""

    pcm_bytes: bytearray = field(default_factory=bytearray)
    header: protocol.AudioFrameHeader | None = None

    def append_frame(self, header: protocol.AudioFrameHeader, payload: bytes) -> None:
        """Append a PCM payload, ensuring audio params stay consistent."""
        if header.payload_len != len(payload):
            raise ValueError("payload length mismatch")

        if self.header is None:
            self.header = header
        else:
            if header.sample_rate != self.header.sample_rate:
                raise ValueError("sample rate changed mid-stream")
            if header.channels != self.header.channels:
                raise ValueError("channel count changed mid-stream")
            if header.bits_per_sample != self.header.bits_per_sample:
                raise ValueError("bit depth changed mid-stream")

        self.pcm_bytes.extend(payload)

    def snapshot(self) -> Tuple[bytes, protocol.AudioFrameHeader]:
        """Return current PCM bytes with the header metadata."""
        if self.header is None:
            raise ValueError("no audio buffered yet")
        return bytes(self.pcm_bytes), self.header

    def clear(self) -> None:
        """Reset the buffer for the next utterance."""
        self.pcm_bytes.clear()
        self.header = None

    def is_empty(self) -> bool:
        return len(self.pcm_bytes) == 0

    def byte_count(self) -> int:
        return len(self.pcm_bytes)


class StageTimer:
    """Record elapsed time for sequential pipeline stages."""

    def __init__(self) -> None:
        self._last = time.perf_counter()
        self._durations: list[tuple[str, float]] = []

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self._durations.append((name, now - self._last))
        self._last = now

    def metrics(self) -> Dict[str, float]:
        total = 0.0
        metric: Dict[str, float] = {}
        for name, duration in self._durations:
            metric[f"{name}_ms"] = round(duration * 1000.0, 2)
            total += duration
        if self._durations:
            metric["total_ms"] = round(total * 1000.0, 2)
        else:
            metric["total_ms"] = 0.0
        return metric


def _estimate_duration_ms(byte_len: int, header: protocol.AudioFrameHeader) -> float:
    """Approximate duration (ms) for PCM bytes."""
    bytes_per_sample = header.channels * (header.bits_per_sample // 8)
    if bytes_per_sample == 0 or header.sample_rate == 0:
        return 0.0
    samples = byte_len / bytes_per_sample
    seconds = samples / header.sample_rate
    return round(seconds * 1000.0, 2)


@app.get("/")
async def root_status():
    """Lightweight status endpoint for container health checks."""
    return {"service": "speaking-stone-edge", "status": "ok"}


@app.on_event("startup")
async def _warm_stt_model() -> None:
    """Load the Whisper model during startup to avoid first-request latency."""
    stt_module._get_model()


@app.websocket("/ws/audio")
async def audio_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text(protocol.encode_control_message("connected", {"note": "placeholder session"}))
    websocket.state.audio_buffer = AudioStreamBuffer()
    websocket.state.chat_history: list[dict[str, str]] = []
    client = websocket.client or ("unknown", 0)
    logger.info("websocket_connected client=%s", client)

    try:
        while True:
            message = await websocket.receive()
            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                logger.info("websocket_disconnect client=%s", client)
                break
            if "bytes" in message and message["bytes"] is not None:
                raw_frame = message["bytes"]
                try:
                    header = protocol.AudioFrameHeader.from_bytes(raw_frame)
                except ValueError as exc:
                    logger.warning("invalid_audio_header client=%s error=%s", client, exc)
                    await websocket.send_text(
                        protocol.encode_control_message(
                            "error", {"detail": str(exc), "received_bytes": len(raw_frame)}
                        )
                    )
                    continue

                frame_payload = raw_frame[protocol.HEADER_SIZE :]
                if len(frame_payload) != header.payload_len:
                    logger.warning(
                        "payload_length_mismatch client=%s header=%s actual=%d",
                        client,
                        header.payload_len,
                        len(frame_payload),
                    )
                    await websocket.send_text(
                        protocol.encode_control_message(
                            "error",
                            {
                                "detail": "audio payload length mismatch",
                                "header_payload_len": header.payload_len,
                                "actual_payload_len": len(frame_payload),
                            },
                        )
                    )
                    continue

                audio_buffer: AudioStreamBuffer = websocket.state.audio_buffer
                try:
                    audio_buffer.append_frame(header, frame_payload)
                    logger.debug(
                        "frame_buffered client=%s sequence=%d total_bytes=%d",
                        client,
                        header.sequence,
                        audio_buffer.byte_count(),
                    )
                except ValueError as exc:
                    audio_buffer.clear()
                    logger.warning(
                        "frame_rejected client=%s sequence=%d error=%s",
                        client,
                        header.sequence,
                        exc,
                    )
                    await websocket.send_text(
                        protocol.encode_control_message(
                            "error",
                            {
                                "detail": str(exc),
                                "sequence": header.sequence,
                                "sample_rate": header.sample_rate,
                                "channels": header.channels,
                                "bits_per_sample": header.bits_per_sample,
                            },
                        )
                    )

            elif "text" in message and message["text"] is not None:
                await _handle_control_message(websocket, message["text"])
            else:
                await websocket.send_text(protocol.encode_control_message("noop", {}))
    except WebSocketDisconnect:
        # TODO: add reconnect/backoff strategy for clients.
        return


async def _handle_control_message(websocket: WebSocket, raw_text: str) -> None:
    """Process control messages coming from the client."""
    try:
        control = protocol.decode_control_message(raw_text)
    except json.JSONDecodeError:
        await websocket.send_text(protocol.encode_control_message("ack", {"echo": raw_text}))
        return

    if control.get("type") != protocol.MSG_TYPE_CONTROL:
        await websocket.send_text(protocol.encode_control_message("ack", {"echo": raw_text}))
        return

    event = control.get("event")
    if event == "speech_end":
        logger.info("control_event client=%s event=speech_end", websocket.client)
        await _flush_transcription(websocket)
    elif event == "reset_buffer":
        websocket.state.audio_buffer.clear()
        logger.info("control_event client=%s event=reset_buffer", websocket.client)
        await websocket.send_text(protocol.encode_control_message("ack", {"event": "reset_buffer"}))
    elif event == "text_input":
        payload = control.get("payload") or {}
        try:
            await _process_text_input(websocket, payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("text_input_failed client=%s error=%s", websocket.client, exc)
            await websocket.send_text(
                protocol.encode_control_message(
                    "error",
                    {
                        "detail": "text_input_failed",
                        "error": str(exc),
                    },
                )
            )
    else:
        logger.debug("control_event client=%s event=%s", websocket.client, event)
        await websocket.send_text(protocol.encode_control_message("ack", {"event": event}))


async def _flush_transcription(websocket: WebSocket) -> None:
    """Run STT + LLM + TTS for the buffered audio and reset the buffer."""
    audio_buffer: AudioStreamBuffer = websocket.state.audio_buffer
    if audio_buffer.is_empty():
        logger.info("flush_skipped client=%s reason=no_audio", websocket.client)
        await websocket.send_text(protocol.encode_control_message("noop", {"detail": "no audio buffered"}))
        return

    timer = StageTimer()
    try:
        pcm_bytes, header = audio_buffer.snapshot()
        duration_ms = _estimate_duration_ms(len(pcm_bytes), header)
        logger.info(
            "flush_begin client=%s buffered_bytes=%d est_duration_ms=%.2f",
            websocket.client,
            len(pcm_bytes),
            duration_ms,
        )
        transcript = transcribe_audio(pcm_bytes, header)
        timer.mark("stt")
    except ValueError as exc:
        logger.error("flush_failed client=%s error=%s", websocket.client, exc)
        await websocket.send_text(protocol.encode_control_message("error", {"detail": str(exc)}))
        audio_buffer.clear()
        return

    chat_history: list[dict[str, str]] = websocket.state.chat_history
    reply_text = generate_reply(transcript, chat_history)
    timer.mark("llm")
    tts_bytes = synthesize_speech(reply_text)
    timer.mark("tts")

    # Maintain per-connection history so the LLM can reference prior turns.
    chat_history.append({"role": "user", "content": transcript})
    chat_history.append({"role": "assistant", "content": reply_text})

    timings = timer.metrics()
    logger.info("timings=%s transcript_len=%d reply_len=%d", timings, len(transcript), len(reply_text))

    await websocket.send_text(
        protocol.encode_control_message(
            "transcription_ready",
            {
                "header": {
                    "sample_rate": header.sample_rate,
                    "channels": header.channels,
                    "bits_per_sample": header.bits_per_sample,
                    "flags": header.flags,
                },
                "payload_bytes": len(pcm_bytes),
                "transcript": transcript,
                "reply": reply_text,
            },
        )
    )

    # TODO: stream synthesized TTS bytes over WebSocket once streaming is implemented.
    await websocket.send_bytes(tts_bytes)
    audio_buffer.clear()


async def _process_text_input(websocket: WebSocket, payload: dict) -> None:
    """Handle a text-only turn (skip STT, run LLM with optional TTS)."""
    text = (payload.get("text") or "").strip()
    skip_tts = bool(payload.get("skip_tts"))
    if not text:
        await websocket.send_text(protocol.encode_control_message("error", {"detail": "empty text input"}))
        return

    timer = StageTimer()
    transcript = text
    chat_history: list[dict[str, str]] = websocket.state.chat_history
    reply_text = generate_reply(transcript, chat_history)
    timer.mark("llm")
    tts_bytes = b""
    if not skip_tts:
        tts_bytes = synthesize_speech(reply_text)
        timer.mark("tts")

    chat_history.append({"role": "user", "content": transcript})
    chat_history.append({"role": "assistant", "content": reply_text})

    timings = timer.metrics()
    logger.info(
        "text_input_processed client=%s timings=%s transcript_len=%d reply_len=%d skip_tts=%s",
        websocket.client,
        timings,
        len(transcript),
        len(reply_text),
        skip_tts,
    )

    await websocket.send_text(
        protocol.encode_control_message(
            "transcription_ready",
            {
                "header": None,
                "payload_bytes": 0,
                "transcript": transcript,
                "reply": reply_text,
                "timings": timings,
                "tts_skipped": skip_tts,
            },
        )
    )
    if not skip_tts:
        await websocket.send_bytes(tts_bytes)
