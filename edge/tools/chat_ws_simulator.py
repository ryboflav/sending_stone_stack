"""Send typed text over the websocket to exercise LLM + TTS."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import wave

import websockets

from speaking_stone_edge import protocol, tts_module


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="ws://127.0.0.1:8000/ws/audio",
        help="Websocket URL for the edge server",
    )
    parser.add_argument(
        "--ping-interval",
        type=float,
        default=20.0,
        help="Send websocket pings every N seconds to keep the connection alive (set 0 to disable)",
    )
    parser.add_argument(
        "--text",
        help="Send a single text turn and exit (omit for interactive loop)",
    )
    parser.add_argument(
        "--skip-tts",
        action="store_true",
        help="Do not request TTS (exercise LLM only)",
    )
    parser.add_argument(
        "--output-wav",
        type=Path,
        default=Path("tests/data/audio/chat_output.wav"),
        help="Where to save synthesized PCM as a WAV file (overwrites per turn)",
    )
    return parser.parse_args()


def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(tts_module.TARGET_CHANNELS)
        wav.setsampwidth(tts_module.TARGET_SAMPLE_WIDTH)
        wav.setframerate(tts_module.TARGET_SAMPLE_RATE)
        wav.writeframes(pcm)


async def _send_text_turn(
    ws: websockets.WebSocketClientProtocol,
    text: str,
    output_path: Path,
    turn_index: int,
    single_turn: bool,
    skip_tts: bool,
) -> None:
    text = text.strip()
    if not text:
        print("!! empty input; skipping")
        return

    await ws.send(protocol.encode_control_message("text_input", {"text": text, "skip_tts": skip_tts}))
    print(f'>> sent text_input (turn {turn_index}): "{text}" skip_tts={skip_tts}')

    collected = bytearray()
    ready_seen = False
    while True:
        try:
            message = await ws.recv()
        except websockets.ConnectionClosed as exc:
            print(f"<< connection closed by server code={exc.code} reason={exc.reason}")
            break

        if isinstance(message, str):
            print(f"<< text: {message}")
            try:
                control = protocol.decode_control_message(message)
                event = control.get("event")
                payload = control.get("payload") or {}
                if event == "transcription_ready":
                    ready_seen = True
                    transcript = payload.get("transcript", "")
                    reply = payload.get("reply", "")
                    tts_skipped = payload.get("tts_skipped", False)
                    print(f'<< transcript: "{transcript}"')
                    print(f'<< reply: "{reply}"')
                    if tts_skipped:
                        print("<< TTS was skipped")
                        break
            except Exception:
                # Non-control text; keep looping.
                pass
        else:
            print(f"<< received {len(message)} bytes (TTS chunk)")
            collected.extend(message)
            if ready_seen:
                break

        if ready_seen and collected:
            break

    if collected:
        if single_turn:
            out_path = output_path
        else:
            out_path = output_path.with_name(f"{output_path.stem}_turn{turn_index}{output_path.suffix}")
        _write_wav(out_path, bytes(collected))
        print(f"<< wrote synthesized audio to {out_path}")


async def _run(args: argparse.Namespace) -> None:
    print(f"Connecting to {args.url} ...")
    ping_interval = None if args.ping_interval <= 0 else args.ping_interval
    async with websockets.connect(args.url, ping_interval=ping_interval) as ws:
        turn = 1
        if args.text:
            await _send_text_turn(ws, args.text, args.output_wav, turn, single_turn=True, skip_tts=args.skip_tts)
            return

        async def _ainput(prompt: str) -> str:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: input(prompt))

        while True:
            try:
                user_input = await _ainput("you> ")
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break
            if not user_input.strip():
                print("Exiting.")
                break
            await _send_text_turn(ws, user_input, args.output_wav, turn, single_turn=False, skip_tts=args.skip_tts)
            turn += 1


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)


if __name__ == "__main__":
    main()
