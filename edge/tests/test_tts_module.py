import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from speaking_stone_edge import tts_module


def test_synthesize_speech_falls_back_without_voice(monkeypatch):
    monkeypatch.setattr(tts_module, "_synthesize_with_piper", lambda text: None)
    data = tts_module.synthesize_speech("testing fallback")
    assert data.startswith(b"[tts-placeholder")
