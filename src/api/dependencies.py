"""
FastAPI dependency injection providers for the GraphRL-Sec API.

Provides a singleton Neo4jQueryService to all route handlers via
FastAPI's Depends() mechanism. The singleton is created during application
startup and closed during shutdown via the lifespan context in main.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Generator

from fastapi import Depends, HTTPException, status

if TYPE_CHECKING:
    from src.graph.neo4j_queries import Neo4jQueryService

# ---------------------------------------------------------------------------
# Singleton holder — populated by lifespan in main.py
# ---------------------------------------------------------------------------

_query_service: "Neo4jQueryService | None" = None


def set_query_service(service: "Neo4jQueryService") -> None:
    """Called once during application startup to register the singleton."""
    global _query_service
    _query_service = service


def clear_query_service() -> None:
    """Called during application shutdown to release the reference."""
    global _query_service
    _query_service = None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_query_service() -> Generator["Neo4jQueryService", None, None]:
    """
    Yield the Neo4jQueryService singleton for injection via Depends().

    Raises:
        503 Service Unavailable — if the service has not been initialised
        (e.g., Neo4j was unreachable at startup).
    """
    if _query_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j query service is not available. Check database connectivity.",
        )
    yield _query_service


QueryServiceDep = Annotated["Neo4jQueryService", Depends(get_query_service)]
