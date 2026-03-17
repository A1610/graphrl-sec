"""
Temporal window manager for streaming graph construction.

Implements a sliding window over UnifiedEvent streams.  Each window
produces a complete set of edges and node statistics that can be
converted to a PyG HeteroData snapshot.

Window model:
  - Fixed size:  window_size_hours (default 1 h)
  - Slide step:  window_slide_minutes (default 15 min)
  - Overlap:     window_size - slide (45 min default)

Events are bucketed by their Unix timestamp.  Windows are emitted
as soon as all events within [start, end) are available.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Generator, Iterable
from dataclasses import dataclass

import structlog

from src.graph.config import GraphConfig, graph_settings
from src.graph.edge_constructor import EdgeAccumulator, EdgeConstructor
from src.graph.node_registry import NodeRegistry
from src.ingestion.schemas import UnifiedEvent

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Window descriptor
# ---------------------------------------------------------------------------


@dataclass
class TimeWindow:
    """Metadata for a single temporal graph window."""

    window_id:   int
    start_ts:    float   # inclusive  (Unix seconds)
    end_ts:      float   # exclusive  (Unix seconds)
    num_events:  int = 0

    @property
    def duration_s(self) -> float:
        return self.end_ts - self.start_ts

    @property
    def midpoint_ts(self) -> float:
        return (self.start_ts + self.end_ts) / 2.0

    def __repr__(self) -> str:
        from datetime import datetime, timezone
        start = datetime.fromtimestamp(self.start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        end   = datetime.fromtimestamp(self.end_ts,   tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"TimeWindow(id={self.window_id}, [{start}, {end}), events={self.num_events})"


# ---------------------------------------------------------------------------
# Window result (window + its accumulated edges)
# ---------------------------------------------------------------------------


@dataclass
class WindowResult:
    """Output of processing one temporal window."""

    window:      TimeWindow
    accumulator: EdgeAccumulator
    registry:    NodeRegistry     # snapshot after this window


# ---------------------------------------------------------------------------
# Sliding window engine
# ---------------------------------------------------------------------------


class SlidingWindowEngine:
    """
    Partitions a sorted stream of UnifiedEvents into overlapping windows.

    Usage::

        engine = SlidingWindowEngine()
        for result in engine.process_stream(events):
            pyg_data = converter.convert(result)

    Thread safety: NOT thread-safe — designed for single-threaded streaming.
    """

    def __init__(self, config: GraphConfig | None = None) -> None:
        self._config = config or graph_settings
        self._window_size_s = self._config.window_size_hours * 3600.0
        self._slide_s       = self._config.window_slide_minutes * 60.0

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    def process_stream(
        self,
        events: Iterable[UnifiedEvent],
    ) -> Generator[WindowResult, None, None]:
        """
        Process a time-ordered stream of events into window results.

        Args:
            events: Events in ascending timestamp order.

        Yields:
            WindowResult for each completed window.
        """
        # Buffer events in memory — keyed by window_start_ts
        # Each event may appear in multiple windows (size > slide).
        event_buffer: dict[float, list[UnifiedEvent]] = defaultdict(list)
        window_counter = 0
        first_ts: float | None = None
        last_ts:  float | None = None

        for event in events:
            ts = event.timestamp.timestamp()

            if first_ts is None:
                first_ts = ts
            last_ts = ts

            # Determine which window slots this event belongs to
            earliest_window_start = self._window_start_for_ts(ts - self._window_size_s + self._slide_s)
            latest_window_start   = self._window_start_for_ts(ts)

            ws = earliest_window_start
            while ws <= latest_window_start:
                event_buffer[ws].append(event)
                ws += self._slide_s

            # Emit windows that are fully past (all events have been seen)
            ready_starts = sorted(k for k in event_buffer if k + self._window_size_s <= ts)

            for ws in ready_starts:
                window_events = event_buffer.pop(ws)
                window = TimeWindow(
                    window_id=window_counter,
                    start_ts=ws,
                    end_ts=ws + self._window_size_s,
                    num_events=len(window_events),
                )
                window_counter += 1

                # Fresh registry per window (independent snapshots)
                win_reg = NodeRegistry(self._config)
                win_constructor = EdgeConstructor(win_reg, self._config)
                acc = win_constructor.process_batch(
                    window_events, ws, ws + self._window_size_s
                )

                logger.info(
                    "window_ready",
                    window_id=window.window_id,
                    events=window.num_events,
                    edges=acc.num_edges,
                    nodes=win_reg.total_nodes,
                )
                yield WindowResult(window=window, accumulator=acc, registry=win_reg)

        # Flush remaining buffered windows at stream end
        for ws in sorted(event_buffer):
            window_events = event_buffer[ws]
            if not window_events:
                continue
            window = TimeWindow(
                window_id=window_counter,
                start_ts=ws,
                end_ts=ws + self._window_size_s,
                num_events=len(window_events),
            )
            window_counter += 1

            win_reg = NodeRegistry(self._config)
            win_constructor = EdgeConstructor(win_reg, self._config)
            acc = win_constructor.process_batch(
                window_events, ws, ws + self._window_size_s
            )

            logger.info(
                "window_flushed",
                window_id=window.window_id,
                events=window.num_events,
                edges=acc.num_edges,
                nodes=win_reg.total_nodes,
            )
            yield WindowResult(window=window, accumulator=acc, registry=win_reg)

        logger.info(
            "stream_complete",
            total_windows=window_counter,
            first_ts=first_ts,
            last_ts=last_ts,
        )

    def compute_windows(
        self,
        start_ts: float,
        end_ts: float,
    ) -> list[TimeWindow]:
        """
        Pre-compute all window boundaries for a known time range.

        Useful for pre-allocating storage or progress bars.
        """
        windows: list[TimeWindow] = []
        ws = self._window_start_for_ts(start_ts)
        wid = 0
        while ws < end_ts:
            windows.append(TimeWindow(
                window_id=wid,
                start_ts=ws,
                end_ts=min(ws + self._window_size_s, end_ts),
            ))
            ws += self._slide_s
            wid += 1
        return windows

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _window_start_for_ts(self, ts: float) -> float:
        """Snap a timestamp to the nearest slide-aligned window start."""
        return math.floor(ts / self._slide_s) * self._slide_s
