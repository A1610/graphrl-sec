"""
Unified Event Schema for GraphRL-Sec ingestion pipeline.

All data sources (CICIDS2017, UNSW-NB15, LANL, real-time syslog)
are normalized into UnifiedEvent before entering the system.
This is the single source of truth for data entering GraphRL-Sec.
"""

from __future__ import annotations

import hashlib
import ipaddress
import math
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Top-level classification of the network event."""

    NETWORK_FLOW = "network_flow"
    AUTH = "auth"
    DNS = "dns"
    PROCESS = "process"
    FILE = "file"


class Protocol(str, Enum):
    """Standardized transport-layer protocols."""

    TCP = "TCP"
    UDP = "UDP"
    ICMP = "ICMP"
    OTHER = "OTHER"


class AttackLabel(str, Enum):
    """Unified attack category labels across all datasets."""

    BENIGN = "BENIGN"
    # CICIDS2017 categories
    DDOS = "DDoS"
    PORT_SCAN = "PortScan"
    BOT = "Bot"
    INFILTRATION = "Infiltration"
    BRUTE_FORCE = "BruteForce"
    SQL_INJECTION = "SQLInjection"
    XSS = "XSS"
    FTP_PATATOR = "FTP-Patator"
    SSH_PATATOR = "SSH-Patator"
    DOS_SLOWLORIS = "DoS-Slowloris"
    DOS_SLOWHTTPTEST = "DoS-SlowHTTPTest"
    DOS_HULK = "DoS-Hulk"
    DOS_GOLDENEYE = "DoS-GoldenEye"
    HEARTBLEED = "Heartbleed"
    # UNSW-NB15 categories
    FUZZERS = "Fuzzers"
    ANALYSIS = "Analysis"
    BACKDOORS = "Backdoors"
    DOS = "DoS"
    EXPLOITS = "Exploits"
    GENERIC = "Generic"
    RECONNAISSANCE = "Reconnaissance"
    SHELLCODE = "Shellcode"
    WORMS = "Worms"
    # LANL categories
    RED_TEAM = "RedTeam"
    LATERAL_MOVEMENT = "LateralMovement"
    # Generic unknown
    UNKNOWN = "UNKNOWN"


class DatasetSource(str, Enum):
    """Which dataset this event originates from."""

    CICIDS2017 = "CICIDS2017"
    UNSW_NB15 = "UNSW-NB15"
    LANL = "LANL"
    SYNTHETIC = "SYNTHETIC"
    REALTIME = "REALTIME"


class CollectorMode(str, Enum):
    """How the event was collected."""

    BATCH = "batch"
    STREAMING = "streaming"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class SourceInfo(BaseModel):
    """Source endpoint of the network event."""

    model_config = {"frozen": True}

    ip: str
    port: int | None = Field(default=None, ge=0, le=65535)
    hostname: str | None = None
    user: str | None = None

    @field_validator("ip", mode="before")
    @classmethod
    def validate_ip(cls, v: Any) -> str:
        try:
            ipaddress.ip_address(str(v).strip())
            return str(v).strip()
        except ValueError as exc:
            raise ValueError(f"Invalid source IP address: {v!r}") from exc


class DestinationInfo(BaseModel):
    """Destination endpoint of the network event."""

    model_config = {"frozen": True}

    ip: str
    port: int | None = Field(default=None, ge=0, le=65535)
    hostname: str | None = None
    service: str | None = None

    @field_validator("ip", mode="before")
    @classmethod
    def validate_ip(cls, v: Any) -> str:
        try:
            ipaddress.ip_address(str(v).strip())
            return str(v).strip()
        except ValueError as exc:
            raise ValueError(f"Invalid destination IP address: {v!r}") from exc


class NetworkInfo(BaseModel):
    """Network-layer statistics for the flow."""

    model_config = {"frozen": True}

    protocol: Protocol = Protocol.TCP
    bytes_sent: int = Field(default=0, ge=0)
    bytes_received: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0.0, ge=0.0)
    packets_sent: int = Field(default=0, ge=0)
    packets_received: int = Field(default=0, ge=0)

    # Derived flow features used by T-HetGAT
    flow_bytes_per_second: float = Field(default=0.0, ge=0.0)
    flow_packets_per_second: float = Field(default=0.0, ge=0.0)
    fwd_packet_length_mean: float = Field(default=0.0, ge=0.0)
    bwd_packet_length_mean: float = Field(default=0.0, ge=0.0)
    flow_iat_mean: float = Field(default=0.0, ge=0.0)      # inter-arrival time
    active_mean: float = Field(default=0.0, ge=0.0)
    idle_mean: float = Field(default=0.0, ge=0.0)

    @field_validator(
        "duration_ms",
        "flow_bytes_per_second",
        "flow_packets_per_second",
        "fwd_packet_length_mean",
        "bwd_packet_length_mean",
        "flow_iat_mean",
        "active_mean",
        "idle_mean",
        mode="before",
    )
    @classmethod
    def sanitize_float(cls, v: Any) -> float:
        """Replace NaN / Infinity with 0.0 — common in CICIDS2017."""
        if v is None:
            return 0.0
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return max(0.0, f)

    @field_validator("bytes_sent", "bytes_received", "packets_sent", "packets_received", mode="before")
    @classmethod
    def sanitize_int(cls, v: Any) -> int:
        """Replace NaN / negative integers with 0."""
        if v is None:
            return 0
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return 0
            return max(0, int(f))
        except (ValueError, TypeError):
            return 0


class EventMetadata(BaseModel):
    """Provenance and labeling metadata."""

    model_config = {"frozen": True}

    dataset_source: DatasetSource
    original_label: str = "BENIGN"
    attack_label: AttackLabel = AttackLabel.BENIGN
    is_attack: bool = False
    collector: CollectorMode = CollectorMode.BATCH
    # Extra dataset-specific fields preserved for debugging
    raw_features: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------


class UnifiedEvent(BaseModel):
    """
    Canonical network event schema used throughout GraphRL-Sec.

    All parsers must produce UnifiedEvent objects. Downstream modules
    (graph constructor, T-HetGAT, DRL agent) consume only this type.
    """

    model_config = {"frozen": True}

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime
    event_type: EventType = EventType.NETWORK_FLOW
    source: SourceInfo
    destination: DestinationInfo
    network: NetworkInfo
    metadata: EventMetadata

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        """Normalize all timestamps to UTC-aware datetime."""
        if isinstance(v, str):
            # Python 3.10 does not support 'Z' suffix — replace with +00:00
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime):
            if v.tzinfo is None:
                # Assume UTC if no timezone
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        raise ValueError(f"Cannot parse timestamp: {v!r}")

    def dedup_key(self) -> str:
        """
        Deterministic deduplication key.
        Two events with the same (src_ip, dst_ip, dst_port, timestamp_sec, protocol)
        are considered duplicates.
        """
        raw = (
            f"{self.source.ip}|{self.destination.ip}|"
            f"{self.destination.port}|"
            f"{int(self.timestamp.timestamp())}|"
            f"{self.network.protocol}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_kafka_payload(self) -> bytes:
        """Serialize to UTF-8 JSON bytes for Kafka publishing."""
        return self.model_dump_json(indent=None).encode("utf-8")

    @classmethod
    def from_kafka_payload(cls, data: bytes) -> UnifiedEvent:
        """Deserialize from Kafka message bytes."""
        return cls.model_validate_json(data.decode("utf-8"))
