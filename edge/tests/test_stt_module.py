import pathlib
import struct
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from speaking_stone_edge import protocol, stt_module


def test_pcm16_conversion_validates_header():
    header = protocol.AudioFrameHeader(
        sequence=0,
        payload_len=4,
        sample_rate=16000,
        channels=1,
        bits_per_sample=16,
    )
    pcm = struct.pack("<hh", 0, 32767)
    samples = stt_module._pcm16_mono_to_float32(pcm, header)
    assert samples.dtype.name == "float32"
    assert samples.shape[0] == 2
    assert samples[0] == 0
    assert samples[1] == 32767 / 32768.0


def test_transcribe_audio_uses_model(monkeypatch):
    header = protocol.AudioFrameHeader(
        sequence=1,
        payload_len=4,
        sample_rate=16000,
        channels=1,
        bits_per_sample=16,
    )
    pcm = struct.pack("<hh", 0, 0)

    captured = {}

    class DummySegment:
        def __init__(self, text: str):
            self.text = text

    class DummyModel:
        def transcribe(self, audio, language, vad_filter):
            captured["language"] = language
            captured["vad_filter"] = vad_filter
            captured["audio_len"] = len(audio)
            return [DummySegment(" hi there ")], None

    monkeypatch.setattr(stt_module, "_get_model", lambda: DummyModel())
    text = stt_module.transcribe_audio(pcm, header)

    assert text == "hi there"
    assert captured["vad_filter"] is True
    assert captured["audio_len"] == 2


def test_transcribe_audio_rejects_wrong_sample_rate():
    header = protocol.AudioFrameHeader(
        sequence=2,
        payload_len=4,
        sample_rate=8000,
        channels=1,
        bits_per_sample=16,
    )
    pcm = struct.pack("<hh", 0, 0)

    with pytest.raises(ValueError):
        stt_module.transcribe_audio(pcm, header)
