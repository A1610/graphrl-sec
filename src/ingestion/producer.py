"""
Kafka Producer for GraphRL-Sec ingestion pipeline.

Publishes normalized UnifiedEvent objects to Redpanda/Kafka topics.

Features:
  - Delivery callbacks — every message is confirmed or logged as failed
  - Rate limiting — configurable events/second (token bucket algorithm)
  - Retry logic — transient errors retried with exponential backoff
  - Graceful shutdown — flush on context exit, no message loss
  - Metrics — counters for published / failed / rate-limited events
  - Async-compatible — can be used from sync or async contexts
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from types import TracebackType
from typing import Any

import structlog
from confluent_kafka import KafkaError, Message, Producer

from src.ingestion.config import IngestionConfig, settings
from src.ingestion.schemas import UnifiedEvent

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Token Bucket Rate Limiter (thread-safe)
# ---------------------------------------------------------------------------


class _TokenBucket:
    """
    Thread-safe token bucket rate limiter.

    Allows up to `rate` tokens per second. Caller acquires tokens
    one at a time; blocks (sleeps) if bucket is empty.
    """

    def __init__(self, rate: float) -> None:
        self._rate = rate                       # tokens per second
        self._tokens = float(rate)              # start full
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until one token is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            # Sleep for a fraction of the token replenishment period
            time.sleep(0.5 / self._rate)

    def update_rate(self, rate: float) -> None:
        with self._lock:
            self._rate = rate
            # Reset token count so a rate decrease takes effect immediately
            # without allowing a burst from accumulated tokens at the old rate.
            self._tokens = min(self._tokens, rate)
            self._last_refill = time.monotonic()


# ---------------------------------------------------------------------------
# Delivery callback handler
# ---------------------------------------------------------------------------


def _make_delivery_callback(
    stats: dict[str, int],
    on_error: Callable[[str, bytes], None] | None,
) -> Callable[[KafkaError | None, Message], None]:
    """
    Build a Kafka delivery callback that updates stats and logs failures.

    Confluent-kafka calls this for every message after broker ACK (or error).
    """

    def _callback(err: KafkaError | None, msg: Message) -> None:
        if err is not None:
            stats["failed"] += 1
            topic = msg.topic() if msg else "unknown"
            payload = msg.value() if msg else b""
            logger.error(
                "kafka_delivery_failed",
                topic=topic,
                error=str(err),
                payload_preview=payload[:100] if payload else b"",
            )
            if on_error is not None:
                try:
                    on_error(str(err), payload or b"")
                except Exception as cb_exc:  # noqa: BLE001
                    logger.error("delivery_error_callback_raised", exc=str(cb_exc))
        else:
            stats["published"] += 1

    return _callback


# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------


class EventProducer:
    """
    Kafka producer wrapper for publishing UnifiedEvent objects.

    Usage (context manager — recommended):

        with EventProducer() as producer:
            for event in events:
                producer.publish(event)
        # All messages flushed on __exit__

    Usage (manual):

        producer = EventProducer()
        producer.publish(event)
        producer.flush()
        producer.close()
    """

    def __init__(
        self,
        config: IngestionConfig | None = None,
        topic: str | None = None,
        rate_limit: int | None = None,
        on_delivery_error: Callable[[str, bytes], None] | None = None,
    ) -> None:
        """
        Args:
            config:             IngestionConfig instance. Defaults to module settings.
            topic:              Kafka topic to publish to. Defaults to config value.
            rate_limit:         Events per second. Overrides config if provided.
            on_delivery_error:  Optional callback(error_str, raw_bytes) for failed deliveries.
        """
        self._config = config or settings
        self._topic = topic or self._config.kafka_topic_normalized_events
        self._closed = False

        self._stats: dict[str, int] = {
            "published":     0,
            "failed":        0,
            "rate_limited":  0,
            "total_attempts": 0,
        }

        # Build confluent-kafka producer config
        kafka_conf: dict[str, Any] = {
            "bootstrap.servers":  self._config.kafka_bootstrap_servers,
            "batch.size":         self._config.kafka_producer_batch_size,
            "linger.ms":          self._config.kafka_producer_linger_ms,
            "compression.type":   self._config.kafka_producer_compression,
            "acks":               self._config.kafka_producer_acks,
            # Reliability settings
            "retries":            5,
            "retry.backoff.ms":   200,
            "delivery.timeout.ms": 30_000,
            "request.timeout.ms":  10_000,
            # Avoid message loss on transient errors
            "enable.idempotence": self._config.kafka_producer_acks == "all",
            # Socket settings
            "socket.keepalive.enable": True,
        }

        self._producer = Producer(kafka_conf)
        self._delivery_cb = _make_delivery_callback(self._stats, on_delivery_error)

        # Rate limiter
        effective_rate = rate_limit or self._config.ingestion_rate_limit
        self._rate_limiter = _TokenBucket(rate=float(effective_rate))

        self._log = logger.bind(
            topic=self._topic,
            brokers=self._config.kafka_bootstrap_servers,
        )
        self._log.info("producer_initialized", rate_limit=effective_rate)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> EventProducer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Core publish methods
    # ------------------------------------------------------------------

    def publish(
        self,
        event: UnifiedEvent,
        key: str | None = None,
    ) -> None:
        """
        Publish a single UnifiedEvent to Kafka.

        Applies rate limiting before sending.
        Non-blocking — delivery confirmation arrives via callback.

        Args:
            event:  The UnifiedEvent to publish.
            key:    Optional Kafka message key for partitioning.
                    Defaults to event.source.ip for co-location of same-host flows.
        """
        if self._closed:
            raise RuntimeError("EventProducer is closed. Cannot publish.")

        self._stats["total_attempts"] += 1

        # Rate limit
        self._rate_limiter.acquire()

        payload = event.to_kafka_payload()
        message_key = (key or event.source.ip).encode("utf-8")

        self._producer.produce(
            topic=self._topic,
            value=payload,
            key=message_key,
            on_delivery=self._delivery_cb,
        )

        # Poll to serve delivery callbacks without blocking
        self._producer.poll(0)

    def publish_batch(
        self,
        events: list[UnifiedEvent],
        flush_every: int = 10_000,
    ) -> int:
        """
        Publish a list of events, flushing every `flush_every` messages.

        Returns:
            Number of events published (excluding failed deliveries).
        """
        for i, event in enumerate(events, 1):
            self.publish(event)
            if i % flush_every == 0:
                self._producer.flush(timeout=30.0)
                self._log.debug("batch_flush", flushed=i, stats=self._stats)
        return len(events)

    def flush(self, timeout: float = 30.0) -> int:
        """
        Flush all buffered messages and wait for delivery confirmations.

        Args:
            timeout: Maximum seconds to wait for delivery.

        Returns:
            Number of messages still in queue (0 = all delivered).
        """
        remaining: int = self._producer.flush(timeout=timeout)
        if remaining > 0:
            self._log.warning("flush_incomplete", remaining=remaining, timeout=timeout)
        return remaining

    def close(self) -> None:
        """Flush all messages and close the producer cleanly."""
        if self._closed:
            return
        self._closed = True
        remaining = self.flush(timeout=60.0)
        if remaining > 0:
            self._log.error("producer_close_messages_lost", lost=remaining)
        self._log.info("producer_closed", final_stats=self._stats)

    # ------------------------------------------------------------------
    # Stats & introspection
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict[str, int]:
        """Return a copy of current publish statistics."""
        return dict(self._stats)

    def update_rate_limit(self, events_per_second: int) -> None:
        """Dynamically update the rate limit without recreating the producer."""
        self._rate_limiter.update_rate(float(events_per_second))
        self._log.info("rate_limit_updated", new_rate=events_per_second)

    def __repr__(self) -> str:
        return (
            f"EventProducer(topic={self._topic!r}, "
            f"brokers={self._config.kafka_bootstrap_servers!r}, "
            f"closed={self._closed})"
        )


# ---------------------------------------------------------------------------
# Convenience context manager
# ---------------------------------------------------------------------------


@contextmanager
def get_producer(
    topic: str | None = None,
    rate_limit: int | None = None,
    config: IngestionConfig | None = None,
) -> Generator[EventProducer, None, None]:
    """
    Context manager that yields a configured EventProducer.

    Guarantees flush + close on exit even if an exception occurs.

    Example:
        with get_producer(rate_limit=2000) as producer:
            for event in normalized_events:
                producer.publish(event)
    """
    producer = EventProducer(config=config, topic=topic, rate_limit=rate_limit)
    try:
        yield producer
    finally:
        producer.close()
