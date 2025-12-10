import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from speaking_stone_edge import protocol


def test_audio_frame_header_roundtrip():
    header = protocol.AudioFrameHeader(
        sequence=42,
        payload_len=1600,
        sample_rate=16000,
        channels=1,
        bits_per_sample=16,
        flags=3,
    )
    raw = header.to_bytes()

    assert len(raw) == protocol.HEADER_SIZE
    decoded = protocol.AudioFrameHeader.from_bytes(raw)
    assert decoded == header


def test_audio_frame_header_requires_minimum_bytes():
    too_short = b"\x00\x01"
    try:
        protocol.AudioFrameHeader.from_bytes(too_short)
    except ValueError as exc:
        assert "expected" in str(exc)
    else:
        raise AssertionError("Expected ValueError to be raised for short header")
