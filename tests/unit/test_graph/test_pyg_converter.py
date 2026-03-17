"""Unit tests for PyGConverter."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import torch
from torch_geometric.data import HeteroData

from src.graph.config import GraphConfig
from src.graph.edge_constructor import EdgeConstructor
from src.graph.node_registry import NodeRegistry
from src.graph.pyg_converter import ConversionStats, PyGConverter
from src.graph.temporal import TimeWindow, WindowResult
from src.ingestion.schemas import Protocol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WIN_START = 1_700_000_000.0
WIN_END   = 1_700_003_600.0


def _make_event(
    src_ip: str = "10.0.0.1",
    dst_ip: str = "10.0.0.2",
    dst_port: int = 80,
    ts: float = WIN_START + 100,
    is_attack: bool = False,
) -> MagicMock:
    event = MagicMock()
    event.source.ip  = src_ip
    event.destination.ip       = dst_ip
    event.destination.port     = dst_port
    event.destination.hostname = None   # explicit None — MagicMock attrs are truthy
    event.metadata.is_attack   = is_attack
    event.network.protocol   = Protocol.TCP
    event.network.bytes_sent = 100
    event.network.bytes_received = 200
    event.network.packets_sent   = 1
    event.network.packets_received = 2
    event.network.duration_ms = 10.0
    event.timestamp.timestamp.return_value = ts
    return event


def _build_result(events: list[MagicMock]) -> WindowResult:
    cfg      = GraphConfig()
    reg      = NodeRegistry(cfg)
    ctor     = EdgeConstructor(reg, cfg)
    acc      = ctor.process_batch(events, WIN_START, WIN_END)
    window   = TimeWindow(window_id=0, start_ts=WIN_START, end_ts=WIN_END, num_events=len(events))
    return WindowResult(window=window, accumulator=acc, registry=reg)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPyGConverter:
    def test_returns_hetero_data(self) -> None:
        result = _build_result([_make_event()])
        data, _ = PyGConverter().convert(result)
        assert isinstance(data, HeteroData)

    def test_returns_conversion_stats(self) -> None:
        result = _build_result([_make_event()])
        _, stats = PyGConverter().convert(result)
        assert isinstance(stats, ConversionStats)

    def test_host_node_features_present(self) -> None:
        result = _build_result([_make_event()])
        data, _ = PyGConverter().convert(result)
        assert hasattr(data["host"], "x")
        assert data["host"].x.dtype == torch.float32

    def test_host_feature_dim(self) -> None:
        result = _build_result([_make_event()])
        data, _ = PyGConverter().convert(result)
        assert data["host"].x.shape[1] == 8

    def test_service_node_features_present(self) -> None:
        result = _build_result([_make_event(dst_port=443)])
        data, _ = PyGConverter().convert(result)
        assert hasattr(data["service"], "x")
        assert data["service"].x.shape[1] == 4

    def test_connects_to_edge_present(self) -> None:
        result = _build_result([_make_event()])
        data, _ = PyGConverter().convert(result)
        # host -> host OR external_ip -> host, etc.
        edge_types = [str(et) for et in data.edge_types]
        assert any("connects_to" in et for et in edge_types)

    def test_edge_index_shape(self) -> None:
        result = _build_result([_make_event()])
        data, _ = PyGConverter().convert(result)
        for et in data.edge_types:
            edge_index = data[et].edge_index
            assert edge_index.shape[0] == 2
            assert edge_index.dtype == torch.long

    def test_edge_attr_dim(self) -> None:
        result = _build_result([_make_event()])
        data, _ = PyGConverter().convert(result)
        for et in data.edge_types:
            edge_attr = data[et].edge_attr
            assert edge_attr.shape[1] == 12
            assert edge_attr.dtype == torch.float32

    def test_window_metadata_attached(self) -> None:
        result = _build_result([_make_event()])
        data, _ = PyGConverter().convert(result)
        assert data["window_id"] == 0
        assert data["start_ts"] == pytest.approx(WIN_START)
        assert data["end_ts"] == pytest.approx(WIN_END)

    def test_stats_node_count(self) -> None:
        events = [_make_event(src_ip="10.0.0.1"), _make_event(src_ip="10.0.0.2")]
        result = _build_result(events)
        _, stats = PyGConverter().convert(result)
        assert stats.num_nodes >= 2

    def test_stats_edge_count(self) -> None:
        result = _build_result([_make_event()])
        _, stats = PyGConverter().convert(result)
        assert stats.num_edges >= 1

    def test_empty_window_produces_valid_data(self) -> None:
        result = _build_result([])
        data, stats = PyGConverter().convert(result)
        assert isinstance(data, HeteroData)
        assert stats.num_nodes == 0
        assert stats.num_edges == 0

    def test_external_ip_node_features(self) -> None:
        result = _build_result([_make_event(src_ip="8.8.8.8")])
        data, _ = PyGConverter().convert(result)
        assert hasattr(data["external_ip"], "x")
        assert data["external_ip"].x.shape[1] == 8

    def test_node_feature_values_in_range(self) -> None:
        result = _build_result([_make_event()])
        data, _ = PyGConverter().convert(result)
        for ntype in data.node_types:
            x = data[ntype].x
            assert (x >= 0.0).all(), f"{ntype}: features below 0"
            assert (x <= 1.0).all(), f"{ntype}: features above 1"
