"""Unit tests for KafkaTopicManager.

All Kafka interactions are mocked — no live broker required.
"""

from __future__ import annotations

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.topics import (
    TOPIC_SPECS,
    TOPICS_BY_NAME,
    KafkaTopicManager,
    TopicEnsureResult,
    TopicInfo,
    TopicSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager() -> tuple[KafkaTopicManager, MagicMock]:
    """Return (KafkaTopicManager, mock_admin) pair."""
    mock_admin = MagicMock()
    # list_topics returns a metadata object whose .topics dict has names as keys
    mock_meta = MagicMock()
    mock_meta.topics = {}
    mock_admin.list_topics.return_value = mock_meta

    with patch("src.ingestion.topics.AdminClient", return_value=mock_admin):
        mgr = KafkaTopicManager()
    return mgr, mock_admin


def _future_ok() -> Future[None]:
    f: Future[None] = Future()
    f.set_result(None)
    return f


def _future_err(msg: str) -> Future[None]:
    f: Future[None] = Future()
    f.set_exception(Exception(msg))
    return f


# ---------------------------------------------------------------------------
# TopicSpec
# ---------------------------------------------------------------------------


class TestTopicSpec:
    def test_to_new_topic_name(self) -> None:
        spec = TopicSpec(
            name="test-topic",
            num_partitions=2,
            replication_factor=1,
            config={"retention.ms": "3600000"},
        )
        nt = spec.to_new_topic()
        assert nt.topic == "test-topic"

    def test_to_new_topic_partitions(self) -> None:
        spec = TopicSpec(name="t", num_partitions=4, replication_factor=1, config={})
        assert spec.to_new_topic().num_partitions == 4

    def test_frozen(self) -> None:
        spec = TopicSpec(name="t", num_partitions=1, replication_factor=1, config={})
        with pytest.raises(AttributeError):
            spec.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TOPIC_SPECS integrity
# ---------------------------------------------------------------------------


class TestTopicSpecsConstants:
    def test_four_topics_defined(self) -> None:
        assert len(TOPIC_SPECS) == 4

    def test_normalized_events_present(self) -> None:
        assert "normalized-events" in TOPICS_BY_NAME

    def test_anomaly_scores_present(self) -> None:
        assert "anomaly-scores" in TOPICS_BY_NAME

    def test_triage_decisions_present(self) -> None:
        assert "triage-decisions" in TOPICS_BY_NAME

    def test_graph_snapshots_present(self) -> None:
        assert "graph-snapshots" in TOPICS_BY_NAME

    def test_all_have_positive_partitions(self) -> None:
        for spec in TOPIC_SPECS:
            assert spec.num_partitions >= 1, f"{spec.name}: partitions < 1"

    def test_all_have_replication_factor(self) -> None:
        for spec in TOPIC_SPECS:
            assert spec.replication_factor >= 1, f"{spec.name}: replication < 1"

    def test_normalized_events_has_retention(self) -> None:
        spec = TOPICS_BY_NAME["normalized-events"]
        assert "retention.ms" in spec.config

    def test_topic_names_unique(self) -> None:
        names = [s.name for s in TOPIC_SPECS]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# KafkaTopicManager.ping
# ---------------------------------------------------------------------------


class TestPing:
    def test_ping_true_when_reachable(self) -> None:
        mgr, mock_admin = _make_manager()
        assert mgr.ping() is True

    def test_ping_false_on_exception(self) -> None:
        mgr, mock_admin = _make_manager()
        mock_admin.list_topics.side_effect = Exception("broker down")
        assert mgr.ping() is False


# ---------------------------------------------------------------------------
# KafkaTopicManager.ensure_topics
# ---------------------------------------------------------------------------


class TestEnsureTopics:
    def test_returns_ensure_result(self) -> None:
        mgr, mock_admin = _make_manager()
        mock_admin.create_topics.return_value = {
            s.name: _future_ok() for s in TOPIC_SPECS
        }
        result = mgr.ensure_topics()
        assert isinstance(result, TopicEnsureResult)

    def test_all_created_when_none_exist(self) -> None:
        mgr, mock_admin = _make_manager()
        mock_admin.create_topics.return_value = {
            s.name: _future_ok() for s in TOPIC_SPECS
        }
        result = mgr.ensure_topics()
        assert set(result.created) == {s.name for s in TOPIC_SPECS}
        assert result.already_exist == []
        assert result.failed == []

    def test_already_exist_when_all_present(self) -> None:
        mgr, mock_admin = _make_manager()
        # Simulate all topics existing already
        mock_meta = MagicMock()
        mock_meta.topics = {s.name: MagicMock() for s in TOPIC_SPECS}
        mock_admin.list_topics.return_value = mock_meta
        result = mgr.ensure_topics()
        assert set(result.already_exist) == {s.name for s in TOPIC_SPECS}
        assert result.created == []

    def test_failed_on_create_error(self) -> None:
        mgr, mock_admin = _make_manager()
        mock_admin.create_topics.return_value = {
            s.name: _future_err("broker error") for s in TOPIC_SPECS
        }
        result = mgr.ensure_topics()
        assert set(result.failed) == {s.name for s in TOPIC_SPECS}

    def test_already_exists_error_goes_to_already_exist(self) -> None:
        mgr, mock_admin = _make_manager()
        mock_admin.create_topics.return_value = {
            s.name: _future_err("topic already exists") for s in TOPIC_SPECS
        }
        result = mgr.ensure_topics()
        assert set(result.already_exist) == {s.name for s in TOPIC_SPECS}
        assert result.failed == []

    def test_custom_specs_used(self) -> None:
        mgr, mock_admin = _make_manager()
        custom = [TopicSpec(name="custom-topic", num_partitions=1, replication_factor=1, config={})]
        mock_admin.create_topics.return_value = {"custom-topic": _future_ok()}
        result = mgr.ensure_topics(specs=custom)
        assert "custom-topic" in result.created


# ---------------------------------------------------------------------------
# KafkaTopicManager.list_topics
# ---------------------------------------------------------------------------


class TestListTopics:
    def test_returns_list(self) -> None:
        mgr, mock_admin = _make_manager()
        # Build mock topic metadata
        mock_partition = MagicMock()
        mock_partition.replicas = [0]
        mock_topic_meta = MagicMock()
        mock_topic_meta.partitions = {0: mock_partition}
        mock_meta = MagicMock()
        mock_meta.topics = {"normalized-events": mock_topic_meta}
        mock_admin.list_topics.return_value = mock_meta

        result = mgr.list_topics()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TopicInfo)

    def test_internal_topics_excluded(self) -> None:
        mgr, mock_admin = _make_manager()
        mock_meta = MagicMock()
        mock_meta.topics = {"__consumer_offsets": MagicMock(), "normalized-events": MagicMock()}
        for t in mock_meta.topics.values():
            t.partitions = {}
        mock_admin.list_topics.return_value = mock_meta
        result = mgr.list_topics()
        names = [t.name for t in result]
        assert "__consumer_offsets" not in names
        assert "normalized-events" in names

    def test_empty_cluster_returns_empty_list(self) -> None:
        mgr, mock_admin = _make_manager()
        result = mgr.list_topics()
        assert result == []


# ---------------------------------------------------------------------------
# KafkaTopicManager.delete_topics
# ---------------------------------------------------------------------------


class TestDeleteTopics:
    def test_delete_returns_bool_per_topic(self) -> None:
        mgr, mock_admin = _make_manager()
        mock_admin.delete_topics.return_value = {
            "normalized-events": _future_ok(),
        }
        result = mgr.delete_topics(["normalized-events"])
        assert result["normalized-events"] is True

    def test_delete_failure_returns_false(self) -> None:
        mgr, mock_admin = _make_manager()
        mock_admin.delete_topics.return_value = {
            "normalized-events": _future_err("cannot delete"),
        }
        result = mgr.delete_topics(["normalized-events"])
        assert result["normalized-events"] is False
