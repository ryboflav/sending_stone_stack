# Local WebSocket simulator

1. Start the edge service:

   ```
   uvicorn speaking_stone_edge.main:app --reload --port 8000
   ```

2. Replay a WAV clip (default chunk size ~80 ms). The simulator will downmix/resample to 16 kHz mono PCM16 automatically:

   ```
   python -m tools.audio_ws_simulator tests/data/audio/test_speech.wav --chunk-ms 80
   ```

3. Watch the console for control messages and TTS byte counts. The script writes any synthesized reply to `tests/data/audio/output.wav` (16 kHz mono WAV) so you can listen afterward, and the FastAPI server logs print per-stage timing metrics (STT/LLM/TTS + total) for each utterance.

Notes:
- TTS is returned as a single binary payload immediately after the `transcription_ready` control message (no streaming chunks yet).
- A `reset_buffer` control event at the start of capture clears any prior audio for the connection; the simulator does not send it, but firmware should.

## Text-only chat simulator

If you just want to type turns and exercise LLM + TTS (skip STT), start the edge service as above, then run:

```
python -m tools.chat_ws_simulator --text "hello there"
```

or enter an interactive loop:

```
python -m tools.chat_ws_simulator  # add --ping-interval 20 to keep the socket alive during long pauses
```

Replies print to the console and the synthesized audio is written to `tests/data/audio/chat_output.wav` (or per-turn files when interactive). Add `--skip-tts` to exercise only the LLM without synthesizing audio.
