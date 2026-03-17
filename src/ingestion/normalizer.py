"""
Event Normalizer — converts raw parser output to UnifiedEvent objects.

The normalizer sits between parsers and the Kafka producer / batch loader.
It is the final validation gate: any row that cannot produce a valid
UnifiedEvent is rejected here with a structured log entry.

Pipeline:
    Parser.parse_file() -> Iterator[dict]
        -> EventNormalizer.normalize() -> UnifiedEvent | None
            -> KafkaProducer / BatchLoader
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import structlog
from pydantic import ValidationError

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

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Protocol string normalization
# ---------------------------------------------------------------------------
_PROTO_NORMALIZE: dict[str, Protocol] = {
    "TCP":   Protocol.TCP,
    "UDP":   Protocol.UDP,
    "ICMP":  Protocol.ICMP,
    "ICMP6": Protocol.ICMP,
    "6":     Protocol.TCP,
    "17":    Protocol.UDP,
    "1":     Protocol.ICMP,
}


def _to_protocol(raw: Any) -> Protocol:
    s = str(raw or "").strip().upper()
    return _PROTO_NORMALIZE.get(s, Protocol.OTHER)


def _to_dataset_source(raw: Any) -> DatasetSource:
    s = str(raw or "").strip().upper().replace("-", "_")
    try:
        return DatasetSource(s)
    except ValueError:
        mapping = {
            "CICIDS2017": DatasetSource.CICIDS2017,
            "UNSW_NB15":  DatasetSource.UNSW_NB15,
            "UNSWNB15":   DatasetSource.UNSW_NB15,
            "LANL":       DatasetSource.LANL,
        }
        return mapping.get(s, DatasetSource.SYNTHETIC)


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


class EventNormalizer:
    """
    Converts raw parser row dicts into validated UnifiedEvent objects.

    Thread-safe — holds no mutable state after construction.
    One instance can be shared across threads.
    """

    def __init__(
        self,
        collector: CollectorMode = CollectorMode.BATCH,
        drop_benign_ratio: float = 0.0,
        deduplicate: bool = True,
    ) -> None:
        """
        Args:
            collector:          How events were collected (batch / streaming).
            drop_benign_ratio:  Fraction of BENIGN events to drop for class
                                balance during training (0.0 = keep all).
                                Set to e.g. 0.8 to keep 20% of benign events.
            deduplicate:        Track seen dedup keys to skip exact duplicates.
        """
        self._collector = collector
        self._drop_benign_ratio = drop_benign_ratio
        self._deduplicate = deduplicate
        self._seen_keys: set[str] = set()

        # Counters for metrics
        self._stats: dict[str, int] = {
            "total":      0,
            "normalized": 0,
            "skipped_validation": 0,
            "skipped_duplicate":  0,
            "skipped_benign_drop": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize(self, row: dict[str, Any]) -> UnifiedEvent | None:
        """
        Convert one raw parser row dict to a UnifiedEvent.

        Returns None (and logs reason) if the row should be skipped.
        Never raises — all exceptions are caught and logged.
        """
        self._stats["total"] += 1

        try:
            event = self._build_event(row)
        except ValidationError as exc:
            self._stats["skipped_validation"] += 1
            logger.debug(
                "event_validation_failed",
                errors=exc.errors(include_url=False),
                src_ip=row.get("src_ip"),
                dst_ip=row.get("dst_ip"),
            )
            return None
        except Exception as exc:
            self._stats["skipped_validation"] += 1
            logger.warning("event_normalization_error", error=str(exc), row_keys=list(row.keys()))
            return None

        # Deduplication check
        if self._deduplicate:
            key = event.dedup_key()
            if key in self._seen_keys:
                self._stats["skipped_duplicate"] += 1
                return None
            self._seen_keys.add(key)

        # Optional benign downsampling (for class balance)
        if self._drop_benign_ratio > 0.0 and not event.metadata.is_attack:
            import random
            if random.random() < self._drop_benign_ratio:
                self._stats["skipped_benign_drop"] += 1
                return None

        self._stats["normalized"] += 1
        return event

    def normalize_batch(
        self,
        rows: Iterator[dict[str, Any]],
    ) -> Iterator[UnifiedEvent]:
        """
        Normalize an iterable of raw rows, yielding valid UnifiedEvents.

        Skipped rows are logged but do not interrupt iteration.
        """
        for row in rows:
            event = self.normalize(row)
            if event is not None:
                yield event

    @property
    def stats(self) -> dict[str, int]:
        """Return a snapshot of normalization counters."""
        return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset all counters (useful between dataset files)."""
        for key in self._stats:
            self._stats[key] = 0

    def reset_dedup_cache(self) -> None:
        """Clear the deduplication cache (use between dataset files)."""
        self._seen_keys.clear()

    # ------------------------------------------------------------------
    # Internal build logic
    # ------------------------------------------------------------------

    def _build_event(self, row: dict[str, Any]) -> UnifiedEvent:
        """
        Construct a UnifiedEvent from a normalized parser row dict.

        Raises:
            pydantic.ValidationError: If any required field is invalid.
        """
        # --- Timestamp ---
        ts = row.get("timestamp")
        if isinstance(ts, datetime):
            timestamp = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        elif isinstance(ts, (int, float)):
            timestamp = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        elif isinstance(ts, str):
            timestamp = datetime.fromisoformat(ts)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = datetime.now(tz=timezone.utc)

        # --- Source ---
        source = SourceInfo(
            ip=str(row["src_ip"]).strip(),
            port=_to_optional_int(row.get("src_port")),
            hostname=row.get("src_hostname") or None,
            user=row.get("src_user") or None,
        )

        # --- Destination ---
        destination = DestinationInfo(
            ip=str(row["dst_ip"]).strip(),
            port=_to_optional_int(row.get("dst_port")),
            hostname=row.get("dst_hostname") or None,
            service=_infer_service(row.get("dst_port")),
        )

        # --- Network ---
        network = NetworkInfo(
            protocol=_to_protocol(row.get("protocol", "TCP")),
            bytes_sent=row.get("bytes_sent", 0),
            bytes_received=row.get("bytes_received", 0),
            duration_ms=row.get("duration_ms", 0.0),
            packets_sent=row.get("packets_sent", 0),
            packets_received=row.get("packets_received", 0),
            flow_bytes_per_second=row.get("flow_bytes_per_second", 0.0),
            flow_packets_per_second=row.get("flow_packets_per_second", 0.0),
            fwd_packet_length_mean=row.get("fwd_packet_length_mean", 0.0),
            bwd_packet_length_mean=row.get("bwd_packet_length_mean", 0.0),
            flow_iat_mean=row.get("flow_iat_mean", 0.0),
            active_mean=row.get("active_mean", 0.0),
            idle_mean=row.get("idle_mean", 0.0),
        )

        # --- Metadata ---
        attack_label_raw = row.get("attack_label", AttackLabel.BENIGN)
        if isinstance(attack_label_raw, str):
            try:
                attack_label = AttackLabel(attack_label_raw)
            except ValueError:
                attack_label = AttackLabel.UNKNOWN
        else:
            attack_label = attack_label_raw

        metadata = EventMetadata(
            dataset_source=_to_dataset_source(row.get("dataset_source", "SYNTHETIC")),
            original_label=str(row.get("original_label", "BENIGN")),
            attack_label=attack_label,
            is_attack=bool(row.get("is_attack", False)),
            collector=self._collector,
            raw_features={},   # keep payload lean — raw features not stored
        )

        return UnifiedEvent(
            timestamp=timestamp,
            event_type=EventType.NETWORK_FLOW,
            source=source,
            destination=destination,
            network=network,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Well-known port → service name mapping
_PORT_SERVICE_MAP: dict[int, str] = {
    20:   "ftp-data",
    21:   "ftp",
    22:   "ssh",
    23:   "telnet",
    25:   "smtp",
    53:   "dns",
    67:   "dhcp",
    68:   "dhcp",
    80:   "http",
    110:  "pop3",
    119:  "nntp",
    123:  "ntp",
    143:  "imap",
    161:  "snmp",
    179:  "bgp",
    389:  "ldap",
    443:  "https",
    445:  "smb",
    465:  "smtps",
    514:  "syslog",
    587:  "smtp-submission",
    636:  "ldaps",
    993:  "imaps",
    995:  "pop3s",
    1433: "mssql",
    1521: "oracle",
    3306: "mysql",
    3389: "rdp",
    5432: "postgresql",
    5900: "vnc",
    6379: "redis",
    7474: "neo4j-http",
    7687: "neo4j-bolt",
    8080: "http-alt",
    8443: "https-alt",
    9092: "kafka",
    27017: "mongodb",
}


def _infer_service(port: Any) -> str | None:
    """Return known service name for well-known ports."""
    if port is None:
        return None
    try:
        p = int(float(str(port)))
        return _PORT_SERVICE_MAP.get(p)
    except (ValueError, TypeError):
        return None


def _to_optional_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return int(f)
    except (ValueError, TypeError):
        return None
