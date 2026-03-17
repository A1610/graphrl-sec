"""
PyG HeteroData Converter — transforms WindowResult into PyTorch Geometric graphs.

Converts the edge accumulator + node registry from a temporal window into a
PyG HeteroData object ready for GNN inference or training.

Node feature matrices per type:
  host         : (N_host,      8)   float32
  external_ip  : (N_ext,       8)   float32   (same features as host)
  service      : (N_svc,       4)   float32
  domain       : (N_dom,       4)   float32
  user         : (N_user,      8)   float32   (zeros — no stats yet)

Edge index + feature tensors per relation:
  (host|external_ip, connects_to,     host|external_ip)  : edge_index (2, E), edge_attr (E, 12)
  (host|external_ip, uses_service,    service)           : edge_index (2, E), edge_attr (E, 12)
  (host|external_ip, resolves_domain, domain)            : edge_index (2, E), edge_attr (E, 12)
  (host|external_ip, authenticated_as, user)             : edge_index (2, E), edge_attr (E, 12)

Node IDs are re-indexed per type starting from 0 within each HeteroData store.
"""

from __future__ import annotations

from collections import defaultdict
from typing import NamedTuple

import numpy as np
import numpy.typing as npt
import structlog
import torch
from torch_geometric.data import HeteroData

from src.graph.config import GraphConfig, graph_settings
from src.graph.edge_constructor import EdgeType
from src.graph.feature_engineering import (
    NodeStats,
    extract_domain_features,
    extract_host_features,
    extract_service_features,
)
from src.graph.node_registry import Node, NodeType
from src.graph.temporal import WindowResult

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

# NodeType -> HeteroData store name
_NODE_TYPE_TO_STORE: dict[NodeType, str] = {
    NodeType.HOST:        "host",
    NodeType.EXTERNAL_IP: "external_ip",
    NodeType.SERVICE:     "service",
    NodeType.DOMAIN:      "domain",
    NodeType.USER:        "user",
}

# EdgeType -> HeteroData relation name
_EDGE_TYPE_TO_REL: dict[EdgeType, str] = {
    EdgeType.CONNECTS_TO:      "connects_to",
    EdgeType.USES_SERVICE:     "uses_service",
    EdgeType.RESOLVES_DOMAIN:  "resolves_domain",
    EdgeType.AUTHENTICATED_AS: "authenticated_as",
}

# IP-type node types (HOST and EXTERNAL_IP share same feature extractor)
_IP_TYPES = {NodeType.HOST, NodeType.EXTERNAL_IP}


# ---------------------------------------------------------------------------
# Conversion result
# ---------------------------------------------------------------------------


class ConversionStats(NamedTuple):
    num_nodes:       int
    num_edges:       int
    node_type_counts: dict[str, int]
    edge_type_counts: dict[str, int]


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


class PyGConverter:
    """
    Converts a WindowResult into a PyG HeteroData graph.

    Each call to `convert()` produces one independent HeteroData object
    representing the network topology snapshot for that window.
    """

    def __init__(self, config: GraphConfig | None = None) -> None:
        self._config = config or graph_settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self, result: WindowResult) -> tuple[HeteroData, ConversionStats]:
        """
        Convert a WindowResult to a PyG HeteroData object.

        Args:
            result: WindowResult from SlidingWindowEngine.

        Returns:
            (HeteroData, ConversionStats) — graph + summary statistics.
        """
        acc        = result.accumulator
        registry   = result.registry
        window     = result.window

        # ----------------------------------------------------------------
        # Step 1: Build per-type local index maps  (global_id -> local_idx)
        # ----------------------------------------------------------------
        type_to_nodes:    dict[NodeType, list[Node]] = defaultdict(list)
        global_to_local:  dict[int, int] = {}

        for node in registry.all_nodes():
            local_idx = len(type_to_nodes[node.node_type])
            type_to_nodes[node.node_type].append(node)
            global_to_local[node.node_id] = local_idx

        # ----------------------------------------------------------------
        # Step 2: Build node feature matrices
        # ----------------------------------------------------------------
        data = HeteroData()

        node_type_counts: dict[str, int] = {}
        for ntype, nodes in type_to_nodes.items():
            store_name = _NODE_TYPE_TO_STORE[ntype]
            feat_rows  = []
            for node in nodes:
                feat = self._node_features(
                    node,
                    acc.get_stats(node.node_id),
                    window.start_ts,
                    window.end_ts,
                    ntype,
                )
                feat_rows.append(feat)

            x = torch.from_numpy(np.stack(feat_rows, axis=0))  # (N, D)
            data[store_name].x = x
            node_type_counts[store_name] = len(nodes)

        # ----------------------------------------------------------------
        # Step 3: Build edge index + attribute tensors
        # ----------------------------------------------------------------
        # Group edges by (src_store, rel, dst_store)
        edge_groups: dict[tuple[str, str, str], tuple[list[int], list[int], list[npt.NDArray[np.float32]]]] = defaultdict(
            lambda: ([], [], [])
        )

        for edge in acc.edges:
            src_store = _NODE_TYPE_TO_STORE[edge.src_node.node_type]
            dst_store = _NODE_TYPE_TO_STORE[edge.dst_node.node_type]
            rel       = _EDGE_TYPE_TO_REL[edge.edge_type]
            key       = (src_store, rel, dst_store)

            src_local = global_to_local.get(edge.src_node.node_id)
            dst_local = global_to_local.get(edge.dst_node.node_id)
            if src_local is None or dst_local is None:
                # Node not registered — should not happen in normal flow
                logger.warning(
                    "pyg_edge_node_missing",
                    src_id=edge.src_node.node_id,
                    dst_id=edge.dst_node.node_id,
                )
                continue

            src_list, dst_list, feat_list = edge_groups[key]
            src_list.append(src_local)
            dst_list.append(dst_local)
            feat_list.append(edge.features)

        edge_type_counts: dict[str, int] = {}
        for (src_store, rel, dst_store), (srcs, dsts, feats) in edge_groups.items():
            edge_index = torch.tensor([srcs, dsts], dtype=torch.long)   # (2, E)
            edge_attr  = torch.from_numpy(np.stack(feats, axis=0))       # (E, 12)
            data[src_store, rel, dst_store].edge_index = edge_index
            data[src_store, rel, dst_store].edge_attr  = edge_attr
            edge_type_counts[f"{src_store}__{rel}__{dst_store}"] = len(srcs)

        # ----------------------------------------------------------------
        # Step 4: Attach window metadata
        # ----------------------------------------------------------------
        data["window_id"]    = window.window_id
        data["start_ts"]     = window.start_ts
        data["end_ts"]       = window.end_ts
        data["num_events"]   = window.num_events

        stats = ConversionStats(
            num_nodes=sum(node_type_counts.values()),
            num_edges=sum(edge_type_counts.values()),
            node_type_counts=node_type_counts,
            edge_type_counts=edge_type_counts,
        )

        logger.debug(
            "pyg_conversion_complete",
            window_id=window.window_id,
            num_nodes=stats.num_nodes,
            num_edges=stats.num_edges,
        )
        return data, stats

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _node_features(
        self,
        node: Node,
        stats: NodeStats | None,
        window_start_ts: float,
        window_end_ts: float,
        ntype: NodeType,
    ) -> npt.NDArray[np.float32]:
        """Return the correct feature vector for a node type."""
        if ntype in _IP_TYPES:
            is_internal = ntype == NodeType.HOST
            return extract_host_features(
                node, stats, window_start_ts, window_end_ts, is_internal
            )
        if ntype == NodeType.SERVICE:
            port     = node.attributes.get("port", 0)
            protocol = node.attributes.get("protocol", "TCP")
            return extract_service_features(port, protocol)
        if ntype == NodeType.DOMAIN:
            domain = node.attributes.get("domain", node.entity_key)
            return extract_domain_features(domain)
        if ntype == NodeType.USER:
            # Users have no independent stats yet — zero vector (same dim as host)
            return np.zeros(self._config.host_feature_dim, dtype=np.float32)
        # Fallback — should never happen
        return np.zeros(8, dtype=np.float32)
