"""Stream microphone audio over the websocket with push-to-talk controls."""

from __future__ import annotations

import argparse
import asyncio
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import sounddevice as sd
import websockets
from pynput import keyboard, mouse

from speaking_stone_edge import protocol

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # bytes (16-bit)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
        default=0.5,
        help="Seconds to wait after sending speech_end before accepting the next turn",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Input device id/name for sounddevice (defaults to system default)",
    )
    parser.add_argument(
        "--push-key",
        default="space",
        help="Keyboard key to hold for push-to-talk (set to 'none' to disable)",
    )
    parser.add_argument(
        "--push-button",
        default="right",
        choices=["left", "right", "middle", "none"],
        help="Mouse button to hold for push-to-talk",
    )
    parser.add_argument(
        "--output-wav",
        type=Path,
        default=Path("tests/data/audio/mic_output.wav"),
        help="Where to save any synthesized PCM as a WAV file",
    )
    return parser.parse_args()


def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(TARGET_CHANNELS)
        wav.setsampwidth(TARGET_SAMPLE_WIDTH)
        wav.setframerate(TARGET_SAMPLE_RATE)
        wav.writeframes(pcm)


async def _listen_for_responses(
    ws: websockets.WebSocketClientProtocol, output_path: Path
) -> None:
    collected = bytearray()
    try:
        while True:
            message = await ws.recv()
            if isinstance(message, str):
                print(f"<< text: {message}")
            else:
                print(f"<< received {len(message)} bytes (likely TTS chunk)")
                collected.extend(message)
    except websockets.ConnectionClosed:
        print("<< connection closed by server")
    finally:
        if collected:
            _write_wav(output_path, bytes(collected))
            print(f"<< wrote synthesized audio to {output_path}")


@dataclass
class _PushState:
    active: bool = False
    stop_event: Optional[asyncio.Event] = None
    task: Optional[asyncio.Task[None]] = None


def _key_matches(key: keyboard.Key | keyboard.KeyCode, binding: str) -> bool:
    if binding == "none":
        return False
    if isinstance(key, keyboard.Key) and key.name == binding:
        return True
    if isinstance(key, keyboard.KeyCode) and binding and len(binding) == 1:
        return key.char == binding
    return False


def _mouse_matches(button: mouse.Button, binding: str) -> bool:
    if binding == "none":
        return False
    return (binding == "left" and button is mouse.Button.left) or (
        binding == "right" and button is mouse.Button.right
    ) or (binding == "middle" and button is mouse.Button.middle)


def _build_listeners(
    loop: asyncio.AbstractEventLoop,
    events: asyncio.Queue[str],
    push_key: str,
    push_button: str,
) -> list:
    listeners = []

    def enqueue(event: str) -> None:
        asyncio.run_coroutine_threadsafe(events.put(event), loop)

    if push_key != "none":
        def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:
            if _key_matches(key, push_key):
                enqueue("start")

        def on_release(key: keyboard.Key | keyboard.KeyCode) -> None:
            if _key_matches(key, push_key):
                enqueue("stop")

        listeners.append(keyboard.Listener(on_press=on_press, on_release=on_release))

    if push_button != "none":
        def on_click(
            x: int, y: int, button: mouse.Button, pressed: bool
        ) -> None:
            if _mouse_matches(button, push_button):
                enqueue("start" if pressed else "stop")

        listeners.append(mouse.Listener(on_click=on_click))

    return listeners


async def _stream_from_mic(
    ws: websockets.WebSocketClientProtocol,
    chunk_ms: int,
    device: Optional[str],
    stop_event: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    blocksize = max(1, int(TARGET_SAMPLE_RATE * chunk_ms / 1000))

    def callback(indata, frames, time_info, status) -> None:  # type: ignore[override]
        if status:
            print(f"!! input status: {status}", file=sys.stderr)
        # Copy bytes to avoid referencing sounddevice's internal buffer
        asyncio.run_coroutine_threadsafe(audio_queue.put(bytes(indata)), loop)

    print(">> recording (hold push-to-talk)...")
    with sd.RawInputStream(
        samplerate=TARGET_SAMPLE_RATE,
        blocksize=blocksize,
        channels=TARGET_CHANNELS,
        dtype="int16",
        device=device,
        callback=callback,
    ):
        sequence = 0
        while not stop_event.is_set() or not audio_queue.empty():
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            header = protocol.AudioFrameHeader(
                sequence=sequence,
                payload_len=len(chunk),
                sample_rate=TARGET_SAMPLE_RATE,
                channels=TARGET_CHANNELS,
                bits_per_sample=TARGET_SAMPLE_WIDTH * 8,
            )
            await ws.send(header.to_bytes() + chunk)
            sequence += 1

    await ws.send(protocol.encode_control_message("speech_end", {}))
    print(">> sent speech_end")


async def _manage_push_to_talk(
    ws: websockets.WebSocketClientProtocol,
    args: argparse.Namespace,
    events: asyncio.Queue[str],
) -> None:
    state = _PushState()
    while True:
        event = await events.get()
        if event == "start" and not state.active:
            state.active = True
            state.stop_event = asyncio.Event()
            state.task = asyncio.create_task(
                _stream_from_mic(ws, args.chunk_ms, args.device, state.stop_event)
            )
        elif event == "stop" and state.active and state.stop_event:
            state.stop_event.set()
            if state.task:
                await state.task
            await asyncio.sleep(args.post_delay)
            state.active = False
            state.stop_event = None
            state.task = None


async def _run(args: argparse.Namespace) -> None:
    loop = asyncio.get_running_loop()
    events: asyncio.Queue[str] = asyncio.Queue()

    listeners = _build_listeners(loop, events, args.push_key, args.push_button)
    for listener in listeners:
        listener.start()
    if not listeners:
        raise SystemExit("No push-to-talk inputs configured. Set --push-key or --push-button.")

    print(f"Connecting to {args.url} ...")
    async with websockets.connect(args.url, ping_interval=None) as ws:
        listener_task = asyncio.create_task(_listen_for_responses(ws, args.output_wav))
        try:
            await _manage_push_to_talk(ws, args, events)
        finally:
            for listener in listeners:
                listener.stop()
            await ws.close()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)


if __name__ == "__main__":
    main()
