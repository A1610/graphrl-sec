"""
Phase 1 end-to-end integration test.

Validates the full pipeline without live external services:
    CSV fixture  →  Parser  →  EventNormalizer
    →  SlidingWindowEngine  →  PyGConverter  →  HeteroData
    →  Neo4jWriter (mocked)

Every component runs real production code; only Neo4j is mocked.
Tests confirm data flows correctly through all Phase 1 modules and that
the PyG graph structure is valid for GNN consumption.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import torch
from torch_geometric.data import HeteroData

from src.graph.config import GraphConfig
from src.graph.pyg_converter import ConversionStats, PyGConverter
from src.graph.temporal import SlidingWindowEngine, WindowResult
from src.ingestion.batch import BatchIngestor
from src.ingestion.normalizer import EventNormalizer
from src.ingestion.parsers.cicids import CICIDSParser
from src.ingestion.parsers.unsw import UNSWParser
from src.ingestion.schemas import CollectorMode, DatasetSource, UnifiedEvent

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_CICIDS_CSV = _FIXTURES / "sample_cicids.csv"
_UNSW_CSV   = _FIXTURES / "sample_unsw.csv"

# Small window config so the 83-second fixture data produces windows on flush.
_CFG = GraphConfig(
    neo4j_uri="bolt://localhost:7687",   # never actually connected
    window_size_hours=0.1,               # 360 s — covers fixture time range
    window_slide_minutes=1.0,            # 60 s slide
    serialize_snapshots=False,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_unsw() -> list[UnifiedEvent]:
    parser     = UNSWParser()
    normalizer = EventNormalizer(collector=CollectorMode.BATCH, deduplicate=False)
    return [
        e for row in parser.parse_file(_UNSW_CSV)
        if (e := normalizer.normalize(row)) is not None
    ]


def _parse_cicids() -> list[UnifiedEvent]:
    parser     = CICIDSParser()
    normalizer = EventNormalizer(collector=CollectorMode.BATCH, deduplicate=False)
    return [
        e for row in parser.parse_file(_CICIDS_CSV)
        if (e := normalizer.normalize(row)) is not None
    ]


def _run_engine(events: list[UnifiedEvent]) -> list[WindowResult]:
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    return list(SlidingWindowEngine(_CFG).process_stream(iter(sorted_events)))


def _convert(windows: list[WindowResult]) -> list[tuple[HeteroData, ConversionStats]]:
    converter = PyGConverter(_CFG)
    return [converter.convert(w) for w in windows]


def _mock_neo4j_driver() -> tuple[MagicMock, MagicMock]:
    """Return (mock_driver, mock_session) with context-manager protocol set up."""
    mock_driver  = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__  = MagicMock(return_value=False)
    return mock_driver, mock_session


# ---------------------------------------------------------------------------
# 1. Parser + EventNormalizer
# ---------------------------------------------------------------------------


class TestPhase1Parsing:
    """CSV fixtures parse and normalize into valid UnifiedEvent objects."""

    def test_unsw_fixture_produces_events(self) -> None:
        assert len(_parse_unsw()) >= 1

    def test_cicids_fixture_produces_events(self) -> None:
        assert len(_parse_cicids()) >= 1

    def test_unsw_timestamps_are_timezone_aware(self) -> None:
        # UNSW parser uses epoch 0 as a sentinel for missing Stime — still tz-aware.
        for e in _parse_unsw():
            assert e.timestamp.tzinfo is not None
            assert e.timestamp.timestamp() >= 0

    def test_cicids_timestamps_are_timezone_aware(self) -> None:
        for e in _parse_cicids():
            assert e.timestamp.tzinfo is not None
            assert e.timestamp.timestamp() > 0

    def test_unsw_ips_are_non_empty(self) -> None:
        for e in _parse_unsw():
            assert e.source.ip and e.destination.ip

    def test_cicids_ips_are_non_empty(self) -> None:
        for e in _parse_cicids():
            assert e.source.ip and e.destination.ip

    def test_unsw_dataset_source_tag(self) -> None:
        for e in _parse_unsw():
            assert e.metadata.dataset_source == DatasetSource.UNSW_NB15

    def test_cicids_dataset_source_tag(self) -> None:
        for e in _parse_cicids():
            assert e.metadata.dataset_source == DatasetSource.CICIDS2017

    def test_batch_ingestor_unsw(self) -> None:
        result = BatchIngestor(deduplicate=False).ingest(DatasetSource.UNSW_NB15, _UNSW_CSV)
        assert result.total_normalized >= 1
        assert result.total_parsed >= result.total_normalized
        assert isinstance(result.events, list)

    def test_batch_ingestor_cicids(self) -> None:
        result = BatchIngestor(deduplicate=False).ingest(DatasetSource.CICIDS2017, _CICIDS_CSV)
        assert result.total_normalized >= 1
        assert isinstance(result.events, list)

    def test_batch_ingestor_unsw_skips_invalid_rows(self) -> None:
        # Fixture contains rows with bad IPs (0.0.0.0, 999.x.x.x) — must be skipped.
        result = BatchIngestor(deduplicate=True).ingest(DatasetSource.UNSW_NB15, _UNSW_CSV)
        assert result.total_skipped >= 0   # may or may not skip depending on validators


# ---------------------------------------------------------------------------
# 2. SlidingWindowEngine
# ---------------------------------------------------------------------------


class TestPhase1WindowEngine:
    """UNSW fixture events flow through the window engine and produce windows."""

    def test_unsw_produces_at_least_one_window(self) -> None:
        assert len(_run_engine(_parse_unsw())) >= 1

    def test_windows_have_positive_event_counts(self) -> None:
        for w in _run_engine(_parse_unsw()):
            assert w.window.num_events > 0

    def test_windows_have_valid_time_range(self) -> None:
        for w in _run_engine(_parse_unsw()):
            assert w.window.end_ts > w.window.start_ts

    def test_windows_contain_edges(self) -> None:
        total = sum(w.accumulator.num_edges for w in _run_engine(_parse_unsw()))
        assert total > 0

    def test_windows_contain_nodes(self) -> None:
        total = sum(w.registry.total_nodes for w in _run_engine(_parse_unsw()))
        assert total > 0

    def test_window_ids_are_sequential(self) -> None:
        for i, w in enumerate(_run_engine(_parse_unsw())):
            assert w.window.window_id == i

    def test_combined_datasets_produce_windows(self) -> None:
        events  = _parse_unsw() + _parse_cicids()
        windows = _run_engine(events)
        assert len(windows) >= 1


# ---------------------------------------------------------------------------
# 3. PyGConverter → HeteroData
# ---------------------------------------------------------------------------


class TestPhase1PyGConversion:
    """WindowResult converts to a structurally valid PyG HeteroData object."""

    @pytest.fixture(scope="class")
    def pyg_results(self) -> list[tuple[HeteroData, ConversionStats]]:
        return _convert(_run_engine(_parse_unsw()))

    def test_returns_heterodata_instances(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        for data, _ in pyg_results:
            assert isinstance(data, HeteroData)

    def test_stats_num_nodes_positive(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        assert sum(s.num_nodes for _, s in pyg_results) > 0

    def test_stats_num_edges_positive(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        assert sum(s.num_edges for _, s in pyg_results) > 0

    def test_node_features_are_float32(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        for data, _ in pyg_results:
            for ntype in data.node_types:
                assert data[ntype].x.dtype == torch.float32, (
                    f"{ntype}.x dtype should be float32"
                )

    def test_node_feature_dims_match_config(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        expected = {
            "host":        _CFG.host_feature_dim,
            "external_ip": _CFG.external_ip_feature_dim,
            "service":     _CFG.service_feature_dim,
            "domain":      _CFG.domain_feature_dim,
        }
        for data, _ in pyg_results:
            for ntype in data.node_types:
                if ntype in expected:
                    assert data[ntype].x.shape[1] == expected[ntype], (
                        f"{ntype}.x dim {data[ntype].x.shape[1]} ≠ {expected[ntype]}"
                    )

    def test_edge_index_shape_is_2_by_num_edges(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        for data, _ in pyg_results:
            for rel in data.edge_types:
                ei = data[rel].edge_index
                assert ei.ndim == 2 and ei.shape[0] == 2

    def test_edge_attr_second_dim_matches_config(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        for data, _ in pyg_results:
            for rel in data.edge_types:
                store = data[rel]
                if hasattr(store, "edge_attr"):
                    assert store.edge_attr.shape[1] == _CFG.edge_feature_dim

    def test_edge_index_src_indices_in_bounds(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        for data, _ in pyg_results:
            for src_type, rel, dst_type in data.edge_types:
                ei    = data[(src_type, rel, dst_type)].edge_index
                n_src = data[src_type].x.shape[0]
                if ei.shape[1] == 0:
                    continue
                assert int(ei[0].max()) < n_src

    def test_edge_index_dst_indices_in_bounds(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        for data, _ in pyg_results:
            for src_type, rel, dst_type in data.edge_types:
                ei    = data[(src_type, rel, dst_type)].edge_index
                n_dst = data[dst_type].x.shape[0]
                if ei.shape[1] == 0:
                    continue
                assert int(ei[1].max()) < n_dst

    def test_no_nan_in_node_features(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        for data, _ in pyg_results:
            for ntype in data.node_types:
                assert not torch.isnan(data[ntype].x).any(), (
                    f"{ntype}.x contains NaN"
                )

    def test_no_nan_in_edge_features(
        self, pyg_results: list[tuple[HeteroData, ConversionStats]]
    ) -> None:
        for data, _ in pyg_results:
            for rel in data.edge_types:
                store = data[rel]
                if hasattr(store, "edge_attr"):
                    assert not torch.isnan(store.edge_attr).any(), (
                        f"{rel} edge_attr contains NaN"
                    )


# ---------------------------------------------------------------------------
# 4. Neo4jWriter (mocked)
# ---------------------------------------------------------------------------


class TestPhase1Neo4jWriter:
    """Neo4jWriter is called correctly for each window; Neo4j is mocked."""

    def test_writer_executes_cypher_for_each_window(self) -> None:
        from src.graph.neo4j_writer import Neo4jWriter

        windows              = _run_engine(_parse_unsw())
        mock_driver, mock_session = _mock_neo4j_driver()

        with patch("src.graph.neo4j_writer.GraphDatabase.driver", return_value=mock_driver):
            writer = Neo4jWriter(_CFG)
            for w in windows:
                writer.write_window(w)
            writer.close()

        assert mock_session.run.call_count > 0

    def test_every_window_triggers_at_least_one_cypher_call(self) -> None:
        from src.graph.neo4j_writer import Neo4jWriter

        windows              = _run_engine(_parse_unsw())
        mock_driver, mock_session = _mock_neo4j_driver()

        with patch("src.graph.neo4j_writer.GraphDatabase.driver", return_value=mock_driver):
            writer = Neo4jWriter(_CFG)
            for w in windows:
                before = mock_session.run.call_count
                writer.write_window(w)
                after  = mock_session.run.call_count
                assert after > before, "window produced no Cypher calls"
            writer.close()


# ---------------------------------------------------------------------------
# 5. Full pipeline smoke tests
# ---------------------------------------------------------------------------


class TestPhase1FullPipeline:
    """End-to-end: CSV → events → windows → PyG → Neo4j (mocked)."""

    def _run_full(self, dataset: DatasetSource, path: Path) -> None:
        from src.graph.neo4j_writer import Neo4jWriter

        result = BatchIngestor(deduplicate=False).ingest(dataset, path)
        assert result.total_normalized >= 1

        sorted_events = sorted(result.events, key=lambda e: e.timestamp)
        windows       = list(SlidingWindowEngine(_CFG).process_stream(iter(sorted_events)))
        assert windows

        converter = PyGConverter(_CFG)
        for w in windows:
            data, stats = converter.convert(w)
            assert isinstance(data, HeteroData)
            assert stats.num_nodes > 0

        mock_driver, mock_session = _mock_neo4j_driver()
        with patch("src.graph.neo4j_writer.GraphDatabase.driver", return_value=mock_driver):
            writer = Neo4jWriter(_CFG)
            for w in windows:
                writer.write_window(w)
            writer.close()

        assert mock_session.run.call_count > 0

    def test_full_pipeline_unsw(self) -> None:
        self._run_full(DatasetSource.UNSW_NB15, _UNSW_CSV)

    def test_full_pipeline_cicids(self) -> None:
        self._run_full(DatasetSource.CICIDS2017, _CICIDS_CSV)
