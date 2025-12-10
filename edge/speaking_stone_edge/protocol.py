"""Shared protocol constants and helpers for edge service.

Keep these values aligned with shared/protocol.md and firmware/main/protocol.h.
"""

import json
import struct
from dataclasses import dataclass
from typing import Any, Dict, Tuple

MSG_TYPE_AUDIO_CHUNK = "MSG_TYPE_AUDIO_CHUNK"
MSG_TYPE_TTS_CHUNK = "MSG_TYPE_TTS_CHUNK"
MSG_TYPE_CONTROL = "MSG_TYPE_CONTROL"


HEADER_STRUCT = struct.Struct("<HHHBBH")
HEADER_SIZE = HEADER_STRUCT.size


@dataclass(frozen=True)
class AudioFrameHeader:
    """Binary header prepended to each PCM frame sent over the websocket."""

    sequence: int
    payload_len: int
    sample_rate: int
    channels: int
    bits_per_sample: int
    flags: int = 0

    def to_bytes(self) -> bytes:
        """Return the packed binary header."""
        return HEADER_STRUCT.pack(
            self.sequence,
            self.payload_len,
            self.sample_rate,
            self.channels,
            self.bits_per_sample,
            self.flags,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "AudioFrameHeader":
        """Decode binary header bytes."""
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Incomplete audio header: expected {HEADER_SIZE} bytes, got {len(data)}")
        unpacked: Tuple[int, int, int, int, int, int] = HEADER_STRUCT.unpack_from(data)
        return cls(*unpacked)


def encode_control_message(event: str, payload: Dict[str, Any]) -> str:
    """Encode a control message as a JSON string."""
    return json.dumps({"type": MSG_TYPE_CONTROL, "event": event, "payload": payload})


def decode_control_message(raw: str) -> Dict[str, Any]:
    """Decode a control message JSON string."""
    return json.loads(raw)
