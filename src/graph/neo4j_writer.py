"""
Neo4j Writer — persists graph snapshots to Neo4j for query and exploration.

Writes nodes and edges using batched Cypher MERGE statements so the
operation is idempotent — re-running ingestion does not create duplicates.

Node labels:   Host, ExternalIP, Service, Domain, User
Relationship:  CONNECTS_TO, USES_SERVICE, RESOLVES_DOMAIN, AUTHENTICATED_AS

Each node carries all feature values as properties for Cypher-level filtering.
Each relationship carries window_id, timestamp, and the 12 edge feature values.
"""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import GraphDatabase, Session
from neo4j.exceptions import ServiceUnavailable

from src.graph.config import GraphConfig, graph_settings
from src.graph.edge_constructor import EdgeAccumulator, EdgeType
from src.graph.node_registry import NodeRegistry, NodeType
from src.graph.temporal import WindowResult

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Cypher templates
# ---------------------------------------------------------------------------

# NodeType -> Neo4j label
_NODE_LABELS: dict[NodeType, str] = {
    NodeType.HOST:        "Host",
    NodeType.EXTERNAL_IP: "ExternalIP",
    NodeType.SERVICE:     "Service",
    NodeType.DOMAIN:      "Domain",
    NodeType.USER:        "User",
}

# EdgeType -> Neo4j relationship type
_EDGE_LABELS: dict[EdgeType, str] = {
    EdgeType.CONNECTS_TO:       "CONNECTS_TO",
    EdgeType.USES_SERVICE:      "USES_SERVICE",
    EdgeType.RESOLVES_DOMAIN:   "RESOLVES_DOMAIN",
    EdgeType.AUTHENTICATED_AS:  "AUTHENTICATED_AS",
}

_MERGE_NODE_CYPHER = """\
UNWIND $batch AS row
MERGE (n:{label} {{entity_key: row.entity_key}})
SET n += row.props
"""

_MERGE_EDGE_CYPHER = """\
UNWIND $batch AS row
MATCH (src:{src_label} {{entity_key: row.src_key}})
MATCH (dst:{dst_label} {{entity_key: row.dst_key}})
MERGE (src)-[r:{rel_type} {{edge_key: row.edge_key}}]->(dst)
SET r += row.props
"""

_CREATE_CONSTRAINTS_CYPHER = [
    "CREATE CONSTRAINT host_key IF NOT EXISTS FOR (n:Host) REQUIRE n.entity_key IS UNIQUE",
    "CREATE CONSTRAINT extip_key IF NOT EXISTS FOR (n:ExternalIP) REQUIRE n.entity_key IS UNIQUE",
    "CREATE CONSTRAINT service_key IF NOT EXISTS FOR (n:Service) REQUIRE n.entity_key IS UNIQUE",
    "CREATE CONSTRAINT domain_key IF NOT EXISTS FOR (n:Domain) REQUIRE n.entity_key IS UNIQUE",
    "CREATE CONSTRAINT user_key IF NOT EXISTS FOR (n:User) REQUIRE n.entity_key IS UNIQUE",
]


# ---------------------------------------------------------------------------
# Neo4j Writer
# ---------------------------------------------------------------------------


class Neo4jWriter:
    """
    Writes graph snapshots to Neo4j using batched MERGE operations.

    Usage::

        writer = Neo4jWriter()
        writer.ensure_constraints()
        for result in engine.process_stream(events):
            writer.write_window(result)
        writer.close()

    Or use as context manager::

        with Neo4jWriter() as writer:
            writer.ensure_constraints()
            writer.write_window(result)
    """

    def __init__(self, config: GraphConfig | None = None) -> None:
        self._config = config or graph_settings
        self._driver = GraphDatabase.driver(
            self._config.neo4j_uri,
            auth=(self._config.neo4j_user, self._config.neo4j_password),
            max_connection_pool_size=self._config.neo4j_max_connection_pool_size,
            connection_timeout=self._config.neo4j_connection_timeout_s,
        )
        self._log = logger.bind(uri=self._config.neo4j_uri)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __enter__(self) -> Neo4jWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._driver.close()
        self._log.info("neo4j_driver_closed")

    def ping(self) -> bool:
        """Return True if Neo4j is reachable."""
        try:
            with self._driver.session() as session:
                session.run("RETURN 1")
            return True
        except ServiceUnavailable:
            return False

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def ensure_constraints(self) -> None:
        """Create uniqueness constraints (idempotent)."""
        with self._driver.session() as session:
            for cypher in _CREATE_CONSTRAINTS_CYPHER:
                try:
                    session.run(cypher)
                except Exception as exc:  # noqa: BLE001
                    # Constraint may already exist — log and continue
                    self._log.debug("constraint_already_exists", error=str(exc))
        self._log.info("neo4j_constraints_ensured")

    # ------------------------------------------------------------------
    # Write a complete window
    # ------------------------------------------------------------------

    def write_window(self, result: WindowResult) -> None:
        """
        Persist all nodes and edges from a window to Neo4j.

        Operations are batched per `neo4j_batch_write_size` to avoid
        memory pressure on large windows.
        """
        window   = result.window
        acc      = result.accumulator
        registry = result.registry
        batch_sz = self._config.neo4j_batch_write_size

        self._log.info(
            "neo4j_write_window_start",
            window_id=window.window_id,
            nodes=registry.total_nodes,
            edges=acc.num_edges,
        )

        with self._driver.session() as session:
            self._write_nodes(session, registry, window.window_id, batch_sz)
            self._write_edges(session, acc, window.window_id, batch_sz)

        self._log.info("neo4j_write_window_done", window_id=window.window_id)

    # ------------------------------------------------------------------
    # Node writing
    # ------------------------------------------------------------------

    def _write_nodes(
        self,
        session: Session,
        registry: NodeRegistry,
        window_id: int,
        batch_sz: int,
    ) -> None:
        """Batch-merge all nodes grouped by label."""
        nodes_by_type: dict[NodeType, list[dict[str, Any]]] = {t: [] for t in NodeType}
        for node in registry.all_nodes():
            props: dict[str, Any] = {
                "node_id":   node.node_id,
                "window_id": window_id,
            }
            props.update(node.attributes)
            nodes_by_type[node.node_type].append({
                "entity_key": node.entity_key,
                "props":      props,
            })

        for ntype, rows in nodes_by_type.items():
            if not rows:
                continue
            label  = _NODE_LABELS[ntype]
            cypher = _MERGE_NODE_CYPHER.format(label=label)
            for i in range(0, len(rows), batch_sz):
                session.run(cypher, batch=rows[i: i + batch_sz])

    # ------------------------------------------------------------------
    # Edge writing
    # ------------------------------------------------------------------

    def _write_edges(
        self,
        session: Session,
        acc: EdgeAccumulator,
        window_id: int,
        batch_sz: int,
    ) -> None:
        """
        Batch-merge all edges grouped by (EdgeType, src_node_type, dst_node_type).

        Grouping by the full (rel_type, src_label, dst_label) triple is required
        because CONNECTS_TO can have HOST or EXTERNAL_IP as either endpoint.
        Using a single src_label derived from the first edge would cause silent
        MATCH failures for edges with different node-type combinations.
        """
        # Key: (EdgeType, src NodeType, dst NodeType)
        edges_by_combo: dict[tuple[EdgeType, NodeType, NodeType], list[dict[str, Any]]] = {}

        for edge in acc.edges:
            combo = (edge.edge_type, edge.src_node.node_type, edge.dst_node.node_type)
            if combo not in edges_by_combo:
                edges_by_combo[combo] = []
            props: dict[str, Any] = {f"feat_{i}": float(v) for i, v in enumerate(edge.features)}
            props["window_id"] = window_id
            # Content-based key: identical (src, dst, rel_type, window) edges merge
            # correctly on re-run without creating duplicates.
            edge_key = (
                f"{window_id}:{_EDGE_LABELS[edge.edge_type]}"
                f":{edge.src_node.entity_key}:{edge.dst_node.entity_key}"
            )
            edges_by_combo[combo].append({
                "src_key":  edge.src_node.entity_key,
                "dst_key":  edge.dst_node.entity_key,
                "edge_key": edge_key,
                "props":    props,
            })

        for (etype, src_ntype, dst_ntype), rows in edges_by_combo.items():
            rel_type  = _EDGE_LABELS[etype]
            src_label = _NODE_LABELS[src_ntype]
            dst_label = _NODE_LABELS[dst_ntype]
            cypher    = _MERGE_EDGE_CYPHER.format(
                rel_type=rel_type, src_label=src_label, dst_label=dst_label
            )
            for i in range(0, len(rows), batch_sz):
                session.run(cypher, batch=rows[i: i + batch_sz])
