"""Unit tests for EdgeConstructor."""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.graph.config import GraphConfig
from src.graph.edge_constructor import (
    Edge,
    EdgeAccumulator,
    EdgeConstructor,
    EdgeType,
)
from src.graph.node_registry import NodeRegistry, NodeType
from src.ingestion.schemas import Protocol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WIN_START = 1_700_000_000.0
WIN_END   = 1_700_003_600.0


def _make_event(
    *,
    src_ip: str = "10.0.0.1",
    dst_ip: str = "10.0.0.2",
    dst_port: int = 80,
    protocol: Protocol = Protocol.TCP,
    is_attack: bool = False,
    ts: float = WIN_START + 60,
    bytes_sent: int = 500,
    bytes_recv: int = 1000,
    packets_sent: int = 5,
    packets_recv: int = 10,
    duration_ms: float = 50.0,
    domain: str | None = None,
) -> MagicMock:
    event = MagicMock()
    event.source.ip           = src_ip
    event.destination.ip      = dst_ip
    event.destination.port    = dst_port
    event.network.protocol    = protocol
    event.network.bytes_sent  = bytes_sent
    event.network.bytes_received = bytes_recv
    event.network.packets_sent   = packets_sent
    event.network.packets_received = packets_recv
    event.network.duration_ms = duration_ms
    event.metadata.is_attack  = is_attack
    event.timestamp.timestamp.return_value = ts
    # Must be explicit None — MagicMock attributes are truthy by default
    event.destination.hostname = domain
    return event


@pytest.fixture()
def registry() -> NodeRegistry:
    return NodeRegistry()


@pytest.fixture()
def constructor(registry: NodeRegistry) -> EdgeConstructor:
    return EdgeConstructor(registry)


@pytest.fixture()
def accumulator() -> EdgeAccumulator:
    return EdgeAccumulator(window_start_ts=WIN_START, window_end_ts=WIN_END)


# ---------------------------------------------------------------------------
# Basic edge creation
# ---------------------------------------------------------------------------


class TestProcessEvent:
    def test_creates_connects_to_edge(
        self, constructor: EdgeConstructor, accumulator: EdgeAccumulator
    ) -> None:
        edges = constructor.process_event(_make_event(), accumulator)
        connect_edges = [e for e in edges if e.edge_type == EdgeType.CONNECTS_TO]
        assert len(connect_edges) == 1

    def test_creates_uses_service_edge(
        self, constructor: EdgeConstructor, accumulator: EdgeAccumulator
    ) -> None:
        edges = constructor.process_event(_make_event(dst_port=443), accumulator)
        svc_edges = [e for e in edges if e.edge_type == EdgeType.USES_SERVICE]
        assert len(svc_edges) == 1

    def test_no_service_edge_if_port_zero(
        self, constructor: EdgeConstructor, accumulator: EdgeAccumulator
    ) -> None:
        edges = constructor.process_event(_make_event(dst_port=0), accumulator)
        svc_edges = [e for e in edges if e.edge_type == EdgeType.USES_SERVICE]
        assert len(svc_edges) == 0

    def test_creates_domain_edge(
        self, constructor: EdgeConstructor, accumulator: EdgeAccumulator
    ) -> None:
        edges = constructor.process_event(_make_event(domain="example.com"), accumulator)
        dom_edges = [e for e in edges if e.edge_type == EdgeType.RESOLVES_DOMAIN]
        assert len(dom_edges) == 1

    def test_no_user_edge_for_current_schemas(
        self, constructor: EdgeConstructor, accumulator: EdgeAccumulator
    ) -> None:
        # AUTHENTICATED_AS is Phase 3 (LANL dataset only).
        # UnifiedEvent has no username field — edge must never appear.
        edges = constructor.process_event(_make_event(), accumulator)
        usr_edges = [e for e in edges if e.edge_type == EdgeType.AUTHENTICATED_AS]
        assert len(usr_edges) == 0

    def test_edge_features_are_float32_12dim(
        self, constructor: EdgeConstructor, accumulator: EdgeAccumulator
    ) -> None:
        edges = constructor.process_event(_make_event(), accumulator)
        for edge in edges:
            assert edge.features.shape == (12,)
            assert edge.features.dtype == np.float32

    def test_accumulator_records_edges(
        self, constructor: EdgeConstructor, accumulator: EdgeAccumulator
    ) -> None:
        constructor.process_event(_make_event(), accumulator)
        assert accumulator.num_edges > 0

    def test_src_stats_updated(
        self, constructor: EdgeConstructor, accumulator: EdgeAccumulator
    ) -> None:
        constructor.process_event(_make_event(), accumulator)
        registry: NodeRegistry = constructor._registry
        src_node = registry.get_by_key(NodeType.HOST, "10.0.0.1")
        assert src_node is not None
        stats = accumulator.get_stats(src_node.node_id)
        assert stats is not None
        assert stats.degree == 1


# ---------------------------------------------------------------------------
# Degree cap
# ---------------------------------------------------------------------------


class TestDegreeCap:
    def test_degree_cap_blocks_further_edges(self) -> None:
        cfg = GraphConfig(max_node_degree=10)
        reg = NodeRegistry(cfg)
        ctor = EdgeConstructor(reg, cfg)
        acc  = EdgeAccumulator(window_start_ts=WIN_START, window_end_ts=WIN_END)

        # Fill up to the cap
        for i in range(10):
            ctor.process_event(_make_event(dst_ip=f"10.0.1.{i}"), acc)
        # Next event from same src should be blocked
        result = ctor.process_event(_make_event(dst_ip="10.0.1.100"), acc)
        assert result == []


# ---------------------------------------------------------------------------
# process_batch
# ---------------------------------------------------------------------------


class TestProcessBatch:
    def test_batch_returns_accumulator(self) -> None:
        reg  = NodeRegistry()
        ctor = EdgeConstructor(reg)
        events = [_make_event(dst_ip=f"10.0.0.{i}") for i in range(5)]
        acc = ctor.process_batch(events, WIN_START, WIN_END)
        assert isinstance(acc, EdgeAccumulator)
        assert acc.num_edges > 0

    def test_batch_empty_events(self) -> None:
        reg  = NodeRegistry()
        ctor = EdgeConstructor(reg)
        acc  = ctor.process_batch([], WIN_START, WIN_END)
        assert acc.num_edges == 0

    def test_batch_accumulates_stats(self) -> None:
        reg  = NodeRegistry()
        ctor = EdgeConstructor(reg)
        events = [_make_event() for _ in range(3)]
        acc = ctor.process_batch(events, WIN_START, WIN_END)
        src_node = reg.get_by_key(NodeType.HOST, "10.0.0.1")
        assert src_node is not None
        stats = acc.get_stats(src_node.node_id)
        assert stats is not None
        assert stats.degree == 3


# ---------------------------------------------------------------------------
# EdgeAccumulator
# ---------------------------------------------------------------------------


class TestEdgeAccumulator:
    def test_add_edge_increments_count(self) -> None:
        acc = EdgeAccumulator(window_start_ts=WIN_START, window_end_ts=WIN_END)
        n1 = MagicMock()
        n2 = MagicMock()
        edge = Edge(n1, EdgeType.CONNECTS_TO, n2, np.zeros(12, dtype=np.float32))
        acc.add_edge(edge)
        assert acc.num_edges == 1

    def test_get_stats_none_if_no_updates(self) -> None:
        acc = EdgeAccumulator(window_start_ts=WIN_START, window_end_ts=WIN_END)
        assert acc.get_stats(999) is None
