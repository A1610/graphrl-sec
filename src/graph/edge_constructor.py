"""
Edge Constructor — maps UnifiedEvent objects to typed graph edges.

Each UnifiedEvent produces one or more (src_node, edge_type, dst_node, features)
tuples.  The edge schema follows the heterogeneous graph specification:

    src_type  --[edge_type]--> dst_type

Supported edge types:
  HOST/EXTERNAL_IP  --[CONNECTS_TO]--> HOST/EXTERNAL_IP
  HOST/EXTERNAL_IP  --[USES_SERVICE]--> SERVICE
  HOST/EXTERNAL_IP  --[RESOLVES_DOMAIN]--> DOMAIN
  HOST/EXTERNAL_IP  --[AUTHENTICATED_AS]--> USER

All edges carry a 12-dim float32 feature vector (see feature_engineering).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple

import numpy as np
import numpy.typing as npt
import structlog

from src.graph.config import GraphConfig, graph_settings
from src.graph.feature_engineering import (
    NodeStats,
    extract_edge_features,
)
from src.graph.node_registry import Node, NodeRegistry
from src.ingestion.schemas import UnifiedEvent

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Edge type enum
# ---------------------------------------------------------------------------


class EdgeType(str, Enum):
    CONNECTS_TO     = "connects_to"       # IP -> IP
    USES_SERVICE    = "uses_service"      # IP -> Service
    RESOLVES_DOMAIN = "resolves_domain"   # IP -> Domain
    AUTHENTICATED_AS = "authenticated_as" # IP -> User


# ---------------------------------------------------------------------------
# Edge descriptor
# ---------------------------------------------------------------------------


class Edge(NamedTuple):
    """A single directed edge in the heterogeneous graph."""

    src_node:  Node
    edge_type: EdgeType
    dst_node:  Node
    features:  npt.NDArray[np.float32]   # shape (12,)


# ---------------------------------------------------------------------------
# Per-window edge accumulator
# ---------------------------------------------------------------------------


@dataclass
class EdgeAccumulator:
    """
    Accumulates edges and per-node statistics for one time window.

    After all events in a window are processed, the node feature vectors
    are finalized via `get_node_features()`.
    """

    window_start_ts: float
    window_end_ts:   float

    # Ordered list of edges (insertion order preserved for reproducibility)
    edges: list[Edge] = field(default_factory=list)

    # Per-node running stats (node_id -> NodeStats)
    _node_stats: dict[int, NodeStats] = field(default_factory=dict)

    def add_edge(self, edge: Edge, src_stats_update: tuple[UnifiedEvent, int] | None = None) -> None:
        """
        Append an edge and optionally update src-node statistics.

        Args:
            edge:              The Edge to record.
            src_stats_update:  (event, dst_node_id) pair for NodeStats.update().
        """
        self.edges.append(edge)
        if src_stats_update is not None:
            event, dst_node_id = src_stats_update
            stats = self._node_stats.setdefault(edge.src_node.node_id, NodeStats())
            stats.update(event, dst_node_id)

    def get_stats(self, node_id: int) -> NodeStats | None:
        return self._node_stats.get(node_id)

    @property
    def num_edges(self) -> int:
        return len(self.edges)

    @property
    def num_nodes_with_stats(self) -> int:
        return len(self._node_stats)


# ---------------------------------------------------------------------------
# Edge Constructor
# ---------------------------------------------------------------------------


class EdgeConstructor:
    """
    Converts UnifiedEvent objects into typed graph edges.

    For each event the constructor:
      1. Looks up / creates src and dst IP nodes in the NodeRegistry.
      2. Creates a CONNECTS_TO edge between them.
      3. Optionally creates a USES_SERVICE edge if dst port is non-zero.
      4. Optionally creates a RESOLVES_DOMAIN edge if a domain is present.
      5. Optionally creates an AUTHENTICATED_AS edge if a username is present.

    All edge feature vectors are extracted via extract_edge_features().
    """

    def __init__(
        self,
        registry: NodeRegistry,
        config: GraphConfig | None = None,
    ) -> None:
        self._registry = registry
        self._config = config or graph_settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_event(
        self,
        event: UnifiedEvent,
        accumulator: EdgeAccumulator,
    ) -> list[Edge]:
        """
        Convert one UnifiedEvent into graph edges and record them.

        Returns:
            List of Edge objects created (1–4 edges per event).
        """
        edges_created: list[Edge] = []

        # Resolve src / dst IP nodes
        src_node = self._registry.get_or_create_ip(event.source.ip)
        dst_node = self._registry.get_or_create_ip(event.destination.ip)

        # Check degree cap before adding more edges from this source
        src_stats = accumulator.get_stats(src_node.node_id)
        if src_stats is not None and src_stats.degree >= self._config.max_node_degree:
            logger.debug(
                "edge_degree_cap_reached",
                node_id=src_node.node_id,
                ip=event.source.ip,
                degree=src_stats.degree,
            )
            return []

        # ----------------------------------------------------------------
        # 1. Primary IP-to-IP edge
        # ----------------------------------------------------------------
        feats = extract_edge_features(
            event,
            accumulator.window_start_ts,
            accumulator.window_end_ts,
        )
        ip_edge = Edge(
            src_node=src_node,
            edge_type=EdgeType.CONNECTS_TO,
            dst_node=dst_node,
            features=feats,
        )
        accumulator.add_edge(ip_edge, src_stats_update=(event, dst_node.node_id))
        edges_created.append(ip_edge)

        # ----------------------------------------------------------------
        # 2. USES_SERVICE edge (dst_ip -> service)
        # ----------------------------------------------------------------
        dst_port = event.destination.port
        if dst_port and dst_port > 0:
            svc_node = self._registry.get_or_create_service(
                dst_port,
                event.network.protocol.value,
            )
            svc_edge = Edge(
                src_node=dst_node,
                edge_type=EdgeType.USES_SERVICE,
                dst_node=svc_node,
                features=feats,  # same edge features (context-carrying)
            )
            accumulator.add_edge(svc_edge)
            edges_created.append(svc_edge)

        # ----------------------------------------------------------------
        # 3. RESOLVES_DOMAIN edge (src_ip -> domain)
        #    Uses destination.hostname — the actual DNS field in UnifiedEvent.
        # ----------------------------------------------------------------
        hostname = event.destination.hostname
        if hostname:
            dom_node = self._registry.get_or_create_domain(hostname)
            dom_edge = Edge(
                src_node=src_node,
                edge_type=EdgeType.RESOLVES_DOMAIN,
                dst_node=dom_node,
                features=feats,
            )
            accumulator.add_edge(dom_edge)
            edges_created.append(dom_edge)

        # NOTE: AUTHENTICATED_AS edges are reserved for LANL / auth-log datasets
        # (Phase 3). UnifiedEvent has no username field in CICIDS/UNSW schemas.

        return edges_created

    def process_batch(
        self,
        events: list[UnifiedEvent],
        window_start_ts: float,
        window_end_ts: float,
    ) -> EdgeAccumulator:
        """
        Process a list of events into a fresh EdgeAccumulator.

        Args:
            events:          Events for this time window.
            window_start_ts: Window start as Unix timestamp.
            window_end_ts:   Window end as Unix timestamp.

        Returns:
            Populated EdgeAccumulator (edges + node stats).
        """
        acc = EdgeAccumulator(
            window_start_ts=window_start_ts,
            window_end_ts=window_end_ts,
        )
        skipped = 0
        for event in events:
            created = self.process_event(event, acc)
            if not created:
                skipped += 1

        if skipped:
            logger.debug("edge_constructor_batch_skipped", skipped=skipped, total=len(events))

        logger.debug(
            "edge_constructor_batch_complete",
            events=len(events),
            edges=acc.num_edges,
            nodes_with_stats=acc.num_nodes_with_stats,
        )
        return acc
