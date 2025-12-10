import pathlib
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from speaking_stone_edge import main, protocol


def _header(**overrides):
    base = dict(
        sequence=0,
        payload_len=4,
        sample_rate=16000,
        channels=1,
        bits_per_sample=16,
        flags=0,
    )
    base.update(overrides)
    return protocol.AudioFrameHeader(**base)


def test_audio_stream_buffer_append_and_snapshot():
    buf = main.AudioStreamBuffer()
    header = _header()
    payload = b"\x00\x01\x02\x03"

    buf.append_frame(header, payload)
    data, stored_header = buf.snapshot()

    assert data == payload
    assert stored_header == header
    assert buf.is_empty() is False


def test_audio_stream_buffer_rejects_parameter_changes():
    buf = main.AudioStreamBuffer()
    buf.append_frame(_header(), b"\x00\x01\x02\x03")

    with pytest.raises(ValueError):
        buf.append_frame(_header(sample_rate=8000), b"\x00\x01\x02\x03")

    with pytest.raises(ValueError):
        buf.append_frame(_header(channels=2), b"\x00\x01\x02\x03")

    with pytest.raises(ValueError):
        buf.append_frame(_header(bits_per_sample=8), b"\x00\x01\x02\x03")


def test_audio_stream_buffer_snapshot_without_data():
    buf = main.AudioStreamBuffer()

    with pytest.raises(ValueError):
        buf.snapshot()

    buf.append_frame(_header(), b"\x00\x01\x02\x03")
    buf.clear()
    with pytest.raises(ValueError):
        buf.snapshot()
