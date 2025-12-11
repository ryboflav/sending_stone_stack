# Speaking Stone – ESP32 Firmware Notes

This firmware streams push-to-talk audio to the edge service and plays back the TTS reply. The edge backend is already live at `/ws/audio`; your job is to format frames correctly and send the right control events.

## WebSocket protocol

- URL: `ws://<edge-host>:8000/ws/audio`
- On connect, the server replies with a control JSON like `{"type":"MSG_TYPE_CONTROL","event":"connected",...}`.
- Audio frames are **binary**: a 12-byte header followed by raw PCM16 mono @ 16,000 Hz.
- Control messages are **text JSON** with `type: "MSG_TYPE_CONTROL"`.

### Audio frame header (`speaking_stone_edge/protocol.py`)

Little-endian struct `<HHHBBH>`:

| field           | type | notes                                    |
|-----------------|------|------------------------------------------|
| sequence        | u16  | increment per frame                      |
| payload_len     | u16  | bytes of PCM that follow (max 65,535)    |
| sample_rate     | u16  | **must be 16000**                        |
| channels        | u8   | **must be 1** (mono)                     |
| bits_per_sample | u8   | **must be 16**                           |
| flags           | u16  | reserved (set 0)                         |

Payload: `payload_len` bytes of PCM16 mono @ 16 kHz. Keep frames ~50–100 ms so latency and payload_len stay small.

### Control events (JSON text)

- `reset_buffer`: clear any prior buffered audio for this socket. Send when PTT starts.
- `speech_end`: trigger STT → LLM → TTS for all buffered audio. Mandatory (there is no auto-flush).
- `text_input` (optional): `{"type":"MSG_TYPE_CONTROL","event":"text_input","payload":{"text":"hello","skip_tts":false}}` to send text-only turns.

The server responds to `speech_end` with:
1) A `transcription_ready` control message containing transcript + reply text.
2) One **binary** message containing the entire TTS reply as PCM16 mono @ 16 kHz (single chunk; no TTS streaming yet).

## Firmware send loop (PTT)

1. On button press: send `reset_buffer`.
2. While recording: capture audio, resample/downmix to 16 kHz mono PCM16, chunk into ~80 ms frames, and send header + payload. Keep `sequence` increasing even if you drop a frame.
3. On button release: send `speech_end`.

## Firmware receive loop

- Read text messages; when `event == "transcription_ready"`, note transcript/reply.
- The first binary message after that is the full TTS PCM. Play it directly (mono, 16-bit, 16 kHz).
- There’s no framing on TTS yet (`MSG_TYPE_TTS_CHUNK` is unused).

## Constraints & error cases

- Mid-stream changes to sample rate/channels/bit depth are rejected and clear the buffer.
- No retry/ack for gaps; lost frames just reduce audio quality.
- If `speech_end` is never sent, audio will accumulate and never be processed.

## Test against the edge locally

- Start the edge server: `uvicorn speaking_stone_edge.main:app --reload --port 8000`
- Use the simulator as a reference: `python -m tools.audio_ws_simulator tests/data/audio/test_speech.wav --chunk-ms 80`

## Secrets (Wi-Fi + edge host)

- Copy `main/secrets.example.h` to `main/secrets.h` and fill in `WIFI_SSID`, `WIFI_PASSWORD`, `EDGE_HOST`, `EDGE_PORT`, and `DEVICE_NAME` for your environment.
- `main/secrets.h` is gitignored; keep only the `secrets.example.h` template in source control.
- Include `main/secrets.h` in your code (or read its values into NVS/menuconfig) before bringing up Wi-Fi or opening the WebSocket.

### Using menuconfig (preferred for local-only secrets)

- Config options live in `main/Kconfig.projbuild` (`CONFIG_WIFI_SSID`, `CONFIG_WIFI_PASSWORD`, `CONFIG_EDGE_HOST`, `CONFIG_EDGE_PORT`, `CONFIG_DEVICE_NAME`).
- Keep your local overrides out of git: copy `sdkconfig.defaults.local.example` to `sdkconfig.defaults.local` (gitignored) and fill in your values.
- The project `CMakeLists.txt` sets `IDF_SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.local"` so both fragments load automatically on `idf.py build`. No extra flags needed as long as `sdkconfig.defaults.local` exists.
- Do not commit `sdkconfig`, `sdkconfig.local`, or `sdkconfig.defaults.local`; only the `*.example` stays in source control.

On boot the firmware initializes NVS, sets up Wi-Fi station mode with `CONFIG_WIFI_SSID`/`CONFIG_WIFI_PASSWORD`, and logs progress over the serial port.
