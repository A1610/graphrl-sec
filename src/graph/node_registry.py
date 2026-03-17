"""
Node Registry — maps network entities to unique integer node IDs.

Maintains a thread-safe registry of all nodes observed in the network graph.
Classifies IPs as internal (Host) or external (ExternalIP) based on RFC 1918
private address ranges.

Node types:
  - Host:       Internal IP (10.x, 172.16-31.x, 192.168.x)
  - ExternalIP: Public IP not in internal ranges
  - Service:    Network service identified by port + protocol
  - Domain:     DNS domain name
  - User:       Authenticated user account
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from src.graph.config import GraphConfig, graph_settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    HOST        = "host"
    EXTERNAL_IP = "external_ip"
    SERVICE     = "service"
    DOMAIN      = "domain"
    USER        = "user"


# ---------------------------------------------------------------------------
# Node data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    """Immutable node descriptor."""

    node_id:    int
    node_type:  NodeType
    entity_key: str       # canonical string key (e.g. "192.168.1.1", "http:80/TCP")
    attributes: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __repr__(self) -> str:
        return f"Node(id={self.node_id}, type={self.node_type.value}, key={self.entity_key!r})"


# ---------------------------------------------------------------------------
# Node Registry
# ---------------------------------------------------------------------------


class NodeRegistry:
    """
    Thread-safe registry mapping entity strings to Node objects.

    Each unique entity gets a stable integer ID for the lifetime of the registry.
    The registry is keyed on (node_type, entity_key) pairs.

    Thread safety: a single RLock protects all mutations.
    The registry can be shared across threads for streaming ingestion.
    """

    def __init__(self, config: GraphConfig | None = None) -> None:
        self._config = config or graph_settings
        self._lock = threading.RLock()

        # (NodeType, entity_key) -> Node
        self._nodes: dict[tuple[NodeType, str], Node] = {}
        # node_id -> Node (reverse lookup)
        self._id_to_node: dict[int, Node] = {}
        self._next_id: int = 0

        # Per-type counters for fast stats
        self._type_counts: dict[NodeType, int] = dict.fromkeys(NodeType, 0)

    # ------------------------------------------------------------------
    # Node creation / retrieval
    # ------------------------------------------------------------------

    def get_or_create(
        self,
        node_type: NodeType,
        entity_key: str,
        attributes: dict[str, Any] | None = None,
    ) -> Node:
        """
        Return the existing Node for this entity, or create it.

        Args:
            node_type:   The type of node.
            entity_key:  Canonical identifier string.
            attributes:  Optional metadata (not used for equality).

        Returns:
            The Node object (new or existing).
        """
        key = (node_type, entity_key)
        with self._lock:
            if key in self._nodes:
                return self._nodes[key]
            node = Node(
                node_id=self._next_id,
                node_type=node_type,
                entity_key=entity_key,
                attributes=attributes or {},
            )
            self._nodes[key] = node
            self._id_to_node[self._next_id] = node
            self._next_id += 1
            self._type_counts[node_type] += 1
            return node

    def get_node(self, node_id: int) -> Node | None:
        """Return Node by integer ID, or None if not found."""
        with self._lock:
            return self._id_to_node.get(node_id)

    def get_by_key(self, node_type: NodeType, entity_key: str) -> Node | None:
        """Return Node by (type, key), or None if not found."""
        with self._lock:
            return self._nodes.get((node_type, entity_key))

    # ------------------------------------------------------------------
    # IP-specific helpers
    # ------------------------------------------------------------------

    def get_or_create_ip(self, ip: str) -> Node:
        """
        Create or retrieve an IP node, auto-classifying as Host or ExternalIP.

        Internal IPs (RFC 1918 + loopback) become Host nodes.
        All other IPs become ExternalIP nodes.
        """
        node_type = self._classify_ip(ip)
        return self.get_or_create(node_type, ip, {"ip": ip})

    def get_or_create_service(self, port: int, protocol: str) -> Node:
        """Create or retrieve a Service node keyed by port:protocol."""
        service_name = _port_to_service_name(port)
        key = f"{service_name}:{port}/{protocol.upper()}"
        return self.get_or_create(
            NodeType.SERVICE,
            key,
            {"port": port, "protocol": protocol, "service_name": service_name},
        )

    def get_or_create_domain(self, domain: str) -> Node:
        """Create or retrieve a Domain node (lowercased)."""
        return self.get_or_create(
            NodeType.DOMAIN,
            domain.lower().strip("."),
            {"domain": domain},
        )

    def get_or_create_user(self, username: str) -> Node:
        """Create or retrieve a User node."""
        return self.get_or_create(
            NodeType.USER,
            username.lower().strip(),
            {"username": username},
        )

    # ------------------------------------------------------------------
    # Bulk retrieval
    # ------------------------------------------------------------------

    def nodes_of_type(self, node_type: NodeType) -> list[Node]:
        """Return all nodes of a given type (snapshot — no live view)."""
        with self._lock:
            return [
                node for (nt, _), node in self._nodes.items()
                if nt == node_type
            ]

    def all_nodes(self) -> list[Node]:
        """Return all registered nodes."""
        with self._lock:
            return list(self._nodes.values())

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def total_nodes(self) -> int:
        with self._lock:
            return self._next_id

    def counts_by_type(self) -> dict[str, int]:
        """Return node counts per type."""
        with self._lock:
            return {t.value: count for t, count in self._type_counts.items()}

    def reset(self) -> None:
        """Clear all nodes — used between independent graph snapshots."""
        with self._lock:
            self._nodes.clear()
            self._id_to_node.clear()
            self._next_id = 0
            for t in NodeType:
                self._type_counts[t] = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _classify_ip(self, ip: str) -> NodeType:
        """Classify an IP as HOST (internal) or EXTERNAL_IP (public)."""
        for prefix in self._config.internal_ip_prefixes:
            if ip.startswith(prefix):
                return NodeType.HOST
        return NodeType.EXTERNAL_IP

    def __len__(self) -> int:
        return self.total_nodes

    def __repr__(self) -> str:
        counts = self.counts_by_type()
        return f"NodeRegistry(total={self.total_nodes}, counts={counts})"


# ---------------------------------------------------------------------------
# Port → service name lookup
# ---------------------------------------------------------------------------

_PORT_NAMES: dict[int, str] = {
    20: "ftp-data", 21: "ftp", 22: "ssh", 23: "telnet",
    25: "smtp", 53: "dns", 67: "dhcp", 80: "http",
    110: "pop3", 123: "ntp", 143: "imap", 161: "snmp",
    179: "bgp", 389: "ldap", 443: "https", 445: "smb",
    514: "syslog", 587: "smtp", 636: "ldaps", 993: "imaps",
    995: "pop3s", 1433: "mssql", 1521: "oracle", 3306: "mysql",
    3389: "rdp", 5432: "postgresql", 5900: "vnc", 6379: "redis",
    8080: "http-alt", 8443: "https-alt", 9092: "kafka", 27017: "mongodb",
}


def _port_to_service_name(port: int) -> str:
    return _PORT_NAMES.get(port, f"port-{port}")
