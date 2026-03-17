"""
Graph construction statistics — tracks metrics across windows.

Provides a lightweight collector that accumulates window-level counters
and exposes them as a flat dict (compatible with Prometheus / structlog).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from src.graph.temporal import WindowResult


@dataclass
class WindowStats:
    """Statistics for a single processed window."""

    window_id:         int
    num_events:        int
    num_nodes:         int
    num_edges:         int
    processing_time_s: float
    node_type_counts:  dict[str, int] = field(default_factory=dict)
    edge_type_counts:  dict[str, int] = field(default_factory=dict)


class GraphStatsCollector:
    """
    Thread-safe accumulator for graph construction metrics.

    Tracks totals and per-window stats for monitoring dashboards.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window_stats: list[WindowStats] = []
        self._total_events = 0
        self._total_nodes  = 0
        self._total_edges  = 0
        self._start_time   = time.monotonic()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_window(
        self,
        result: WindowResult,
        processing_time_s: float,
        node_type_counts: dict[str, int] | None = None,
        edge_type_counts: dict[str, int] | None = None,
    ) -> WindowStats:
        """Record metrics for a completed window."""
        w_stats = WindowStats(
            window_id=result.window.window_id,
            num_events=result.window.num_events,
            num_nodes=result.registry.total_nodes,
            num_edges=result.accumulator.num_edges,
            processing_time_s=processing_time_s,
            node_type_counts=node_type_counts or result.registry.counts_by_type(),
            edge_type_counts=edge_type_counts or {},
        )
        with self._lock:
            self._window_stats.append(w_stats)
            self._total_events += w_stats.num_events
            self._total_nodes  += w_stats.num_nodes
            self._total_edges  += w_stats.num_edges
        return w_stats

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @property
    def total_windows(self) -> int:
        with self._lock:
            return len(self._window_stats)

    @property
    def total_events(self) -> int:
        with self._lock:
            return self._total_events

    @property
    def total_nodes(self) -> int:
        with self._lock:
            return self._total_nodes

    @property
    def total_edges(self) -> int:
        with self._lock:
            return self._total_edges

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self._start_time

    def summary(self) -> dict[str, object]:
        """Return a flat metrics dict suitable for structlog / Prometheus."""
        with self._lock:
            windows = len(self._window_stats)
            avg_events = self._total_events / max(windows, 1)
            avg_nodes  = self._total_nodes  / max(windows, 1)
            avg_edges  = self._total_edges  / max(windows, 1)
        return {
            "total_windows":    windows,
            "total_events":     self._total_events,
            "total_nodes":      self._total_nodes,
            "total_edges":      self._total_edges,
            "elapsed_s":        round(self.elapsed_s, 2),
            "avg_events_per_window": round(avg_events, 1),
            "avg_nodes_per_window":  round(avg_nodes,  1),
            "avg_edges_per_window":  round(avg_edges,  1),
        }

    def last_window_stats(self) -> WindowStats | None:
        with self._lock:
            return self._window_stats[-1] if self._window_stats else None

    def reset(self) -> None:
        with self._lock:
            self._window_stats.clear()
            self._total_events = 0
            self._total_nodes  = 0
            self._total_edges  = 0
            self._start_time   = time.monotonic()
