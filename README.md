# Speaking Stone Stack

Scaffold for a split workflow: Edge compute service (FastAPI, WebSockets) in a devcontainer, and ESP32 firmware (ESP-IDF, FreeRTOS) on host. Two independent VS Code windows can open `edge/` and `firmware/` without sharing toolchains.

## Layout
- `shared/` — notes for protocol constants used by both sides.
- `edge/` — FastAPI server scaffold with devcontainer and docker-compose.
- `firmware/` — ESP-IDF firmware skeleton for ESP32.

## Quick start
### Edge (devcontainer)
1. Open `edge/` in VS Code and reopen in devcontainer.
2. Container starts `uvicorn speaking_stone_edge.main:app --host 0.0.0.0 --port 8000` by default.
3. Send WebSocket frames to `ws://localhost:8000/ws/audio` to see echo placeholders.

### Firmware (host)
1. Open `firmware/` in a separate VS Code window with ESP-IDF extension configured.
2. Configure Wi-Fi credentials via `sdkconfig.defaults` (or menuconfig).
3. Build/flash normally; firmware logs simulated audio send/receive.

## Notes
- All STT/LLM/TTS/audio/WebSocket streaming logic is placeholder with TODOs for later implementation.
- Keep protocol constants aligned between `shared/protocol.md`, `edge/speaking_stone_edge/protocol.py`, and `firmware/main/protocol.h`.
