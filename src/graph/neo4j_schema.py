"""
Neo4j Schema Manager — creates constraints and indexes for GraphRL-Sec.

Constraints enforce node uniqueness per entity type (required for MERGE
idempotency in neo4j_writer.py).  Indexes accelerate common query patterns
(neighborhood lookup, time-range scans, top-communicator aggregation).

All operations use 'IF NOT EXISTS' — idempotent, safe to run every startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError, ServiceUnavailable

from src.graph.config import GraphConfig, graph_settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

# Uniqueness constraints — one per node type, on the canonical business key.
# These are REQUIRED: neo4j_writer.py uses MERGE on entity_key.
_CONSTRAINTS: list[tuple[str, str, str]] = [
    # (constraint_name, neo4j_label, property)
    ("graphrl_host_entity_key",       "Host",       "entity_key"),
    ("graphrl_extip_entity_key",      "ExternalIP", "entity_key"),
    ("graphrl_service_entity_key",    "Service",    "entity_key"),
    ("graphrl_domain_entity_key",     "Domain",     "entity_key"),
    ("graphrl_user_entity_key",       "User",       "entity_key"),
]

# Node property indexes — speed up property-based lookups.
_NODE_INDEXES: list[tuple[str, str, str]] = [
    # (index_name, neo4j_label, property)
    ("graphrl_host_ip_idx",           "Host",       "ip"),
    ("graphrl_extip_ip_idx",          "ExternalIP", "ip"),
    ("graphrl_domain_fqdn_idx",       "Domain",     "domain"),
    ("graphrl_service_port_idx",      "Service",    "port"),
    # window_id index — used by time-range queries
    ("graphrl_host_window_idx",       "Host",       "window_id"),
    ("graphrl_extip_window_idx",      "ExternalIP", "window_id"),
    ("graphrl_service_window_idx",    "Service",    "window_id"),
]

# Relationship indexes — speed up edge-level time-range scans.
_REL_INDEXES: list[tuple[str, str, str]] = [
    # (index_name, relationship_type, property)
    ("graphrl_connects_window_idx",   "CONNECTS_TO",      "window_id"),
    ("graphrl_uses_svc_window_idx",   "USES_SERVICE",     "window_id"),
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaStatus:
    """Summary of a schema setup operation."""

    constraints_applied: int   # count of constraint DDL statements run
    node_indexes_applied: int  # count of node index DDL statements run
    rel_indexes_applied: int   # count of relationship index DDL statements run
    errors: int                # count of unexpected errors (not "already exists")

    @property
    def total_applied(self) -> int:
        return self.constraints_applied + self.node_indexes_applied + self.rel_indexes_applied


# ---------------------------------------------------------------------------
# Schema Manager
# ---------------------------------------------------------------------------


class SchemaManager:
    """
    Creates and manages Neo4j schema constraints and indexes.

    Usage::

        with SchemaManager() as schema:
            status = schema.setup()
            print(status)

    All DDL statements are idempotent (IF NOT EXISTS).
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

    def __enter__(self) -> SchemaManager:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the Neo4j driver connection pool."""
        self._driver.close()
        self._log.debug("schema_manager_closed")

    def ping(self) -> bool:
        """Return True if Neo4j is reachable."""
        try:
            with self._driver.session() as session:
                session.run("RETURN 1")
            return True
        except ServiceUnavailable:
            return False

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> SchemaStatus:
        """
        Create all constraints and indexes (idempotent).

        Returns:
            SchemaStatus with applied counts and any error count.
        """
        constraints_applied = 0
        node_idx_applied    = 0
        rel_idx_applied     = 0
        errors              = 0

        with self._driver.session() as session:
            # --- Uniqueness constraints ---
            for name, label, prop in _CONSTRAINTS:
                cypher = (
                    f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                )
                ok = self._run_ddl(session, cypher, name, "constraint")
                if ok:
                    constraints_applied += 1
                else:
                    errors += 1

            # --- Node property indexes ---
            for name, label, prop in _NODE_INDEXES:
                cypher = (
                    f"CREATE INDEX {name} IF NOT EXISTS "
                    f"FOR (n:{label}) ON (n.{prop})"
                )
                ok = self._run_ddl(session, cypher, name, "node_index")
                if ok:
                    node_idx_applied += 1
                else:
                    errors += 1

            # --- Relationship property indexes ---
            for name, rel_type, prop in _REL_INDEXES:
                cypher = (
                    f"CREATE INDEX {name} IF NOT EXISTS "
                    f"FOR ()-[r:{rel_type}]-() ON (r.{prop})"
                )
                ok = self._run_ddl(session, cypher, name, "rel_index")
                if ok:
                    rel_idx_applied += 1
                else:
                    errors += 1

        status = SchemaStatus(
            constraints_applied=constraints_applied,
            node_indexes_applied=node_idx_applied,
            rel_indexes_applied=rel_idx_applied,
            errors=errors,
        )
        self._log.info(
            "schema_setup_complete",
            constraints=constraints_applied,
            node_indexes=node_idx_applied,
            rel_indexes=rel_idx_applied,
            errors=errors,
        )
        return status

    def drop_all(self) -> None:
        """
        Drop all GraphRL-Sec constraints and indexes.

        WARNING: For development / test teardown only.  Never call in production.
        """
        with self._driver.session() as session:
            for name, _, _ in _CONSTRAINTS:
                self._run_ddl(session, f"DROP CONSTRAINT {name} IF EXISTS", name, "drop_constraint")
            for name, _, _ in _NODE_INDEXES:
                self._run_ddl(session, f"DROP INDEX {name} IF EXISTS", name, "drop_node_index")
            for name, _, _ in _REL_INDEXES:
                self._run_ddl(session, f"DROP INDEX {name} IF EXISTS", name, "drop_rel_index")
        self._log.info("schema_dropped")

    def list_constraints(self) -> list[dict[str, object]]:
        """Return all existing constraints from Neo4j."""
        with self._driver.session() as session:
            result = session.run("SHOW CONSTRAINTS")
            return [dict(record) for record in result]

    def list_indexes(self) -> list[dict[str, object]]:
        """Return all existing indexes from Neo4j (excluding constraints)."""
        with self._driver.session() as session:
            result = session.run("SHOW INDEXES")
            return [dict(record) for record in result]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_ddl(
        self,
        session: Any,
        cypher: str,
        name: str,
        kind: str,
    ) -> bool:
        """
        Execute a single DDL statement.

        Returns True on success (including already-exists).
        Returns False only on unexpected errors.
        """
        try:
            session.run(cypher)
            self._log.debug("ddl_ok", kind=kind, name=name)
            return True
        except ClientError as exc:
            # "IF NOT EXISTS" should prevent most errors, but older Neo4j
            # versions may still raise if constraint/index already exists.
            msg = str(exc).lower()
            if "already exists" in msg or "equivalent" in msg:
                self._log.debug("ddl_already_exists", kind=kind, name=name)
                return True
            self._log.error("ddl_error", kind=kind, name=name, error=str(exc))
            return False
