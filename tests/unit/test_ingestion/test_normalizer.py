"""
Unit tests for src/ingestion/normalizer.py
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.ingestion.normalizer import EventNormalizer, _infer_service, _to_optional_int
from src.ingestion.schemas import AttackLabel, CollectorMode, Protocol, UnifiedEvent


@pytest.fixture()
def base_row() -> dict:
    return {
        "src_ip": "192.168.1.10", "src_port": 54321,
        "dst_ip": "10.0.0.1",    "dst_port": 443,
        "protocol": "TCP", "duration_ms": 150.0,
        "bytes_sent": 512, "bytes_received": 1024,
        "packets_sent": 5, "packets_received": 10,
        "flow_bytes_per_second": 10240.0,
        "flow_packets_per_second": 100.0,
        "fwd_packet_length_mean": 102.4,
        "bwd_packet_length_mean": 102.4,
        "flow_iat_mean": 10.0,
        "active_mean": 0.0,
        "idle_mean": 0.0,
        "original_label": "DDoS",
        "attack_label": "DDoS",
        "is_attack": True,
        "timestamp": datetime(2017, 7, 7, 12, 0, 0, tzinfo=timezone.utc),
        "dataset_source": "CICIDS2017",
    }


@pytest.fixture()
def normalizer() -> EventNormalizer:
    return EventNormalizer(deduplicate=False)


# ---------------------------------------------------------------------------
# Core normalization
# ---------------------------------------------------------------------------


class TestEventNormalizerCore:
    def test_valid_row_produces_event(self, normalizer: EventNormalizer, base_row: dict) -> None:
        event = normalizer.normalize(base_row)
        assert event is not None
        assert isinstance(event, UnifiedEvent)

    def test_source_ip_preserved(self, normalizer: EventNormalizer, base_row: dict) -> None:
        event = normalizer.normalize(base_row)
        assert event is not None
        assert event.source.ip == "192.168.1.10"

    def test_destination_port_preserved(self, normalizer: EventNormalizer, base_row: dict) -> None:
        event = normalizer.normalize(base_row)
        assert event is not None
        assert event.destination.port == 443

    def test_attack_label_set(self, normalizer: EventNormalizer, base_row: dict) -> None:
        event = normalizer.normalize(base_row)
        assert event is not None
        assert event.metadata.attack_label == AttackLabel.DDOS
        assert event.metadata.is_attack is True

    def test_collector_mode_set(self, base_row: dict) -> None:
        n = EventNormalizer(collector=CollectorMode.STREAMING, deduplicate=False)
        event = n.normalize(base_row)
        assert event is not None
        assert event.metadata.collector == CollectorMode.STREAMING

    def test_invalid_src_ip_returns_none(self, normalizer: EventNormalizer, base_row: dict) -> None:
        base_row["src_ip"] = "999.999.999.999"
        assert normalizer.normalize(base_row) is None

    def test_invalid_dst_ip_returns_none(self, normalizer: EventNormalizer, base_row: dict) -> None:
        base_row["dst_ip"] = "not-an-ip"
        assert normalizer.normalize(base_row) is None

    def test_stats_incremented_on_success(self, normalizer: EventNormalizer, base_row: dict) -> None:
        normalizer.normalize(base_row)
        assert normalizer.stats["total"] == 1
        assert normalizer.stats["normalized"] == 1

    def test_stats_incremented_on_skip(self, normalizer: EventNormalizer, base_row: dict) -> None:
        base_row["src_ip"] = "bad-ip"
        normalizer.normalize(base_row)
        assert normalizer.stats["skipped_validation"] == 1

    def test_reset_stats(self, normalizer: EventNormalizer, base_row: dict) -> None:
        normalizer.normalize(base_row)
        normalizer.reset_stats()
        assert normalizer.stats["total"] == 0

    def test_timestamp_naive_gets_utc(self, normalizer: EventNormalizer, base_row: dict) -> None:
        base_row["timestamp"] = datetime(2017, 7, 7, 12, 0, 0)  # naive
        event = normalizer.normalize(base_row)
        assert event is not None
        assert event.timestamp.tzinfo == timezone.utc

    def test_timestamp_as_unix_epoch(self, normalizer: EventNormalizer, base_row: dict) -> None:
        base_row["timestamp"] = 1499428800.0  # Unix timestamp
        event = normalizer.normalize(base_row)
        assert event is not None
        assert event.timestamp.year == 2017

    def test_protocol_tcp_normalized(self, normalizer: EventNormalizer, base_row: dict) -> None:
        event = normalizer.normalize(base_row)
        assert event is not None
        assert event.network.protocol == Protocol.TCP

    def test_protocol_number_6_normalized_to_tcp(self, normalizer: EventNormalizer, base_row: dict) -> None:
        base_row["protocol"] = "6"
        event = normalizer.normalize(base_row)
        assert event is not None
        assert event.network.protocol == Protocol.TCP

    def test_unknown_protocol_becomes_other(self, normalizer: EventNormalizer, base_row: dict) -> None:
        base_row["protocol"] = "ospf"
        event = normalizer.normalize(base_row)
        assert event is not None
        assert event.network.protocol == Protocol.OTHER


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_duplicate_skipped(self, base_row: dict) -> None:
        n = EventNormalizer(deduplicate=True)
        e1 = n.normalize(base_row)
        e2 = n.normalize(base_row)
        assert e1 is not None
        assert e2 is None
        assert n.stats["skipped_duplicate"] == 1

    def test_different_events_not_deduplicated(self, base_row: dict) -> None:
        n = EventNormalizer(deduplicate=True)
        row2 = dict(base_row, src_ip="192.168.1.20")
        e1 = n.normalize(base_row)
        e2 = n.normalize(row2)
        assert e1 is not None
        assert e2 is not None

    def test_dedup_disabled_allows_duplicates(self, base_row: dict) -> None:
        n = EventNormalizer(deduplicate=False)
        e1 = n.normalize(base_row)
        e2 = n.normalize(base_row)
        assert e1 is not None
        assert e2 is not None

    def test_reset_dedup_cache_allows_resend(self, base_row: dict) -> None:
        n = EventNormalizer(deduplicate=True)
        n.normalize(base_row)
        n.reset_dedup_cache()
        e2 = n.normalize(base_row)
        assert e2 is not None


# ---------------------------------------------------------------------------
# normalize_batch
# ---------------------------------------------------------------------------


class TestNormalizeBatch:
    def test_batch_yields_valid_events(self, normalizer: EventNormalizer, base_row: dict) -> None:
        rows = [base_row, dict(base_row, src_ip="10.20.30.40")]
        events = list(normalizer.normalize_batch(iter(rows)))
        assert len(events) == 2

    def test_batch_skips_invalid(self, normalizer: EventNormalizer, base_row: dict) -> None:
        rows = [base_row, dict(base_row, src_ip="bad-ip")]
        events = list(normalizer.normalize_batch(iter(rows)))
        assert len(events) == 1


# ---------------------------------------------------------------------------
# Service inference & helpers
# ---------------------------------------------------------------------------


class TestInferService:
    def test_port_80_is_http(self) -> None:
        assert _infer_service(80) == "http"

    def test_port_443_is_https(self) -> None:
        assert _infer_service(443) == "https"

    def test_port_22_is_ssh(self) -> None:
        assert _infer_service(22) == "ssh"

    def test_port_53_is_dns(self) -> None:
        assert _infer_service(53) == "dns"

    def test_unknown_port_returns_none(self) -> None:
        assert _infer_service(54321) is None

    def test_none_port_returns_none(self) -> None:
        assert _infer_service(None) is None

    def test_string_port(self) -> None:
        assert _infer_service("3306") == "mysql"


class TestToOptionalInt:
    def test_valid_int(self) -> None:
        assert _to_optional_int(42) == 42

    def test_float_truncated(self) -> None:
        assert _to_optional_int(3.9) == 3

    def test_none_returns_none(self) -> None:
        assert _to_optional_int(None) is None

    def test_inf_returns_none(self) -> None:
        assert _to_optional_int(float("inf")) is None

    def test_nan_returns_none(self) -> None:
        assert _to_optional_int(float("nan")) is None
