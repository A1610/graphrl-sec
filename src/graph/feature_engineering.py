"""
Feature engineering for graph nodes and edges.

Extracts fixed-dimension feature vectors from network entities and events.
All feature vectors are NumPy float32 arrays — ready for PyG tensor conversion.

Node features (per type):
  Host / ExternalIP : [degree_norm, bytes_sent_norm, bytes_recv_norm,
                       packets_norm, unique_dsts_norm, is_internal,
                       attack_score, last_seen_norm]
  Service           : [port_norm, is_well_known, is_privileged, protocol_onehot_2]
  Domain            : [label_count, digit_ratio, length_norm, entropy_norm]

Edge features (all types, dim=12):
  [timestamp_norm, duration_norm, bytes_sent_norm, bytes_recv_norm,
   packets_sent_norm, packets_recv_norm, protocol_tcp, protocol_udp,
   protocol_icmp, protocol_other, port_norm, is_attack]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from src.graph.node_registry import Node
from src.ingestion.schemas import Protocol, UnifiedEvent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EDGE_FEATURE_DIM = 12
_MAX_BYTES       = 1_000_000.0    # 1MB normalization cap
_MAX_PACKETS     = 10_000.0
_MAX_DURATION_MS = 300_000.0      # 5 minutes
_MAX_PORT        = 65535.0
_MAX_DEGREE      = 10_000.0
_MAX_LABEL_LEN   = 253.0          # max DNS label length


# ---------------------------------------------------------------------------
# Node state accumulators (updated as events arrive)
# ---------------------------------------------------------------------------


@dataclass
class NodeStats:
    """Running statistics accumulated per node as events are processed."""

    degree:        int   = 0
    bytes_sent:    int   = 0
    bytes_recv:    int   = 0
    packets_sent:  int   = 0
    packets_recv:  int   = 0
    unique_dsts:   set[int] = field(default_factory=set)
    attack_count:  int   = 0
    event_count:   int   = 0
    last_seen_ts:  float = 0.0    # Unix timestamp

    def update(self, event: UnifiedEvent, dst_node_id: int) -> None:
        self.degree        += 1
        self.bytes_sent    += event.network.bytes_sent
        self.bytes_recv    += event.network.bytes_received
        self.packets_sent  += event.network.packets_sent
        self.packets_recv  += event.network.packets_received
        self.unique_dsts.add(dst_node_id)
        self.event_count   += 1
        self.last_seen_ts   = max(self.last_seen_ts, event.timestamp.timestamp())
        if event.metadata.is_attack:
            self.attack_count += 1


# ---------------------------------------------------------------------------
# Node feature extraction
# ---------------------------------------------------------------------------


def extract_host_features(
    node: Node,
    stats: NodeStats | None,
    window_start_ts: float,
    window_end_ts: float,
    is_internal: bool,
) -> npt.NDArray[np.float32]:
    """
    Extract 8-dimensional feature vector for Host / ExternalIP nodes.

    Features:
        [0] degree_norm          — normalized connection degree
        [1] bytes_sent_norm      — normalized total bytes sent
        [2] bytes_recv_norm      — normalized total bytes received
        [3] packets_norm         — normalized total packets
        [4] unique_dsts_norm     — normalized unique destination count
        [5] is_internal          — 1.0 if internal IP, 0.0 if external
        [6] attack_score         — fraction of events flagged as attacks
        [7] last_seen_norm       — normalized time since last seen in window
    """
    s = stats or NodeStats()
    window_duration = max(window_end_ts - window_start_ts, 1.0)

    degree_norm         = min(s.degree / _MAX_DEGREE, 1.0)
    bytes_sent_norm     = min(s.bytes_sent / _MAX_BYTES, 1.0)
    bytes_recv_norm     = min(s.bytes_recv / _MAX_BYTES, 1.0)
    packets_norm        = min((s.packets_sent + s.packets_recv) / _MAX_PACKETS, 1.0)
    unique_dsts_norm    = min(len(s.unique_dsts) / _MAX_DEGREE, 1.0)
    is_internal_f       = 1.0 if is_internal else 0.0
    attack_score        = s.attack_count / max(s.event_count, 1)
    time_since_seen     = window_end_ts - s.last_seen_ts if s.last_seen_ts > 0 else window_duration
    last_seen_norm      = 1.0 - min(time_since_seen / window_duration, 1.0)

    return np.array([
        degree_norm, bytes_sent_norm, bytes_recv_norm, packets_norm,
        unique_dsts_norm, is_internal_f, attack_score, last_seen_norm,
    ], dtype=np.float32)


def extract_service_features(port: int, protocol: str) -> npt.NDArray[np.float32]:
    """
    Extract 4-dimensional feature vector for Service nodes.

    Features:
        [0] port_norm       — port / 65535
        [1] is_well_known   — 1.0 if IANA system port (≤ 1023)
        [2] is_registered   — 1.0 if IANA registered port (≤ 49151); 0 = ephemeral
        [3] protocol_enc    — 0=TCP, 0.5=UDP, 1.0=ICMP, 0.75=OTHER
    """
    port_norm     = port / _MAX_PORT
    is_well_known  = 1.0 if port <= 1023  else 0.0
    is_registered  = 1.0 if port <= 49151 else 0.0
    proto_enc = {"TCP": 0.0, "UDP": 0.5, "ICMP": 1.0}.get(protocol.upper(), 0.75)
    return np.array([port_norm, is_well_known, is_registered, proto_enc], dtype=np.float32)


def extract_domain_features(domain: str) -> npt.NDArray[np.float32]:
    """
    Extract 4-dimensional feature vector for Domain nodes.

    Features:
        [0] label_count_norm  — number of DNS labels (dots + 1) / 10
        [1] digit_ratio       — fraction of chars that are digits
        [2] length_norm       — length / max_label_len
        [3] entropy_norm      — Shannon entropy / log2(36)
    """
    if not domain:
        return np.zeros(4, dtype=np.float32)

    label_count = domain.count(".") + 1
    label_count_norm = min(label_count / 10.0, 1.0)
    digit_ratio = sum(c.isdigit() for c in domain) / max(len(domain), 1)
    length_norm = min(len(domain) / _MAX_LABEL_LEN, 1.0)
    entropy = _string_entropy(domain)
    max_entropy = math.log2(36)  # 26 letters + 10 digits
    entropy_norm = min(entropy / max_entropy, 1.0) if max_entropy > 0 else 0.0

    return np.array([label_count_norm, digit_ratio, length_norm, entropy_norm], dtype=np.float32)


# ---------------------------------------------------------------------------
# Edge feature extraction
# ---------------------------------------------------------------------------


def extract_edge_features(
    event: UnifiedEvent,
    window_start_ts: float,
    window_end_ts: float,
) -> npt.NDArray[np.float32]:
    """
    Extract 12-dimensional feature vector for any edge type.

    Features:
        [0]  timestamp_norm       — event time within window [0, 1]
        [1]  duration_norm        — flow duration / max_duration
        [2]  bytes_sent_norm      — bytes sent / max_bytes
        [3]  bytes_recv_norm      — bytes received / max_bytes
        [4]  packets_sent_norm    — packets sent / max_packets
        [5]  packets_recv_norm    — packets received / max_packets
        [6]  protocol_tcp         — 1 if TCP else 0
        [7]  protocol_udp         — 1 if UDP else 0
        [8]  protocol_icmp        — 1 if ICMP else 0
        [9]  protocol_other       — 1 if OTHER else 0
        [10] port_norm            — destination port / 65535
        [11] is_attack            — 1.0 if event is attack else 0.0
    """
    ts = event.timestamp.timestamp()
    window_duration = max(window_end_ts - window_start_ts, 1.0)
    timestamp_norm = max(0.0, min((ts - window_start_ts) / window_duration, 1.0))

    duration_norm     = min(event.network.duration_ms / _MAX_DURATION_MS, 1.0)
    bytes_sent_norm   = min(event.network.bytes_sent / _MAX_BYTES, 1.0)
    bytes_recv_norm   = min(event.network.bytes_received / _MAX_BYTES, 1.0)
    packets_sent_norm = min(event.network.packets_sent / _MAX_PACKETS, 1.0)
    packets_recv_norm = min(event.network.packets_received / _MAX_PACKETS, 1.0)

    proto = event.network.protocol
    proto_tcp   = 1.0 if proto == Protocol.TCP   else 0.0
    proto_udp   = 1.0 if proto == Protocol.UDP   else 0.0
    proto_icmp  = 1.0 if proto == Protocol.ICMP  else 0.0
    proto_other = 1.0 if proto == Protocol.OTHER else 0.0

    port_norm  = (event.destination.port or 0) / _MAX_PORT
    is_attack  = 1.0 if event.metadata.is_attack else 0.0

    return np.array([
        timestamp_norm, duration_norm, bytes_sent_norm, bytes_recv_norm,
        packets_sent_norm, packets_recv_norm,
        proto_tcp, proto_udp, proto_icmp, proto_other,
        port_norm, is_attack,
    ], dtype=np.float32)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _string_entropy(s: str) -> float:
    """Shannon entropy of a string."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    n = len(s)
    return -sum((count / n) * math.log2(count / n) for count in freq.values())
