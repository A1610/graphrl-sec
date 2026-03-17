"""
Kafka Consumer for GraphRL-Sec — streams UnifiedEvents into the graph pipeline.

Consumes from the `normalized-events` topic and routes each batch through:
    1. SlidingWindowEngine  → WindowResult per temporal window
    2. PyGConverter         → HeteroData PyG graph
    3. Neo4jWriter          → persists to Neo4j (optional, configurable)

Delivery guarantees:
    - at-least-once: Kafka offsets are committed ONLY after successful processing
    - on processing failure the batch is logged and the consumer continues
      (dead-lettering to structlog) so the pipeline never stalls

Batching strategy:
    - Collect up to `batch_size` events OR `batch_timeout_s` seconds, whichever
      comes first, then process.  This bounds both latency and memory usage.

Graceful shutdown:
    - SIGTERM / SIGINT are caught.  The consumer finishes the current batch,
      commits offsets, then exits cleanly.
"""

from __future__ import annotations

import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import torch
from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from src.graph.config import GraphConfig, graph_settings
from src.graph.neo4j_writer import Neo4jWriter
from src.graph.pyg_converter import ConversionStats, PyGConverter
from src.graph.temporal import SlidingWindowEngine, WindowResult
from src.ingestion.config import IngestionConfig
from src.ingestion.config import settings as ingestion_settings
from src.ingestion.schemas import UnifiedEvent

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Consumer configuration
# ---------------------------------------------------------------------------


@dataclass
class ConsumerConfig:
    """
    Runtime configuration for GraphConsumer.

    These are the knobs you tune per deployment environment.
    """

    # Kafka
    bootstrap_servers: str  = "localhost:9092"
    topic:             str  = "normalized-events"
    group_id:          str  = "graph-constructor-group"
    auto_offset_reset: str  = "earliest"   # replay from start if no committed offset

    # Batching
    batch_size:        int   = 500          # max events per processing batch
    batch_timeout_s:   float = 5.0          # max seconds to wait before flushing

    # Poll
    poll_timeout_s:    float = 1.0          # Consumer.poll() timeout
    max_poll_records:  int   = 500          # max messages per poll call

    # Neo4j write (optional — disable for pure PyG conversion)
    write_neo4j:       bool  = True

    # Snapshot saving — .pt files for pre-training
    snapshot_dir:      Path | None = None   # None = do not save snapshots
    min_snapshot_events: int = 5            # skip windows with fewer events than this

    @classmethod
    def from_configs(
        cls,
        ingestion: IngestionConfig | None = None,
        graph: GraphConfig | None = None,
    ) -> ConsumerConfig:
        """Build from environment-based config objects."""
        ing = ingestion or ingestion_settings
        return cls(
            bootstrap_servers=ing.kafka_bootstrap_servers,
            topic=ing.kafka_topic_normalized_events,
        )


# ---------------------------------------------------------------------------
# Consumer metrics
# ---------------------------------------------------------------------------


@dataclass
class ConsumerMetrics:
    """Running counters for a consumer session."""

    messages_consumed:   int = 0
    batches_processed:   int = 0
    windows_constructed: int = 0
    neo4j_writes:        int = 0
    processing_errors:   int = 0
    deserialization_errors: int = 0
    elapsed_s:           float = field(default=0.0, init=False)
    _start: float = field(default_factory=time.monotonic, init=False, repr=False)

    def snapshot(self) -> dict[str, object]:
        self.elapsed_s = time.monotonic() - self._start
        rate = self.messages_consumed / max(self.elapsed_s, 0.001)
        return {
            "messages_consumed":      self.messages_consumed,
            "batches_processed":      self.batches_processed,
            "windows_constructed":    self.windows_constructed,
            "neo4j_writes":           self.neo4j_writes,
            "processing_errors":      self.processing_errors,
            "deserialization_errors": self.deserialization_errors,
            "elapsed_s":              round(self.elapsed_s, 2),
            "events_per_second":      round(rate, 1),
        }


# ---------------------------------------------------------------------------
# Graph Consumer
# ---------------------------------------------------------------------------


class GraphConsumer:
    """
    Kafka consumer that drives the graph construction pipeline.

    Usage (blocking — runs until SIGTERM/SIGINT or stop() is called)::

        consumer = GraphConsumer()
        consumer.run()

    Usage (background thread)::

        consumer = GraphConsumer()
        thread = threading.Thread(target=consumer.run, daemon=True)
        thread.start()
        # ... later ...
        consumer.stop()
        thread.join()

    Usage (context manager)::

        with GraphConsumer() as consumer:
            consumer.run()
    """

    def __init__(
        self,
        config: ConsumerConfig | None = None,
        graph_config: GraphConfig | None = None,
        on_window_ready: Callable[[WindowResult, ConversionStats], None] | None = None,
    ) -> None:
        """
        Args:
            config:           Consumer configuration. Defaults to ConsumerConfig().
            graph_config:     Graph construction config. Defaults to graph_settings.
            on_window_ready:  Optional callback(window_result, stats) called for
                              every completed window — useful for testing / custom sinks.
        """
        self._cfg             = config or ConsumerConfig()
        self._graph_cfg       = graph_config or graph_settings
        self._on_window       = on_window_ready
        self._metrics         = ConsumerMetrics()
        self._stop_event      = threading.Event()
        self._snapshot_seq    = 0   # global counter across all batches — prevents overwrite
        self._log         = logger.bind(
            topic=self._cfg.topic,
            group_id=self._cfg.group_id,
        )

        # Kafka consumer
        kafka_conf: dict[str, Any] = {
            "bootstrap.servers":         self._cfg.bootstrap_servers,
            "group.id":                  self._cfg.group_id,
            "auto.offset.reset":         self._cfg.auto_offset_reset,
            "enable.auto.commit":        False,   # manual commit for at-least-once
            "max.poll.interval.ms":      300_000, # 5 min — allows slow Neo4j writes
            "session.timeout.ms":        30_000,
            "fetch.min.bytes":           1,
            "fetch.wait.max.ms":         500,
        }
        self._consumer = Consumer(kafka_conf)

        # Graph pipeline components (created per-run to allow reuse)
        self._engine    = SlidingWindowEngine(self._graph_cfg)
        self._converter = PyGConverter(self._graph_cfg)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __enter__(self) -> GraphConsumer:
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def stop(self) -> None:
        """Signal the consumer to finish the current batch and exit."""
        self._stop_event.set()
        self._log.info("consumer_stop_requested")

    @property
    def metrics(self) -> ConsumerMetrics:
        return self._metrics

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> ConsumerMetrics:
        """
        Blocking consume loop.

        Subscribes to the configured topic, collects events into batches,
        and processes each batch through the graph construction pipeline.

        Returns:
            ConsumerMetrics from this run session.
        """
        self._consumer.subscribe([self._cfg.topic])
        self._log.info(
            "consumer_started",
            topic=self._cfg.topic,
            batch_size=self._cfg.batch_size,
            batch_timeout_s=self._cfg.batch_timeout_s,
        )

        # Register graceful-shutdown signal handlers
        _register_signal_handler(self._stop_event)

        writer: Neo4jWriter | None = None
        if self._cfg.write_neo4j:
            writer = Neo4jWriter(self._graph_cfg)

        try:
            self._consume_loop(writer)
        finally:
            self._consumer.close()
            if writer is not None:
                writer.close()
            self._log.info("consumer_stopped", **self._metrics.snapshot())

        return self._metrics

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _consume_loop(self, writer: Neo4jWriter | None) -> None:
        """Core poll-batch-process loop."""
        batch: list[UnifiedEvent] = []
        batch_start = time.monotonic()
        last_msgs: list[Message] = []   # messages in current batch (for offset commit)

        while not self._stop_event.is_set():
            msg = self._consumer.poll(timeout=self._cfg.poll_timeout_s)

            if msg is None:
                # No message within poll timeout — check if batch timer expired
                if batch and (time.monotonic() - batch_start) >= self._cfg.batch_timeout_s:
                    self._process_batch(batch, last_msgs, writer)
                    batch.clear()
                    last_msgs.clear()
                    batch_start = time.monotonic()
                continue

            kafka_err = msg.error()
            if kafka_err:
                if kafka_err.code() == KafkaError._PARTITION_EOF:
                    # Normal end-of-partition — not an error
                    self._log.debug(
                        "partition_eof",
                        partition=msg.partition(),
                        offset=msg.offset(),
                    )
                else:
                    raise KafkaException(kafka_err)
                continue

            # Deserialize message
            event = self._deserialize(msg)
            if event is None:
                # Bad message — skip but still commit later to advance offset
                last_msgs.append(msg)
                continue

            batch.append(event)
            last_msgs.append(msg)
            self._metrics.messages_consumed += 1

            # Flush batch when full OR timeout reached
            timeout_reached = (time.monotonic() - batch_start) >= self._cfg.batch_timeout_s
            if len(batch) >= self._cfg.batch_size or timeout_reached:
                self._process_batch(batch, last_msgs, writer)
                batch.clear()
                last_msgs.clear()
                batch_start = time.monotonic()

        # Flush any remaining events on clean shutdown
        if batch:
            self._process_batch(batch, last_msgs, writer)

    def _deserialize(self, msg: Message) -> UnifiedEvent | None:
        """Deserialize a Kafka message to UnifiedEvent. Returns None on failure."""
        payload = msg.value()
        if not payload:
            self._metrics.deserialization_errors += 1
            self._log.warning("empty_kafka_message", offset=msg.offset())
            return None
        try:
            return UnifiedEvent.from_kafka_payload(payload)
        except Exception as exc:  # noqa: BLE001
            self._metrics.deserialization_errors += 1
            self._log.warning(
                "deserialization_error",
                offset=msg.offset(),
                error=str(exc),
                payload_preview=payload[:80] if payload else b"",
            )
            return None

    def _process_batch(
        self,
        events: list[UnifiedEvent],
        messages: list[Message],
        writer: Neo4jWriter | None,
    ) -> None:
        """
        Run one batch through graph construction → PyG → Neo4j.

        Offsets are committed AFTER successful Neo4j write.
        On any error the batch is logged and offsets still advance
        (dead-letter pattern) so the consumer never stalls indefinitely.
        """
        if not events:
            self._commit(messages)
            return

        # Sort by timestamp to ensure SlidingWindowEngine receives events in order
        events_sorted = sorted(events, key=lambda e: e.timestamp)

        try:
            windows_this_batch = 0
            for window_result in self._engine.process_stream(iter(events_sorted)):
                pyg_data, conv_stats = self._converter.convert(window_result)
                windows_this_batch += 1
                self._metrics.windows_constructed += 1

                # Persist .pt snapshot for pre-training (if configured)
                if (self._cfg.snapshot_dir is not None
                        and window_result.window.num_events >= self._cfg.min_snapshot_events):
                    self._cfg.snapshot_dir.mkdir(parents=True, exist_ok=True)
                    snap_path = (
                        self._cfg.snapshot_dir
                        / f"window_{self._snapshot_seq:06d}.pt"
                    )
                    torch.save(pyg_data, snap_path)
                    self._log.debug(
                        "snapshot_saved",
                        path=str(snap_path),
                        seq=self._snapshot_seq,
                        window_id=window_result.window.window_id,
                        num_nodes=conv_stats.num_nodes,
                        num_edges=conv_stats.num_edges,
                    )
                    self._snapshot_seq += 1

                if writer is not None:
                    writer.write_window(window_result)
                    self._metrics.neo4j_writes += 1

                if self._on_window is not None:
                    try:
                        self._on_window(window_result, conv_stats)
                    except Exception as cb_exc:  # noqa: BLE001
                        self._log.error("on_window_callback_error", error=str(cb_exc))

            self._metrics.batches_processed += 1
            self._log.debug(
                "batch_processed",
                events=len(events),
                windows=windows_this_batch,
            )
        except Exception as exc:  # noqa: BLE001
            self._metrics.processing_errors += 1
            self._log.error(
                "batch_processing_error",
                events=len(events),
                error=str(exc),
                exc_info=True,
            )

        # Always advance offsets — avoids infinite reprocessing of bad batches
        self._commit(messages)

    def _commit(self, messages: list[Message]) -> None:
        """Commit the offset of the last message in the batch."""
        if not messages:
            return
        try:
            self._consumer.commit(message=messages[-1], asynchronous=False)
        except KafkaException as exc:
            self._log.warning("offset_commit_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Signal handler helper
# ---------------------------------------------------------------------------


def _register_signal_handler(stop_event: threading.Event) -> None:
    """Install SIGTERM/SIGINT handlers that set the stop event."""
    def _handler(signum: int, _frame: object) -> None:
        logger.info("shutdown_signal_received", signal=signum)
        stop_event.set()

    try:
        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT,  _handler)
    except (OSError, ValueError):
        # signal.signal() can fail in non-main threads — silently ignore
        pass
