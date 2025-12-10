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
