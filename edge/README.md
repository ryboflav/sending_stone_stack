# Speaking Stone Edge – Audio Streaming Plan

## Overview

The ESP32-S3 firmware will use push-to-talk. While the user holds the button the device will STREAM PCM frames to the edge service over the `/ws/audio` websocket. The server buffers those frames per connection, stitches them into larger windows, and only calls Whisper when either (a) enough audio has accumulated or (b) the device signals end of speech. This gives near-real-time transcripts and avoids storing entire recordings on the microcontroller.

## Frame format

- Each frame is a binary blob: the `AudioFrameHeader` (see `speaking_stone_edge/protocol.py`) followed by `payload_len` bytes of raw PCM16 mono at 16 kHz.
- Frames should be sent every ~50–100 ms while recording so latency stays low, and `sequence` increments for easier reassembly.
- If the device needs to drop or retry a frame it should still keep the sequence monotonic; the server will detect gaps.

## Push-to-talk flow

1. Button press: send a control message telling the server that speech capture started (optional but helps reset buffers).
2. Stream frames continually until the button is released. Do not wait to accumulate the entire utterance.
3. Button release: send a `MSG_TYPE_CONTROL` event such as `speech_end` so the server knows to flush any buffered audio through STT and then reply via TTS.

## Server expectations

- `audio_websocket` now keeps per-connection state (`AudioStreamBuffer`) where incoming frame payloads are appended.
- Control messages with `event: "speech_end"` trigger Whisper+LLM+TTS for the buffered audio, and the server replies with a `transcription_ready` control payload plus a binary chunk containing placeholder TTS bytes.
- `_pcm16_mono_to_float32` already enforces 16-bit mono; any violations or mid-stream parameter changes are reported back as control errors instead of crashing the socket.
- The initial implementation only flushes on `speech_end`, but once we have empirical latency data we can add time-based or VAD-based flushing.

## Why not full-utterance uploads?

Sending the entire recording only after the button is released is discouraged:

- Memory pressure: PCM16 mono at 16 kHz consumes ~32 KB per second, so a 5 s utterance is ~160 KB. That can exhaust SRAM/PSRAM on the ESP32-S3 once you include networking buffers.
- Latency: Whisper cannot start until the whole buffer finishes transmitting, so the round-trip includes recording time + upload time + transcription time.
- Reliability: Re-sending a large binary blob after Wi-Fi hiccups is costlier than re-transmitting a small frame.

A whole-utterance fallback is possible for testing, but it should be treated as a staging-mode convenience rather than the production path.

## Next steps

- Firmware: implement the chunked send loop, the `speech_end` control message, and any retry/backoff logic for frames.
- Edge: add the buffering/VAD logic described above along with structured error responses when invalid audio parameters are detected.

## Local WebSocket simulator

Run the edge server (for example via `uvicorn speaking_stone_edge.main:app --reload --port 8000`) and then replay a WAV clip through the full pipeline without any external hardware:

```
python -m tools.audio_ws_simulator tests/data/audio/test_speech.wav --chunk-ms 80
```

The simulator converts the clip to 16 kHz mono PCM16, streams frames to `/ws/audio`, triggers `speech_end`, writes the synthesized reply to `tests/data/audio/output.wav`, and prints any control/TTS responses from the service. Per-stage timing metrics are logged on the backend so you can quantify latency end-to-end. See `docs/local_ws_simulator.md` for details.

## LLM configuration (OpenRouter)

1. Install dependencies after pulling updates:
   ```
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set the private values (the `.env` file is gitignored):
   ```
   cp .env.example .env
   ```
3. Populate `OPENROUTER_API_KEY` with your key and (optionally) override `OPENROUTER_MODEL`, `OPENROUTER_REFERRER`, or `OPENROUTER_APP_TITLE`.
4. Start the server; the backend will load the API key at startup and `generate_reply` will call OpenRouter’s `/chat/completions` endpoint for every utterance. If the key is missing or a request fails, the system falls back to an “Echoing your words” response so the rest of the pipeline keeps working.

## TTS configuration (Piper)

1. Install the new dependency if you haven’t already:
   ```
   pip install -r requirements.txt
   ```
2. Download a Piper voice package (both `.onnx` and `.onnx.json`) from the [Piper releases](https://github.com/rhasspy/piper/releases) page and place it somewhere inside the repo, e.g. `tests/data/tts/en_US-amy-low.onnx`.
3. Update `.env` with `PIPER_MODEL_PATH` (and optionally `PIPER_CONFIG_PATH`, `PIPER_SPEAKER_ID`, `PIPER_USE_CUDA`). See `.env.example` for the variables.
4. Restart the FastAPI server; `speaking_stone_edge.tts_module` loads the Piper model once at startup and converts replies into 16 kHz PCM16 bytes. If the model isn’t configured or synthesis fails, we fall back to placeholder bytes so the websocket contract stays intact.
