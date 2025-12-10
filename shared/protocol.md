# Speaking Stone Protocol (Draft)

Minimal placeholder protocol shared between ESP32 firmware and edge service.

## Message types
- `MSG_TYPE_AUDIO_CHUNK` — binary/audio chunk streamed from firmware to edge.
- `MSG_TYPE_TTS_CHUNK` — binary/tts audio chunk streamed from edge to firmware.
- `MSG_TYPE_CONTROL` — JSON control or status messages.

## Encoding
- Control messages use UTF-8 JSON objects with `type` and `payload` fields.
- Binary audio/tts frames are raw bytes; use accompanying control frames to describe them if needed.

## TODO
- Define sequencing, framing, and authentication.
- Add retry/reconnect handling and error codes.
