"""
Unit tests for src/ingestion/schemas.py

Tests: UnifiedEvent validation, field sanitization, serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_event() -> UnifiedEvent:
    return UnifiedEvent(
        timestamp=datetime(2017, 7, 7, 12, 0, 0, tzinfo=timezone.utc),
        event_type=EventType.NETWORK_FLOW,
        source=SourceInfo(ip="192.168.1.10", port=54321),
        destination=DestinationInfo(ip="10.0.0.1", port=80),
        network=NetworkInfo(
            protocol=Protocol.TCP,
            bytes_sent=512,
            bytes_received=1024,
            duration_ms=150.0,
            packets_sent=5,
            packets_received=10,
        ),
        metadata=EventMetadata(
            dataset_source=DatasetSource.CICIDS2017,
            original_label="DDoS",
            attack_label=AttackLabel.DDOS,
            is_attack=True,
            collector=CollectorMode.BATCH,
        ),
    )


# ---------------------------------------------------------------------------
# SourceInfo validation
# ---------------------------------------------------------------------------


class TestSourceInfo:
    def test_valid_ipv4(self) -> None:
        s = SourceInfo(ip="192.168.1.1", port=1234)
        assert s.ip == "192.168.1.1"
        assert s.port == 1234

    def test_valid_ip_no_port(self) -> None:
        s = SourceInfo(ip="10.0.0.1")
        assert s.port is None

    def test_strips_whitespace_from_ip(self) -> None:
        s = SourceInfo(ip="  192.168.1.1  ")
        assert s.ip == "192.168.1.1"

    def test_invalid_ip_raises(self) -> None:
        with pytest.raises(ValidationError, match="Invalid source IP"):
            SourceInfo(ip="999.999.999.999")

    def test_empty_ip_raises(self) -> None:
        with pytest.raises(ValidationError):
            SourceInfo(ip="")

    def test_port_below_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            SourceInfo(ip="192.168.1.1", port=-1)

    def test_port_above_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            SourceInfo(ip="192.168.1.1", port=65536)

    def test_port_max_valid(self) -> None:
        s = SourceInfo(ip="10.0.0.1", port=65535)
        assert s.port == 65535


# ---------------------------------------------------------------------------
# DestinationInfo validation
# ---------------------------------------------------------------------------


class TestDestinationInfo:
    def test_valid(self) -> None:
        d = DestinationInfo(ip="8.8.8.8", port=53, service="dns")
        assert d.ip == "8.8.8.8"
        assert d.service == "dns"

    def test_invalid_ip_raises(self) -> None:
        with pytest.raises(ValidationError, match="Invalid destination IP"):
            DestinationInfo(ip="not-an-ip")


# ---------------------------------------------------------------------------
# NetworkInfo validation and NaN/Inf sanitization
# ---------------------------------------------------------------------------


class TestNetworkInfo:
    def test_defaults_are_zero(self) -> None:
        n = NetworkInfo()
        assert n.bytes_sent == 0
        assert n.duration_ms == 0.0
        assert n.protocol == Protocol.TCP

    def test_inf_sanitized_to_zero(self) -> None:
        n = NetworkInfo(duration_ms=float("inf"))
        assert n.duration_ms == 0.0

    def test_nan_sanitized_to_zero(self) -> None:
        n = NetworkInfo(flow_bytes_per_second=float("nan"))
        assert n.flow_bytes_per_second == 0.0

    def test_negative_float_sanitized_to_zero(self) -> None:
        n = NetworkInfo(duration_ms=-10.0)
        assert n.duration_ms == 0.0

    def test_negative_int_sanitized_to_zero(self) -> None:
        n = NetworkInfo(bytes_sent=-100)
        assert n.bytes_sent == 0

    def test_none_float_sanitized_to_zero(self) -> None:
        n = NetworkInfo(flow_iat_mean=None)  # type: ignore[arg-type]
        assert n.flow_iat_mean == 0.0

    def test_valid_values_preserved(self) -> None:
        n = NetworkInfo(
            protocol=Protocol.UDP,
            bytes_sent=100,
            duration_ms=50.5,
            packets_sent=3,
        )
        assert n.protocol == Protocol.UDP
        assert n.bytes_sent == 100
        assert n.duration_ms == 50.5


# ---------------------------------------------------------------------------
# UnifiedEvent validation
# ---------------------------------------------------------------------------


class TestUnifiedEvent:
    def test_valid_event_creates_uuid(self, valid_event: UnifiedEvent) -> None:
        assert len(valid_event.event_id) == 36
        assert valid_event.event_id.count("-") == 4

    def test_timestamp_without_tz_gets_utc(self) -> None:
        e = UnifiedEvent(
            timestamp=datetime(2017, 7, 7, 12, 0, 0),  # naive datetime
            source=SourceInfo(ip="1.1.1.1"),
            destination=DestinationInfo(ip="2.2.2.2"),
            network=NetworkInfo(),
            metadata=EventMetadata(
                dataset_source=DatasetSource.CICIDS2017,
                collector=CollectorMode.BATCH,
            ),
        )
        assert e.timestamp.tzinfo is not None
        assert e.timestamp.tzinfo == timezone.utc

    def test_timestamp_iso_string_parsed(self) -> None:
        e = UnifiedEvent(
            timestamp="2017-07-07T12:00:00+00:00",  # type: ignore[arg-type]
            source=SourceInfo(ip="1.1.1.1"),
            destination=DestinationInfo(ip="2.2.2.2"),
            network=NetworkInfo(),
            metadata=EventMetadata(
                dataset_source=DatasetSource.CICIDS2017,
                collector=CollectorMode.BATCH,
            ),
        )
        assert e.timestamp.year == 2017

    def test_event_is_immutable(self, valid_event: UnifiedEvent) -> None:
        with pytest.raises(ValidationError):
            valid_event.event_id = "new-id"  # type: ignore[misc]

    def test_dedup_key_is_deterministic(self, valid_event: UnifiedEvent) -> None:
        key1 = valid_event.dedup_key()
        key2 = valid_event.dedup_key()
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex

    def test_dedup_key_differs_for_different_events(self, valid_event: UnifiedEvent) -> None:
        other = UnifiedEvent(
            timestamp=valid_event.timestamp,
            source=SourceInfo(ip="10.10.10.10"),  # different IP
            destination=valid_event.destination,
            network=valid_event.network,
            metadata=valid_event.metadata,
        )
        assert valid_event.dedup_key() != other.dedup_key()

    def test_kafka_round_trip(self, valid_event: UnifiedEvent) -> None:
        payload = valid_event.to_kafka_payload()
        assert isinstance(payload, bytes)
        restored = UnifiedEvent.from_kafka_payload(payload)
        assert restored.event_id == valid_event.event_id
        assert restored.source.ip == valid_event.source.ip
        assert restored.metadata.attack_label == valid_event.metadata.attack_label

    def test_kafka_payload_is_valid_json(self, valid_event: UnifiedEvent) -> None:
        import json
        payload = valid_event.to_kafka_payload()
        data = json.loads(payload)
        assert "event_id" in data
        assert "source" in data
        assert "destination" in data

    def test_two_events_have_different_ids(self, valid_event: UnifiedEvent) -> None:
        other = UnifiedEvent(
            timestamp=valid_event.timestamp,
            source=valid_event.source,
            destination=valid_event.destination,
            network=valid_event.network,
            metadata=valid_event.metadata,
        )
        assert valid_event.event_id != other.event_id
