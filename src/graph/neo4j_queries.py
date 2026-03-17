"""
Neo4j Query Service — read-only graph queries for SOC analysis.

All methods return typed Python dataclasses (not raw neo4j Records).
The driver connection pool is managed by the underlying neo4j driver.

Query methods:
    get_neighborhood        — N-hop subgraph around a given IP
    get_time_window_edges   — all CONNECTS_TO edges in a Unix timestamp range
    get_top_communicators   — most active hosts by outbound connection count
    get_anomalous_paths     — hosts whose attack_score exceeds a threshold
    get_graph_stats         — total node / edge counts per type

All Cypher uses parameterized queries — no string interpolation of user input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

from src.graph.config import GraphConfig, graph_settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses (frozen — safe to cache / serialize)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeResult:
    """A single graph node returned by a query."""

    entity_key: str
    node_label: str                        # "Host", "ExternalIP", etc.
    properties: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class EdgeResult:
    """A single graph relationship returned by a query."""

    src_key:  str
    dst_key:  str
    rel_type: str                          # "CONNECTS_TO", "USES_SERVICE", etc.
    properties: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class NeighborhoodResult:
    """Subgraph centred on a specific IP address."""

    center_ip: str
    hops:      int
    nodes:     tuple[NodeResult, ...]      # immutable, deterministic order
    edges:     tuple[EdgeResult, ...]


@dataclass(frozen=True)
class TimeWindowResult:
    """All connections observed in a Unix timestamp range."""

    start_ts: float
    end_ts:   float
    edges:    tuple[EdgeResult, ...]

    @property
    def edge_count(self) -> int:
        return len(self.edges)


@dataclass(frozen=True)
class CommunicatorResult:
    """A host ranked by outbound connection volume."""

    entity_key:          str
    node_label:          str
    outbound_count:      int   # distinct CONNECTS_TO relationships
    unique_destinations: int   # distinct dst entity_keys


@dataclass(frozen=True)
class GraphStats:
    """Aggregate node/edge counts for the entire database."""

    host_count:            int
    external_ip_count:     int
    service_count:         int
    domain_count:          int
    user_count:            int
    connects_to_count:     int
    uses_service_count:    int
    resolves_domain_count: int
    authenticated_as_count: int

    @property
    def total_nodes(self) -> int:
        return (
            self.host_count + self.external_ip_count + self.service_count
            + self.domain_count + self.user_count
        )

    @property
    def total_edges(self) -> int:
        return (
            self.connects_to_count + self.uses_service_count
            + self.resolves_domain_count + self.authenticated_as_count
        )


# ---------------------------------------------------------------------------
# Cypher templates (parameterized — no f-string injection)
# ---------------------------------------------------------------------------

# N-hop neighbourhood: collect all nodes and relationships within `hops` steps
_NEIGHBORHOOD_CYPHER = """\
MATCH path = (center {entity_key: $entity_key})-[*1..$hops]-(neighbor)
WITH nodes(path) AS ns, relationships(path) AS rs
UNWIND ns AS n
WITH DISTINCT n, rs
RETURN
    n.entity_key            AS entity_key,
    labels(n)[0]            AS node_label,
    properties(n)           AS props,
    [r IN rs | {
        src:   startNode(r).entity_key,
        dst:   endNode(r).entity_key,
        type:  type(r),
        props: properties(r)
    }] AS edges
"""

_TIME_WINDOW_CYPHER = """\
MATCH (src)-[r:CONNECTS_TO]->(dst)
WHERE r.window_id >= $min_window AND r.window_id <= $max_window
RETURN
    src.entity_key  AS src_key,
    dst.entity_key  AS dst_key,
    type(r)         AS rel_type,
    properties(r)   AS props
ORDER BY r.window_id ASC
LIMIT $limit
"""

_TOP_COMMUNICATORS_CYPHER = """\
MATCH (src)-[r:CONNECTS_TO]->(dst)
WITH src, count(r) AS outbound, count(DISTINCT dst.entity_key) AS unique_dsts
ORDER BY outbound DESC
LIMIT $limit
RETURN
    src.entity_key  AS entity_key,
    labels(src)[0]  AS node_label,
    outbound        AS outbound_count,
    unique_dsts     AS unique_destinations
"""

_ANOMALOUS_PATHS_CYPHER = """\
MATCH (src)-[r:CONNECTS_TO]->(dst)
WHERE src.attack_score >= $threshold OR dst.attack_score >= $threshold
WITH src, dst, r
ORDER BY src.attack_score DESC
RETURN DISTINCT
    src.entity_key  AS src_key,
    dst.entity_key  AS dst_key,
    type(r)         AS rel_type,
    properties(r)   AS props
LIMIT $limit
"""

_GRAPH_STATS_CYPHER = """\
CALL {
    MATCH (n:Host)       RETURN count(n) AS c, 'host'            AS t
    UNION ALL
    MATCH (n:ExternalIP) RETURN count(n) AS c, 'external_ip'     AS t
    UNION ALL
    MATCH (n:Service)    RETURN count(n) AS c, 'service'         AS t
    UNION ALL
    MATCH (n:Domain)     RETURN count(n) AS c, 'domain'          AS t
    UNION ALL
    MATCH (n:User)       RETURN count(n) AS c, 'user'            AS t
    UNION ALL
    MATCH ()-[r:CONNECTS_TO]->()      RETURN count(r) AS c, 'connects_to'      AS t
    UNION ALL
    MATCH ()-[r:USES_SERVICE]->()     RETURN count(r) AS c, 'uses_service'     AS t
    UNION ALL
    MATCH ()-[r:RESOLVES_DOMAIN]->()  RETURN count(r) AS c, 'resolves_domain'  AS t
    UNION ALL
    MATCH ()-[r:AUTHENTICATED_AS]->() RETURN count(r) AS c, 'authenticated_as' AS t
}
RETURN t AS category, c AS count
"""


# ---------------------------------------------------------------------------
# Query Service
# ---------------------------------------------------------------------------


class Neo4jQueryService:
    """
    Read-only graph query service for SOC dashboard and campaign detection.

    Usage::

        with Neo4jQueryService() as qs:
            stats = qs.get_graph_stats()
            top   = qs.get_top_communicators(limit=10)

    Thread safety: safe — each method opens its own session.
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

    def __enter__(self) -> Neo4jQueryService:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._driver.close()
        self._log.debug("query_service_closed")

    def ping(self) -> bool:
        """Return True if Neo4j is reachable."""
        try:
            with self._driver.session() as session:
                session.run("RETURN 1")
            return True
        except ServiceUnavailable:
            return False

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_neighborhood(
        self,
        ip: str,
        hops: int = 2,
    ) -> NeighborhoodResult:
        """
        Return the N-hop subgraph centred on an IP address.

        Args:
            ip:   The IP entity_key to use as the traversal centre.
            hops: Maximum relationship hops from the centre node.

        Returns:
            NeighborhoodResult with deduplicated nodes and edges.
        """
        hops = max(1, min(hops, 4))   # safety cap — 5+ hops can be unbounded

        with self._driver.session() as session:
            records = list(session.run(
                _NEIGHBORHOOD_CYPHER,
                entity_key=ip,
                hops=hops,
            ))

        nodes_seen: dict[str, NodeResult] = {}
        edges_seen: dict[tuple[str, str, str], EdgeResult] = {}

        for record in records:
            # Collect node
            ek = record["entity_key"]
            if ek and ek not in nodes_seen:
                nodes_seen[ek] = NodeResult(
                    entity_key=ek,
                    node_label=record["node_label"] or "Unknown",
                    properties=dict(record["props"] or {}),
                )
            # Collect edges from path
            for edge_data in (record["edges"] or []):
                e_key = (edge_data["src"], edge_data["dst"], edge_data["type"])
                if e_key not in edges_seen:
                    edges_seen[e_key] = EdgeResult(
                        src_key=edge_data["src"],
                        dst_key=edge_data["dst"],
                        rel_type=edge_data["type"],
                        properties=dict(edge_data["props"] or {}),
                    )

        result = NeighborhoodResult(
            center_ip=ip,
            hops=hops,
            nodes=tuple(nodes_seen.values()),
            edges=tuple(edges_seen.values()),
        )
        self._log.debug(
            "neighborhood_query",
            ip=ip,
            hops=hops,
            nodes=len(result.nodes),
            edges=len(result.edges),
        )
        return result

    def get_time_window_edges(
        self,
        min_window_id: int,
        max_window_id: int,
        limit: int = 10_000,
    ) -> TimeWindowResult:
        """
        Return all CONNECTS_TO edges whose window_id falls in [min, max].

        Args:
            min_window_id: Inclusive lower bound on window_id.
            max_window_id: Inclusive upper bound on window_id.
            limit:         Max edges to return (prevents unbounded result sets).

        Returns:
            TimeWindowResult with matching edges sorted by window_id ascending.
        """
        with self._driver.session() as session:
            records = list(session.run(
                _TIME_WINDOW_CYPHER,
                min_window=min_window_id,
                max_window=max_window_id,
                limit=limit,
            ))

        edges = tuple(
            EdgeResult(
                src_key=r["src_key"],
                dst_key=r["dst_key"],
                rel_type=r["rel_type"],
                properties=dict(r["props"] or {}),
            )
            for r in records
        )
        result = TimeWindowResult(
            start_ts=float(min_window_id),
            end_ts=float(max_window_id),
            edges=edges,
        )
        self._log.debug(
            "time_window_query",
            min_window=min_window_id,
            max_window=max_window_id,
            edges=len(edges),
        )
        return result

    def get_top_communicators(
        self,
        limit: int = 20,
    ) -> list[CommunicatorResult]:
        """
        Return the most active hosts ranked by outbound CONNECTS_TO count.

        Args:
            limit: Maximum number of hosts to return.

        Returns:
            List of CommunicatorResult sorted by outbound_count descending.
        """
        with self._driver.session() as session:
            records = list(session.run(_TOP_COMMUNICATORS_CYPHER, limit=limit))

        results = [
            CommunicatorResult(
                entity_key=r["entity_key"],
                node_label=r["node_label"] or "Unknown",
                outbound_count=int(r["outbound_count"]),
                unique_destinations=int(r["unique_destinations"]),
            )
            for r in records
        ]
        self._log.debug("top_communicators_query", limit=limit, returned=len(results))
        return results

    def get_anomalous_paths(
        self,
        score_threshold: float = 0.5,
        limit: int = 1_000,
    ) -> list[EdgeResult]:
        """
        Return CONNECTS_TO edges where either endpoint has a high attack_score.

        The attack_score property is set by the feature engineering module
        as the fraction of events from that node that were flagged as attacks.

        Args:
            score_threshold: Minimum attack_score (0–1) on src or dst.
            limit:           Maximum edges to return.

        Returns:
            List of EdgeResult sorted by src attack_score descending.
        """
        with self._driver.session() as session:
            records = list(session.run(
                _ANOMALOUS_PATHS_CYPHER,
                threshold=score_threshold,
                limit=limit,
            ))

        results = [
            EdgeResult(
                src_key=r["src_key"],
                dst_key=r["dst_key"],
                rel_type=r["rel_type"],
                properties=dict(r["props"] or {}),
            )
            for r in records
        ]
        self._log.debug(
            "anomalous_paths_query",
            threshold=score_threshold,
            returned=len(results),
        )
        return results

    def get_graph_stats(self) -> GraphStats:
        """
        Return total node and edge counts per type across the entire database.

        Returns:
            GraphStats with counts for all 5 node types and 4 edge types.
        """
        with self._driver.session() as session:
            records = list(session.run(_GRAPH_STATS_CYPHER))

        counts: dict[str, int] = {r["category"]: int(r["count"]) for r in records}
        stats = GraphStats(
            host_count=counts.get("host", 0),
            external_ip_count=counts.get("external_ip", 0),
            service_count=counts.get("service", 0),
            domain_count=counts.get("domain", 0),
            user_count=counts.get("user", 0),
            connects_to_count=counts.get("connects_to", 0),
            uses_service_count=counts.get("uses_service", 0),
            resolves_domain_count=counts.get("resolves_domain", 0),
            authenticated_as_count=counts.get("authenticated_as", 0),
        )
        self._log.debug(
            "graph_stats_query",
            total_nodes=stats.total_nodes,
            total_edges=stats.total_edges,
        )
        return stats
