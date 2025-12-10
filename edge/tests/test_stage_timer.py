import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from speaking_stone_edge import main


def test_stage_timer_tracks_multiple_marks(monkeypatch):
    times = iter([0.0, 0.05, 0.2])
    monkeypatch.setattr(main.time, "perf_counter", lambda: next(times))

    timer = main.StageTimer()
    timer.mark("stt")
    timer.mark("llm")

    metrics = timer.metrics()
    assert metrics["stt_ms"] == 50.0
    assert metrics["llm_ms"] == 150.0
    assert metrics["total_ms"] == 200.0


def test_stage_timer_without_marks_reports_zero(monkeypatch):
    monkeypatch.setattr(main.time, "perf_counter", lambda: 0.0)
    timer = main.StageTimer()
    metrics = timer.metrics()
    assert metrics["total_ms"] == 0.0
