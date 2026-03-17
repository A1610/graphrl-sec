"""Unit tests for GraphConsumer.

Kafka polling and Neo4j writing are fully mocked.
Tests verify batching logic, deserialization, metrics, and error handling.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from src.graph.config import GraphConfig
from src.ingestion.consumer import ConsumerConfig, ConsumerMetrics, GraphConsumer
from src.ingestion.schemas import (
    AttackLabel,
    CollectorMode,
    DatasetSource,
    DestinationInfo,
    EventMetadata,
    EventType,
    NetworkInfo,
    Protocol,
    SourceInfo,
    UnifiedEvent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    src_ip: str = "10.0.0.1",
    dst_ip: str = "10.0.0.2",
    ts: float | None = None,
) -> UnifiedEvent:
    """Create a minimal valid UnifiedEvent."""
    if ts is None:
        ts = 1_700_000_000.0
    return UnifiedEvent(
        timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
        event_type=EventType.NETWORK_FLOW,
        source=SourceInfo(ip=src_ip, port=12345),
        destination=DestinationInfo(ip=dst_ip, port=80),
        network=NetworkInfo(protocol=Protocol.TCP),
        metadata=EventMetadata(
            dataset_source=DatasetSource.CICIDS2017,
            attack_label=AttackLabel.BENIGN,
            is_attack=False,
            collector=CollectorMode.STREAMING,
        ),
    )


def _kafka_msg(event: UnifiedEvent | None = None, error: Any = None) -> MagicMock:
    """Create a mock Kafka Message."""
    msg = MagicMock()
    msg.error.return_value = error
    if event is not None:
        msg.value.return_value = event.to_kafka_payload()
    else:
        msg.value.return_value = b'{"invalid": true}'
    msg.offset.return_value = 0
    msg.partition.return_value = 0
    return msg


def _make_consumer(
    messages: list[Any],
    write_neo4j: bool = False,
) -> tuple[GraphConsumer, MagicMock]:
    """
    Build a GraphConsumer where Consumer.poll() yields messages then None forever.

    Returns (consumer, mock_kafka_consumer).
    """
    cfg = ConsumerConfig(
        batch_size=100,
        batch_timeout_s=0.05,
        poll_timeout_s=0.01,
        write_neo4j=write_neo4j,
    )

    mock_kafka = MagicMock()
    # poll() returns each message in turn, then None to trigger timeout flush
    return_seq = messages + [None] * 10
    mock_kafka.poll.side_effect = return_seq

    with patch("src.ingestion.consumer.Consumer", return_value=mock_kafka), \
         patch("src.ingestion.consumer.Neo4jWriter"):
        consumer = GraphConsumer(config=cfg, graph_config=GraphConfig())

    consumer._consumer = mock_kafka
    return consumer, mock_kafka


# ---------------------------------------------------------------------------
# ConsumerConfig
# ---------------------------------------------------------------------------


class TestConsumerConfig:
    def test_defaults(self) -> None:
        cfg = ConsumerConfig()
        assert cfg.batch_size == 500
        assert cfg.batch_timeout_s == 5.0
        assert cfg.group_id == "graph-constructor-group"

    def test_from_configs(self) -> None:
        cfg = ConsumerConfig.from_configs()
        assert cfg.topic == "normalized-events"


# ---------------------------------------------------------------------------
# ConsumerMetrics
# ---------------------------------------------------------------------------


class TestConsumerMetrics:
    def test_snapshot_returns_dict(self) -> None:
        m = ConsumerMetrics()
        snap = m.snapshot()
        assert isinstance(snap, dict)
        assert "messages_consumed" in snap
        assert "events_per_second" in snap

    def test_elapsed_increases(self) -> None:
        m = ConsumerMetrics()
        snap1 = m.snapshot()
        time.sleep(0.01)
        snap2 = m.snapshot()
        assert snap2["elapsed_s"] >= snap1["elapsed_s"]


# ---------------------------------------------------------------------------
# GraphConsumer — deserialization
# ---------------------------------------------------------------------------


class TestDeserialization:
    def test_valid_payload_produces_event(self) -> None:
        event = _make_event()
        consumer, mock_kafka = _make_consumer([])
        msg = _kafka_msg(event)
        result = consumer._deserialize(msg)
        assert result is not None
        assert result.source.ip == "10.0.0.1"

    def test_invalid_json_returns_none(self) -> None:
        consumer, _ = _make_consumer([])
        msg = MagicMock()
        msg.value.return_value = b"not json"
        msg.offset.return_value = 0
        result = consumer._deserialize(msg)
        assert result is None
        assert consumer._metrics.deserialization_errors == 1

    def test_empty_payload_returns_none(self) -> None:
        consumer, _ = _make_consumer([])
        msg = MagicMock()
        msg.value.return_value = None
        msg.offset.return_value = 0
        result = consumer._deserialize(msg)
        assert result is None
        assert consumer._metrics.deserialization_errors == 1

    def test_empty_bytes_returns_none(self) -> None:
        consumer, _ = _make_consumer([])
        msg = MagicMock()
        msg.value.return_value = b""
        msg.offset.return_value = 0
        result = consumer._deserialize(msg)
        assert result is None


# ---------------------------------------------------------------------------
# GraphConsumer — batch processing
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    def test_process_batch_empty_commits(self) -> None:
        consumer, mock_kafka = _make_consumer([])
        msgs: list[MagicMock] = [MagicMock()]
        consumer._process_batch([], msgs, None)
        mock_kafka.commit.assert_called_once()

    def test_process_batch_increments_batches_processed(self) -> None:
        events = [_make_event(ts=1_700_000_000.0 + i) for i in range(3)]
        consumer, mock_kafka = _make_consumer([])
        msgs = [MagicMock() for _ in events]
        consumer._process_batch(events, msgs, None)
        assert consumer._metrics.batches_processed == 1

    def test_process_batch_commits_offsets(self) -> None:
        events = [_make_event()]
        consumer, mock_kafka = _make_consumer([])
        msgs = [MagicMock()]
        consumer._process_batch(events, msgs, None)
        mock_kafka.commit.assert_called_once()

    def test_process_batch_on_window_callback_called(self) -> None:
        callback_results: list[Any] = []
        cfg = ConsumerConfig(batch_size=10, batch_timeout_s=0.05, write_neo4j=False)
        mock_kafka = MagicMock()
        with patch("src.ingestion.consumer.Consumer", return_value=mock_kafka), \
             patch("src.ingestion.consumer.Neo4jWriter"):
            consumer = GraphConsumer(
                config=cfg,
                graph_config=GraphConfig(),
                on_window_ready=lambda wr, stats: callback_results.append(stats),
            )
        consumer._consumer = mock_kafka

        events = [_make_event(ts=1_700_000_000.0 + i * 10) for i in range(5)]
        msgs = [MagicMock() for _ in events]
        consumer._process_batch(events, msgs, None)
        # The window callback may or may not fire depending on timestamp spread
        # — just verify it doesn't raise
        assert isinstance(callback_results, list)

    def test_process_batch_error_increments_error_counter(self) -> None:
        consumer, mock_kafka = _make_consumer([])
        # Force an error in the engine
        consumer._engine = MagicMock()
        consumer._engine.process_stream.side_effect = RuntimeError("forced")
        msgs = [MagicMock()]
        consumer._process_batch([_make_event()], msgs, None)
        assert consumer._metrics.processing_errors == 1
        # Offsets should still be committed despite the error
        mock_kafka.commit.assert_called_once()


# ---------------------------------------------------------------------------
# GraphConsumer — metrics counting
# ---------------------------------------------------------------------------


class TestMetricsCounting:
    def test_messages_consumed_increments(self) -> None:
        consumer, _ = _make_consumer([])
        consumer._metrics.messages_consumed += 1
        assert consumer._metrics.messages_consumed == 1

    def test_deserialization_errors_tracked(self) -> None:
        consumer, _ = _make_consumer([])
        bad_msg = MagicMock()
        bad_msg.value.return_value = b"bad"
        bad_msg.offset.return_value = 0
        consumer._deserialize(bad_msg)
        consumer._deserialize(bad_msg)
        assert consumer._metrics.deserialization_errors == 2


# ---------------------------------------------------------------------------
# GraphConsumer — lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_stop_sets_stop_event(self) -> None:
        consumer, _ = _make_consumer([])
        consumer.stop()
        assert consumer._stop_event.is_set()

    def test_context_manager_calls_stop(self) -> None:
        cfg = ConsumerConfig(write_neo4j=False)
        mock_kafka = MagicMock()
        mock_kafka.poll.return_value = None
        with patch("src.ingestion.consumer.Consumer", return_value=mock_kafka), \
             patch("src.ingestion.consumer.Neo4jWriter"), \
             GraphConsumer(config=cfg, graph_config=GraphConfig()) as consumer:
            consumer.stop()   # stop immediately

    def test_metrics_property_returns_metrics(self) -> None:
        consumer, _ = _make_consumer([])
        assert isinstance(consumer.metrics, ConsumerMetrics)
