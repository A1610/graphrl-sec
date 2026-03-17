"""Unit tests for feature engineering functions."""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.graph.feature_engineering import (
    NodeStats,
    _string_entropy,
    extract_domain_features,
    extract_edge_features,
    extract_host_features,
    extract_service_features,
)
from src.graph.node_registry import Node, NodeType
from src.ingestion.schemas import Protocol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(ntype: NodeType = NodeType.HOST) -> Node:
    return Node(node_id=0, node_type=ntype, entity_key="10.0.0.1")


def _make_event(
    *,
    bytes_sent: int = 1000,
    bytes_recv: int = 2000,
    packets_sent: int = 10,
    packets_recv: int = 20,
    duration_ms: float = 100.0,
    protocol: Protocol = Protocol.TCP,
    dst_port: int = 80,
    ts: float = 1_700_000_100.0,
    is_attack: bool = False,
) -> MagicMock:
    event = MagicMock()
    event.timestamp.timestamp.return_value = ts
    event.network.bytes_sent      = bytes_sent
    event.network.bytes_received  = bytes_recv
    event.network.packets_sent    = packets_sent
    event.network.packets_received = packets_recv
    event.network.duration_ms     = duration_ms
    event.network.protocol        = protocol
    event.destination.port        = dst_port
    event.metadata.is_attack      = is_attack
    return event


WIN_START = 1_700_000_000.0
WIN_END   = 1_700_003_600.0   # 1 hour window


# ---------------------------------------------------------------------------
# NodeStats
# ---------------------------------------------------------------------------


class TestNodeStats:
    def test_initial_values(self) -> None:
        s = NodeStats()
        assert s.degree == 0
        assert s.bytes_sent == 0
        assert s.attack_count == 0
        assert len(s.unique_dsts) == 0

    def test_update_increments_degree(self) -> None:
        s = NodeStats()
        s.update(_make_event(), dst_node_id=1)
        assert s.degree == 1

    def test_update_accumulates_bytes(self) -> None:
        s = NodeStats()
        s.update(_make_event(bytes_sent=100, bytes_recv=200), dst_node_id=1)
        s.update(_make_event(bytes_sent=50,  bytes_recv=100), dst_node_id=2)
        assert s.bytes_sent == 150
        assert s.bytes_recv == 300

    def test_update_tracks_unique_dsts(self) -> None:
        s = NodeStats()
        s.update(_make_event(), dst_node_id=1)
        s.update(_make_event(), dst_node_id=1)
        s.update(_make_event(), dst_node_id=2)
        assert len(s.unique_dsts) == 2

    def test_update_increments_attack_count(self) -> None:
        s = NodeStats()
        s.update(_make_event(is_attack=True), dst_node_id=1)
        s.update(_make_event(is_attack=False), dst_node_id=2)
        assert s.attack_count == 1

    def test_last_seen_ts_is_max(self) -> None:
        s = NodeStats()
        s.update(_make_event(ts=1000.0), dst_node_id=1)
        s.update(_make_event(ts=2000.0), dst_node_id=2)
        s.update(_make_event(ts=1500.0), dst_node_id=3)
        assert s.last_seen_ts == 2000.0


# ---------------------------------------------------------------------------
# extract_host_features
# ---------------------------------------------------------------------------


class TestExtractHostFeatures:
    def test_output_shape_and_dtype(self) -> None:
        node = _make_node()
        feats = extract_host_features(node, None, WIN_START, WIN_END, True)
        assert feats.shape == (8,)
        assert feats.dtype == np.float32

    def test_all_zeros_no_stats(self) -> None:
        node = _make_node()
        feats = extract_host_features(node, None, WIN_START, WIN_END, True)
        # degree=0, bytes=0 → first 5 dims are 0
        assert feats[0] == pytest.approx(0.0)
        assert feats[1] == pytest.approx(0.0)
        assert feats[5] == pytest.approx(1.0)   # is_internal=True

    def test_is_internal_flag(self) -> None:
        node = _make_node()
        internal = extract_host_features(node, None, WIN_START, WIN_END, True)
        external = extract_host_features(node, None, WIN_START, WIN_END, False)
        assert internal[5] == pytest.approx(1.0)
        assert external[5] == pytest.approx(0.0)

    def test_values_capped_at_one(self) -> None:
        s = NodeStats()
        s.degree     = 100_000
        s.bytes_sent = 100_000_000
        node = _make_node()
        feats = extract_host_features(node, s, WIN_START, WIN_END, True)
        assert all(0.0 <= v <= 1.0 for v in feats)

    def test_attack_score(self) -> None:
        s = NodeStats()
        s.event_count  = 4
        s.attack_count = 2
        node = _make_node()
        feats = extract_host_features(node, s, WIN_START, WIN_END, True)
        assert feats[6] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# extract_service_features
# ---------------------------------------------------------------------------


class TestExtractServiceFeatures:
    def test_output_shape_and_dtype(self) -> None:
        feats = extract_service_features(80, "TCP")
        assert feats.shape == (4,)
        assert feats.dtype == np.float32

    def test_well_known_port(self) -> None:
        feats = extract_service_features(80, "TCP")
        assert feats[1] == pytest.approx(1.0)  # is_well_known (port <= 1023)
        assert feats[2] == pytest.approx(1.0)  # is_registered (port <= 49151)

    def test_registered_port(self) -> None:
        # Port 8080 is in IANA registered range (1024–49151) — not well-known, but registered
        feats = extract_service_features(8080, "TCP")
        assert feats[1] == pytest.approx(0.0)  # not well-known
        assert feats[2] == pytest.approx(1.0)  # is registered

    def test_ephemeral_port(self) -> None:
        # Port 54321 > 49151 — ephemeral / dynamic range
        feats = extract_service_features(54321, "TCP")
        assert feats[1] == pytest.approx(0.0)  # not well-known
        assert feats[2] == pytest.approx(0.0)  # not registered (ephemeral)

    def test_protocol_encoding(self) -> None:
        assert extract_service_features(80, "TCP")[3]  == pytest.approx(0.0)
        assert extract_service_features(53, "UDP")[3]  == pytest.approx(0.5)
        assert extract_service_features(0,  "ICMP")[3] == pytest.approx(1.0)
        assert extract_service_features(0,  "xyz")[3]  == pytest.approx(0.75)

    def test_port_norm(self) -> None:
        feats = extract_service_features(65535, "TCP")
        assert feats[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# extract_domain_features
# ---------------------------------------------------------------------------


class TestExtractDomainFeatures:
    def test_empty_domain_returns_zeros(self) -> None:
        feats = extract_domain_features("")
        assert np.all(feats == 0.0)

    def test_output_shape_and_dtype(self) -> None:
        feats = extract_domain_features("example.com")
        assert feats.shape == (4,)
        assert feats.dtype == np.float32

    def test_label_count(self) -> None:
        feats = extract_domain_features("a.b.c.d")
        assert feats[0] == pytest.approx(4 / 10.0)

    def test_digit_ratio(self) -> None:
        feats = extract_domain_features("abc123")
        assert feats[1] == pytest.approx(3 / 6)

    def test_entropy_nonzero(self) -> None:
        feats = extract_domain_features("example.com")
        assert feats[3] > 0.0

    def test_all_values_in_range(self) -> None:
        feats = extract_domain_features("very.long.subdomain.example.com.au")
        assert all(0.0 <= v <= 1.0 for v in feats)


# ---------------------------------------------------------------------------
# extract_edge_features
# ---------------------------------------------------------------------------


class TestExtractEdgeFeatures:
    def test_output_shape_and_dtype(self) -> None:
        event = _make_event(ts=WIN_START + 100)
        feats = extract_edge_features(event, WIN_START, WIN_END)
        assert feats.shape == (12,)
        assert feats.dtype == np.float32

    def test_timestamp_norm_bounds(self) -> None:
        # At window start
        e_start = _make_event(ts=WIN_START)
        assert extract_edge_features(e_start, WIN_START, WIN_END)[0] == pytest.approx(0.0)
        # At window end
        e_end = _make_event(ts=WIN_END)
        assert extract_edge_features(e_end, WIN_START, WIN_END)[0] == pytest.approx(1.0)

    def test_tcp_one_hot(self) -> None:
        feats = extract_edge_features(_make_event(protocol=Protocol.TCP), WIN_START, WIN_END)
        assert feats[6] == pytest.approx(1.0)
        assert feats[7] == pytest.approx(0.0)
        assert feats[8] == pytest.approx(0.0)
        assert feats[9] == pytest.approx(0.0)

    def test_udp_one_hot(self) -> None:
        feats = extract_edge_features(_make_event(protocol=Protocol.UDP), WIN_START, WIN_END)
        assert feats[6] == pytest.approx(0.0)
        assert feats[7] == pytest.approx(1.0)

    def test_icmp_one_hot(self) -> None:
        feats = extract_edge_features(_make_event(protocol=Protocol.ICMP), WIN_START, WIN_END)
        assert feats[8] == pytest.approx(1.0)

    def test_is_attack_flag(self) -> None:
        atk   = extract_edge_features(_make_event(is_attack=True),  WIN_START, WIN_END)
        benign = extract_edge_features(_make_event(is_attack=False), WIN_START, WIN_END)
        assert atk[11]   == pytest.approx(1.0)
        assert benign[11] == pytest.approx(0.0)

    def test_all_values_in_range(self) -> None:
        feats = extract_edge_features(
            _make_event(bytes_sent=5_000_000, packets_sent=50_000), WIN_START, WIN_END
        )
        assert all(0.0 <= v <= 1.0 for v in feats)


# ---------------------------------------------------------------------------
# _string_entropy
# ---------------------------------------------------------------------------


class TestStringEntropy:
    def test_empty_string(self) -> None:
        assert _string_entropy("") == 0.0

    def test_uniform_string(self) -> None:
        assert _string_entropy("aaaa") == pytest.approx(0.0)

    def test_two_equal_chars(self) -> None:
        assert _string_entropy("ab") == pytest.approx(1.0)

    def test_entropy_increases_with_diversity(self) -> None:
        low  = _string_entropy("aaab")
        high = _string_entropy("abcd")
        assert high > low
