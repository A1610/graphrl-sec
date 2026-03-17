"""
Kafka Topic Manager — creates and inspects GraphRL-Sec topics.

All topics used by the system are declared here as a single source of truth.
The manager is idempotent: calling ensure_topics() on an existing cluster
that already has the topics is a no-op.

Topics:
    normalized-events   — UnifiedEvent JSON, produced by ingestion CLI
    anomaly-scores      — per-event anomaly float produced by T-HetGAT (Phase 3)
    triage-decisions    — DRL triage agent actions (Phase 4)
    graph-snapshots     — serialized PyG HeteroData (optional, for replay)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from confluent_kafka.admin import AdminClient, NewTopic  # type: ignore[attr-defined]

from src.ingestion.config import IngestionConfig, settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Topic definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicSpec:
    """Specification for one Kafka topic."""

    name:              str
    num_partitions:    int
    replication_factor: int
    config:            dict[str, str]   # Kafka topic-level config overrides

    def to_new_topic(self) -> NewTopic:
        return NewTopic(
            self.name,
            num_partitions=self.num_partitions,
            replication_factor=self.replication_factor,
            config=self.config,
        )


# Production topic specs — partitions sized for single-node RTX 3050 development.
# Scale partitions proportionally for multi-broker production clusters.
TOPIC_SPECS: list[TopicSpec] = [
    TopicSpec(
        name="normalized-events",
        num_partitions=4,
        replication_factor=1,
        config={
            "retention.ms":       str(7 * 24 * 3600 * 1000),  # 7 days
            "compression.type":   "lz4",
            "cleanup.policy":     "delete",
            "max.message.bytes":  str(1024 * 1024),            # 1 MB max per message
        },
    ),
    TopicSpec(
        name="anomaly-scores",
        num_partitions=4,
        replication_factor=1,
        config={
            "retention.ms":       str(3 * 24 * 3600 * 1000),   # 3 days
            "compression.type":   "lz4",
            "cleanup.policy":     "delete",
            "max.message.bytes":  str(256 * 1024),              # 256 KB max
        },
    ),
    TopicSpec(
        name="triage-decisions",
        num_partitions=2,
        replication_factor=1,
        config={
            "retention.ms":       str(30 * 24 * 3600 * 1000),  # 30 days (audit trail)
            "compression.type":   "lz4",
            "cleanup.policy":     "delete",
        },
    ),
    TopicSpec(
        name="graph-snapshots",
        num_partitions=2,
        replication_factor=1,
        config={
            "retention.ms":       str(24 * 3600 * 1000),       # 1 day (large payloads)
            "compression.type":   "zstd",                       # better ratio for binary
            "cleanup.policy":     "delete",
            "max.message.bytes":  str(10 * 1024 * 1024),        # 10 MB — PyG graphs
        },
    ),
]

# Convenience lookup by name
TOPICS_BY_NAME: dict[str, TopicSpec] = {t.name: t for t in TOPIC_SPECS}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicEnsureResult:
    """Result of ensure_topics() call."""

    created:        list[str]   # topics successfully created
    already_exist:  list[str]   # topics that existed already
    failed:         list[str]   # topics that could not be created


@dataclass(frozen=True)
class TopicInfo:
    """Metadata about an existing topic."""

    name:           str
    num_partitions: int
    replication_factor: int
    config:         dict[str, str]


# ---------------------------------------------------------------------------
# Topic Manager
# ---------------------------------------------------------------------------


class KafkaTopicManager:
    """
    Creates and inspects GraphRL-Sec Kafka topics.

    Usage::

        mgr = KafkaTopicManager()
        result = mgr.ensure_topics()
        print(result.created)

    All operations are idempotent.  Creating a topic that already exists
    is silently treated as success.
    """

    def __init__(self, config: IngestionConfig | None = None) -> None:
        self._config = config or settings
        admin_conf: dict[str, Any] = {
            "bootstrap.servers": self._config.kafka_bootstrap_servers,
            # Short timeouts for CLI commands — fail fast if broker unreachable
            "socket.timeout.ms":         10_000,
            "metadata.request.timeout.ms": 10_000,
        }
        self._admin = AdminClient(admin_conf)
        self._log = logger.bind(brokers=self._config.kafka_bootstrap_servers)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return True if at least one broker is reachable."""
        try:
            metadata = self._admin.list_topics(timeout=5)
            return metadata is not None
        except Exception:  # noqa: BLE001
            return False

    def ensure_topics(
        self,
        specs: list[TopicSpec] | None = None,
    ) -> TopicEnsureResult:
        """
        Create all required topics if they do not already exist.

        Args:
            specs: Override the default TOPIC_SPECS list.  Useful for tests.

        Returns:
            TopicEnsureResult with created / already_exist / failed lists.
        """
        target = specs or TOPIC_SPECS
        existing = self._list_existing_topic_names()

        to_create = [s for s in target if s.name not in existing]
        already   = [s.name for s in target if s.name in existing]

        created: list[str] = []
        failed:  list[str] = []

        if to_create:
            new_topics = [s.to_new_topic() for s in to_create]
            futures = self._admin.create_topics(new_topics, validate_only=False)

            for topic_name, future in futures.items():
                try:
                    future.result()   # blocks until create completes or raises
                    created.append(topic_name)
                    self._log.info("topic_created", topic=topic_name)
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc).lower()
                    if "already exists" in msg or "topic_already_exists" in msg.replace(" ", "_"):
                        already.append(topic_name)
                        self._log.debug("topic_already_exists", topic=topic_name)
                    else:
                        failed.append(topic_name)
                        self._log.error("topic_create_failed", topic=topic_name, error=str(exc))

        result = TopicEnsureResult(created=created, already_exist=already, failed=failed)
        self._log.info(
            "ensure_topics_complete",
            created=len(created),
            already_exist=len(already),
            failed=len(failed),
        )
        return result

    def list_topics(self) -> list[TopicInfo]:
        """
        Return metadata for all topics currently on the cluster.

        Returns:
            List of TopicInfo objects (one per topic, sorted by name).
        """
        metadata = self._admin.list_topics(timeout=10)
        results: list[TopicInfo] = []

        for name, topic_meta in sorted(metadata.topics.items()):
            if name.startswith("__"):
                continue   # skip internal Kafka topics
            results.append(TopicInfo(
                name=name,
                num_partitions=len(topic_meta.partitions),
                replication_factor=(
                    len(next(iter(topic_meta.partitions.values())).replicas)
                    if topic_meta.partitions else 0
                ),
                config={},   # config populated on demand via describe_topics()
            ))

        return results

    def delete_topics(self, names: list[str]) -> dict[str, bool]:
        """
        Delete topics by name.

        WARNING: Irreversible — only use in development / test cleanup.

        Returns:
            Dict mapping topic_name -> True (deleted) / False (error).
        """
        futures = self._admin.delete_topics(names, operation_timeout=15)
        results: dict[str, bool] = {}
        for name, future in futures.items():
            try:
                future.result()
                results[name] = True
                self._log.info("topic_deleted", topic=name)
            except Exception as exc:  # noqa: BLE001
                results[name] = False
                self._log.error("topic_delete_failed", topic=name, error=str(exc))
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _list_existing_topic_names(self) -> set[str]:
        """Return the set of topic names currently on the cluster."""
        try:
            metadata = self._admin.list_topics(timeout=10)
            return {name for name in metadata.topics if not name.startswith("__")}
        except Exception as exc:  # noqa: BLE001
            self._log.warning("list_topics_failed", error=str(exc))
            return set()
