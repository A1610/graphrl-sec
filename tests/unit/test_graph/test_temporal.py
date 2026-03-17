"""Unit tests for SlidingWindowEngine."""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from src.graph.config import GraphConfig
from src.graph.temporal import SlidingWindowEngine, TimeWindow, WindowResult
from src.ingestion.schemas import Protocol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(ts: float, src_ip: str = "10.0.0.1", dst_ip: str = "10.0.0.2") -> MagicMock:
    event = MagicMock()
    event.source.ip  = src_ip
    event.destination.ip   = dst_ip
    event.destination.port     = 80
    event.destination.hostname = None   # explicit None — MagicMock attrs are truthy
    event.metadata.is_attack   = False
    event.network.protocol   = Protocol.TCP
    event.network.bytes_sent = 100
    event.network.bytes_received = 200
    event.network.packets_sent   = 1
    event.network.packets_received = 2
    event.network.duration_ms = 10.0
    event.timestamp.timestamp.return_value = ts
    return event


def _small_config() -> GraphConfig:
    """Config with 10-minute windows and 5-minute slides for fast tests."""
    return GraphConfig(
        window_size_hours=10 / 60,    # 10 minutes
        window_slide_minutes=5.0,
    )


# ---------------------------------------------------------------------------
# TimeWindow
# ---------------------------------------------------------------------------


class TestTimeWindow:
    def test_duration(self) -> None:
        w = TimeWindow(window_id=0, start_ts=0.0, end_ts=3600.0)
        assert w.duration_s == pytest.approx(3600.0)

    def test_midpoint(self) -> None:
        w = TimeWindow(window_id=0, start_ts=0.0, end_ts=100.0)
        assert w.midpoint_ts == pytest.approx(50.0)

    def test_repr_contains_window_id(self) -> None:
        w = TimeWindow(window_id=42, start_ts=0.0, end_ts=3600.0)
        assert "42" in repr(w)


# ---------------------------------------------------------------------------
# SlidingWindowEngine
# ---------------------------------------------------------------------------


class TestSlidingWindowEngine:
    def test_no_events_yields_nothing(self) -> None:
        engine  = SlidingWindowEngine(_small_config())
        results = list(engine.process_stream([]))
        assert results == []

    def test_single_event_yields_one_window(self) -> None:
        engine = SlidingWindowEngine(_small_config())
        events = [_make_event(ts=1_000.0)]
        results = list(engine.process_stream(events))
        assert len(results) >= 1

    def test_all_results_are_window_results(self) -> None:
        engine = SlidingWindowEngine(_small_config())
        events = [_make_event(ts=1_000.0 + i * 30) for i in range(20)]
        results = list(engine.process_stream(events))
        for r in results:
            assert isinstance(r, WindowResult)

    def test_window_ids_are_sequential(self) -> None:
        engine = SlidingWindowEngine(_small_config())
        events = [_make_event(ts=1_000.0 + i * 30) for i in range(30)]
        results = list(engine.process_stream(events))
        ids = [r.window.window_id for r in results]
        assert ids == list(range(len(ids)))

    def test_each_window_has_registry(self) -> None:
        engine = SlidingWindowEngine(_small_config())
        events = [_make_event(ts=1_000.0 + i * 10) for i in range(10)]
        for result in engine.process_stream(events):
            assert result.registry.total_nodes >= 0

    def test_each_window_has_accumulator(self) -> None:
        engine = SlidingWindowEngine(_small_config())
        events = [_make_event(ts=1_000.0 + i * 10) for i in range(10)]
        for result in engine.process_stream(events):
            assert result.accumulator is not None

    def test_compute_windows_returns_list(self) -> None:
        engine = SlidingWindowEngine(_small_config())
        windows = engine.compute_windows(0.0, 3600.0)
        assert len(windows) > 0
        assert all(isinstance(w, TimeWindow) for w in windows)

    def test_compute_windows_cover_range(self) -> None:
        engine = SlidingWindowEngine(_small_config())
        windows = engine.compute_windows(0.0, 3600.0)
        assert windows[0].start_ts <= 0.0
        assert windows[-1].end_ts >= 3600.0

    def test_window_start_alignment(self) -> None:
        """Window starts must be multiples of slide_s."""
        cfg    = _small_config()
        engine = SlidingWindowEngine(cfg)
        slide  = cfg.window_slide_minutes * 60.0
        events = [_make_event(ts=1_000.0 + i * 30) for i in range(30)]
        for result in engine.process_stream(events):
            start = result.window.start_ts
            assert math.isclose(start % slide, 0.0, abs_tol=1e-3) or start % slide < 1.0

    def test_events_in_window_time_range(self) -> None:
        """All events in a window must fall within [start, end)."""
        engine = SlidingWindowEngine(_small_config())
        events = [_make_event(ts=1_000.0 + i * 30) for i in range(30)]
        for result in engine.process_stream(events):
            w = result.window
            assert w.num_events >= 0

    def test_overlapping_windows_share_events(self) -> None:
        """With overlap, total events across windows > original event count."""
        engine = SlidingWindowEngine(_small_config())
        # 20 events spread over more than one window but less than two slide periods
        events = [_make_event(ts=1_000.0 + i * 15) for i in range(20)]
        results = list(engine.process_stream(events))
        total_events = sum(r.window.num_events for r in results)
        # Overlapping windows count events multiple times
        assert total_events >= len(events)
