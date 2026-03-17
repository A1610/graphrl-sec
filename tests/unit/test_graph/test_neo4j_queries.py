"""Unit tests for Neo4jQueryService.

All Neo4j interactions are mocked — no live database required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.graph.neo4j_queries import (
    CommunicatorResult,
    EdgeResult,
    GraphStats,
    NeighborhoodResult,
    Neo4jQueryService,
    NodeResult,
    TimeWindowResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(records: list[dict]) -> MagicMock:
    """Build a Neo4jQueryService with a mocked driver that returns `records`."""
    mock_driver  = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__  = MagicMock(return_value=False)

    # session.run(cypher, **params) returns an iterable of record-like objects
    mock_session.run.return_value = [_make_record(r) for r in records]

    with patch("src.graph.neo4j_queries.GraphDatabase.driver", return_value=mock_driver):
        svc = Neo4jQueryService()
    svc._driver = mock_driver
    return svc


def _make_record(data: dict) -> MagicMock:
    """Create a neo4j-record-like object for a given dict."""
    record = MagicMock()
    record.__getitem__ = lambda self, k: data[k]
    record.get         = lambda k, default=None: data.get(k, default)
    return record


# ---------------------------------------------------------------------------
# Result dataclass tests
# ---------------------------------------------------------------------------


class TestResultDataclasses:
    def test_node_result_frozen(self) -> None:
        nr = NodeResult(entity_key="10.0.0.1", node_label="Host")
        with pytest.raises(AttributeError):
            nr.entity_key = "changed"  # type: ignore[misc]

    def test_edge_result_frozen(self) -> None:
        er = EdgeResult(src_key="a", dst_key="b", rel_type="CONNECTS_TO")
        with pytest.raises(AttributeError):
            er.src_key = "x"  # type: ignore[misc]

    def test_graph_stats_total_nodes(self) -> None:
        s = GraphStats(
            host_count=10, external_ip_count=5, service_count=3,
            domain_count=2, user_count=1,
            connects_to_count=100, uses_service_count=50,
            resolves_domain_count=20, authenticated_as_count=5,
        )
        assert s.total_nodes == 21
        assert s.total_edges == 175

    def test_time_window_result_edge_count(self) -> None:
        edges = (EdgeResult("a", "b", "CONNECTS_TO"), EdgeResult("c", "d", "CONNECTS_TO"))
        r = TimeWindowResult(start_ts=0.0, end_ts=3600.0, edges=edges)
        assert r.edge_count == 2

    def test_neighborhood_result_frozen(self) -> None:
        r = NeighborhoodResult(center_ip="1.2.3.4", hops=2, nodes=(), edges=())
        with pytest.raises(AttributeError):
            r.hops = 3  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Neo4jQueryService.ping
# ---------------------------------------------------------------------------


class TestPing:
    def test_ping_true_when_reachable(self) -> None:
        svc = _make_service([])
        assert svc.ping() is True

    def test_ping_false_when_unreachable(self) -> None:
        mock_driver = MagicMock()
        from neo4j.exceptions import ServiceUnavailable
        mock_driver.session.side_effect = ServiceUnavailable("down")
        with patch("src.graph.neo4j_queries.GraphDatabase.driver", return_value=mock_driver):
            svc = Neo4jQueryService()
        svc._driver = mock_driver
        assert svc.ping() is False


# ---------------------------------------------------------------------------
# get_neighborhood
# ---------------------------------------------------------------------------


class TestGetNeighborhood:
    def _make_neighborhood_record(
        self,
        entity_key: str,
        label: str = "Host",
        edges: list | None = None,
    ) -> dict:
        return {
            "entity_key": entity_key,
            "node_label": label,
            "props":      {"ip": entity_key},
            "edges":      edges or [],
        }

    def test_returns_neighborhood_result(self) -> None:
        svc = _make_service([self._make_neighborhood_record("10.0.0.1")])
        result = svc.get_neighborhood("10.0.0.1")
        assert isinstance(result, NeighborhoodResult)

    def test_center_ip_set(self) -> None:
        svc = _make_service([self._make_neighborhood_record("10.0.0.1")])
        result = svc.get_neighborhood("10.0.0.1")
        assert result.center_ip == "10.0.0.1"

    def test_hops_clamped_to_max_4(self) -> None:
        svc = _make_service([])
        result = svc.get_neighborhood("10.0.0.1", hops=10)
        assert result.hops == 4

    def test_hops_clamped_to_min_1(self) -> None:
        svc = _make_service([])
        result = svc.get_neighborhood("10.0.0.1", hops=0)
        assert result.hops == 1

    def test_nodes_deduplicated(self) -> None:
        # Same entity_key returned twice in records — should be deduplicated
        records = [
            self._make_neighborhood_record("10.0.0.1"),
            self._make_neighborhood_record("10.0.0.1"),
        ]
        svc = _make_service(records)
        result = svc.get_neighborhood("10.0.0.1")
        assert len(result.nodes) == 1

    def test_edges_collected_from_path(self) -> None:
        edge_data = [{"src": "10.0.0.1", "dst": "10.0.0.2", "type": "CONNECTS_TO", "props": {}}]
        svc = _make_service([self._make_neighborhood_record("10.0.0.1", edges=edge_data)])
        result = svc.get_neighborhood("10.0.0.1")
        assert len(result.edges) == 1
        assert result.edges[0].rel_type == "CONNECTS_TO"

    def test_empty_database_returns_empty_result(self) -> None:
        svc = _make_service([])
        result = svc.get_neighborhood("99.99.99.99")
        assert result.nodes == ()
        assert result.edges == ()


# ---------------------------------------------------------------------------
# get_time_window_edges
# ---------------------------------------------------------------------------


class TestGetTimeWindowEdges:
    def _make_edge_record(self, src: str = "a", dst: str = "b") -> dict:
        return {"src_key": src, "dst_key": dst, "rel_type": "CONNECTS_TO", "props": {}}

    def test_returns_time_window_result(self) -> None:
        svc = _make_service([self._make_edge_record()])
        result = svc.get_time_window_edges(0, 10)
        assert isinstance(result, TimeWindowResult)

    def test_edges_correctly_mapped(self) -> None:
        svc = _make_service([self._make_edge_record("10.0.0.1", "10.0.0.2")])
        result = svc.get_time_window_edges(0, 10)
        assert result.edges[0].src_key == "10.0.0.1"
        assert result.edges[0].dst_key == "10.0.0.2"

    def test_empty_result_on_no_matches(self) -> None:
        svc = _make_service([])
        result = svc.get_time_window_edges(9999, 99999)
        assert result.edge_count == 0

    def test_start_end_ts_set(self) -> None:
        svc = _make_service([])
        result = svc.get_time_window_edges(100, 200)
        assert result.start_ts == pytest.approx(100.0)
        assert result.end_ts   == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# get_top_communicators
# ---------------------------------------------------------------------------


class TestGetTopCommunicators:
    def _make_comm_record(
        self,
        entity_key: str = "10.0.0.1",
        label: str = "Host",
        outbound: int = 50,
        unique: int = 10,
    ) -> dict:
        return {
            "entity_key":          entity_key,
            "node_label":          label,
            "outbound_count":      outbound,
            "unique_destinations": unique,
        }

    def test_returns_list(self) -> None:
        svc = _make_service([self._make_comm_record()])
        result = svc.get_top_communicators()
        assert isinstance(result, list)

    def test_communicator_result_type(self) -> None:
        svc = _make_service([self._make_comm_record()])
        result = svc.get_top_communicators()
        assert isinstance(result[0], CommunicatorResult)

    def test_counts_mapped_correctly(self) -> None:
        svc = _make_service([self._make_comm_record(outbound=42, unique=7)])
        result = svc.get_top_communicators()
        assert result[0].outbound_count == 42
        assert result[0].unique_destinations == 7

    def test_empty_returns_empty_list(self) -> None:
        svc = _make_service([])
        assert svc.get_top_communicators() == []


# ---------------------------------------------------------------------------
# get_anomalous_paths
# ---------------------------------------------------------------------------


class TestGetAnomalousPaths:
    def _make_anon_record(self) -> dict:
        return {
            "src_key":  "10.0.0.1",
            "dst_key":  "8.8.8.8",
            "rel_type": "CONNECTS_TO",
            "props":    {"window_id": 1},
        }

    def test_returns_list_of_edge_results(self) -> None:
        svc = _make_service([self._make_anon_record()])
        result = svc.get_anomalous_paths(score_threshold=0.5)
        assert isinstance(result, list)
        assert isinstance(result[0], EdgeResult)

    def test_empty_on_no_anomalies(self) -> None:
        svc = _make_service([])
        assert svc.get_anomalous_paths() == []


# ---------------------------------------------------------------------------
# get_graph_stats
# ---------------------------------------------------------------------------


class TestGetGraphStats:
    def _make_stats_records(self) -> list[dict]:
        categories = [
            "host", "external_ip", "service", "domain", "user",
            "connects_to", "uses_service", "resolves_domain", "authenticated_as",
        ]
        return [{"category": c, "count": 10} for c in categories]

    def test_returns_graph_stats(self) -> None:
        svc = _make_service(self._make_stats_records())
        result = svc.get_graph_stats()
        assert isinstance(result, GraphStats)

    def test_all_counts_populated(self) -> None:
        svc = _make_service(self._make_stats_records())
        result = svc.get_graph_stats()
        assert result.host_count == 10
        assert result.external_ip_count == 10
        assert result.connects_to_count == 10

    def test_total_nodes_sum(self) -> None:
        svc = _make_service(self._make_stats_records())
        result = svc.get_graph_stats()
        assert result.total_nodes == 50   # 5 types × 10

    def test_total_edges_sum(self) -> None:
        svc = _make_service(self._make_stats_records())
        result = svc.get_graph_stats()
        assert result.total_edges == 40   # 4 edge types × 10

    def test_empty_database_returns_zeros(self) -> None:
        svc = _make_service([])
        result = svc.get_graph_stats()
        assert result.total_nodes == 0
        assert result.total_edges == 0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_context_manager_closes_driver(self) -> None:
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_driver.session.return_value.__exit__  = MagicMock(return_value=False)
        with patch("src.graph.neo4j_queries.GraphDatabase.driver", return_value=mock_driver), Neo4jQueryService():
            pass
        mock_driver.close.assert_called_once()
